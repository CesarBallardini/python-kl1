"""Streams -- incremental lists over logic variables, the KL1 dataflow channel.

A *stream* is a :class:`~python_kl1.core.logicvar.Var` that gets bound to either
:data:`~python_kl1.core.terms.NIL` (the end) or a
:class:`~python_kl1.core.terms.Cons` cell ``Cons(head, tail)`` whose ``tail`` is
the next stream. Producers extend the open tail; consumers suspend on it until it
appears. Nothing here is a new mechanism -- it is all sugar over write-once
binding and per-variable wake-lists.

The goal is that these read like ordinary Python primitives and drop into
ordinary Python code: :class:`Producer` is a context manager, :func:`stream_from`
turns any iterable (or generator) into a stream, and :func:`drain` turns a
suspending stream back into a plain Python iterator you can ``for``-loop over.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from python_kl1.core.logicvar import Var, deref, unify
from python_kl1.core.terms import NIL, Cons

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from types import TracebackType

    from python_kl1.core.engine import Engine, Goal
    from python_kl1.core.terms import Value


type Consumer = Callable[[Value], None]
"""A per-element sink -- the callback :func:`each` invokes for each stream element."""

type Transform = Callable[[Value], Value]
"""A value-to-value function -- the mapping applied by :func:`map_stream`."""

type Test = Callable[[Value], bool]
"""A value predicate -- the keep-decision applied by :func:`filter_stream`."""


def put(stream: Var, value: Value) -> Var:
    """Extend ``stream`` with one ``value``; return the fresh unbound tail (the new stream)."""
    tail = Var()
    unify(stream, Cons(value, tail))
    return tail


def close(stream: Var) -> None:
    """Terminate ``stream`` by binding its open tail to :data:`NIL`."""
    unify(stream, NIL)


class Producer:
    """A mutable write-end for a stream, usable as a context manager.

    Holds the current open tail and advances it on each :meth:`put`, so producing
    reads like appending to a list. Leaving the ``with`` block closes the stream::

        head, producer = open_stream()
        with producer:
            producer.put(1)
            producer.put(2)
        # head is now the stream 1, 2, NIL
    """

    __slots__ = ('_tail',)

    def __init__(self, stream: Var) -> None:
        """Wrap the open tail ``stream`` as a write-end."""
        self._tail = stream

    def put(self, value: Value) -> None:
        """Append ``value`` to the stream."""
        self._tail = put(self._tail, value)

    def close(self) -> None:
        """Close the stream (idempotent-ish: only valid once, like any tell)."""
        close(self._tail)

    def __enter__(self) -> Producer:
        """Enter the producing scope."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the stream on scope exit."""
        self.close()


def open_stream() -> tuple[Var, Producer]:
    """Create a new stream, returning ``(head, producer)`` -- the read-end and write-end."""
    head = Var()
    return head, Producer(head)


def stream_from(engine: Engine, items: Iterable[Value]) -> Var:
    """Spawn a producer goal that writes ``items`` onto a fresh stream, then closes it.

    ``items`` may be any iterable, including a generator -- the KL1 analogue of a
    Python generator feeding a channel.
    """
    head = Var()
    iterator = iter(items)

    def step(stream: Var) -> None:
        try:
            value = next(iterator)
        except StopIteration:
            close(stream)
            return
        engine.spawn(lambda: step(put(stream, value)))

    engine.spawn(lambda: step(head))
    return head


def each(
    engine: Engine,
    stream: Var,
    on_item: Consumer,
    on_end: Goal | None = None,
) -> None:
    """Consume ``stream``, calling ``on_item`` per element and ``on_end`` at the end.

    Suspends on each unbound tail and resumes when a producer extends it, so the
    consumer never busy-waits.
    """

    def wait(rest: Value) -> None:
        def resume() -> None:
            cell = deref(rest)
            if cell is NIL:
                if on_end is not None:
                    on_end()
            elif isinstance(cell, Cons):
                on_item(deref(cell.head))
                wait(cell.tail)

        engine.when_bound(rest, resume)

    wait(stream)


def collect(engine: Engine, stream: Var) -> list[Value]:
    """Attach a consumer that accumulates ``stream`` into a list.

    Returns the list immediately; it fills as the engine runs, so read it after
    :meth:`~python_kl1.core.engine.Engine.run`.
    """
    out: list[Value] = []
    each(engine, stream, out.append)
    return out


def to_list(stream: Value) -> list[Value]:
    """Materialise a fully-bound stream (a chain of cons cells) into a Python list.

    Walks the ``Cons`` chain, dereferencing each element, until it reaches ``NIL``.
    Raises :class:`ValueError` if the value is not a proper, fully-bound list -- e.g.
    an atom, or a stream whose tail is still unbound (not yet run to quiescence).
    """
    items: list[Value] = []
    cell = deref(stream)
    while isinstance(cell, Cons):
        items.append(deref(cell.head))
        cell = deref(cell.tail)
    if cell is not NIL:
        raise ValueError(f'not a fully-materialised list: ends in {cell!r}')
    return items


def drain(engine: Engine, stream: Var) -> Iterator[Value]:
    """Pump the engine and yield ``stream``'s elements in order, as a Python iterator.

    This bridges the two worlds: a suspending KL1 stream becomes an ordinary
    iterator you can ``for``-loop over or pass to ``list()``. It drives the engine
    one goal at a time, yielding each element as it is produced.
    """
    items: list[Value] = []
    each(engine, stream, items.append)
    seen = 0
    while engine.step():
        while seen < len(items):
            yield items[seen]
            seen += 1
    while seen < len(items):
        yield items[seen]
        seen += 1


def map_stream(engine: Engine, source: Var, fn: Transform) -> Var:
    """Transducer: a new stream of ``fn(x)`` for each ``x`` in ``source``."""
    out = Var()

    def wait(rest: Value, tail: Var) -> None:
        def resume() -> None:
            cell = deref(rest)
            if cell is NIL:
                close(tail)
            elif isinstance(cell, Cons):
                wait(cell.tail, put(tail, fn(deref(cell.head))))

        engine.when_bound(rest, resume)

    wait(source, out)
    return out


def filter_stream(engine: Engine, source: Var, pred: Test) -> Var:
    """Transducer: a new stream of the ``x`` in ``source`` for which ``pred(x)`` holds."""
    out = Var()

    def wait(rest: Value, tail: Var) -> None:
        def resume() -> None:
            cell = deref(rest)
            if cell is NIL:
                close(tail)
            elif isinstance(cell, Cons):
                value = deref(cell.head)
                wait(cell.tail, put(tail, value) if pred(value) else tail)

        engine.when_bound(rest, resume)

    wait(source, out)
    return out
