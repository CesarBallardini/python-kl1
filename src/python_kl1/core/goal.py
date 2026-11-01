"""Committed-choice goal reduction with a decorated-clause surface.

A :class:`Predicate` is an ordered set of guarded clauses -- the KL1
``Head :- Guard | Body`` unit expressed in Python. Each clause is a function of the
goal's arguments that inspects them (dereferencing as needed) and returns one of:

- ``fail()``          -- this clause does not apply;
- ``suspend(*vars)``  -- the guard cannot decide yet; retry when one of ``vars`` binds;
- ``commit(body)``    -- this clause is chosen; run ``body(engine)`` (bind results, spawn goals).

Reduction tries the clauses in order: the **first ``commit`` wins** (committed choice,
no backtracking); if none commits but some suspended, the whole goal suspends on the
union of their variables and is retried when any binds; if every clause fails, the goal
has no matching clause (:class:`NoMatchingClauseError`).

This is the substrate-agnostic execution model: it drives goals through an
:class:`~python_kl1.core.engine.Engine`, so a different backend (threaded, asyncio)
can host the same clauses unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

from python_kl1.core.logicvar import Var, deref, unify
from python_kl1.core.terms import Cons, Nil, Struct

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from python_kl1.core.engine import Describe, Engine, Goal
    from python_kl1.core.terms import Value


type Body = Callable[[Engine], None]
"""A clause body: given the engine, it binds results and spawns sub-goals."""

type Clause = Callable[..., ClauseResult]
"""A guarded clause: given the goal's arguments, it returns a verdict."""

type Compute = Callable[..., Value]
"""The function :func:`bind_from` applies: one parameter per input, given its bound value."""


class NoMatchingClauseError(Exception):
    """Raised when a goal can neither commit to nor suspend on any clause."""


class _Fail:
    """The 'clause does not apply' verdict. Use the singleton via :func:`fail`."""

    __slots__ = ()


FAIL = _Fail()


@dataclass(frozen=True, slots=True)
class Suspend:
    """Verdict: undecidable until one of ``variables`` becomes bound."""

    variables: tuple[Var, ...]


@dataclass(frozen=True, slots=True)
class Commit:
    """Verdict: this clause is chosen; run ``body(engine)``."""

    body: Body


type ClauseResult = _Fail | Suspend | Commit


def fail() -> _Fail:
    """Verdict constructor: this clause does not apply."""
    return FAIL


def suspend(*variables: Var) -> Suspend:
    """Verdict constructor: retry the goal when one of ``variables`` binds."""
    return Suspend(variables)


def commit(body: Body) -> Commit:
    """Verdict constructor: commit to this clause and run ``body``."""
    return Commit(body)


class Predicate:
    """An ordered set of guarded clauses sharing a name."""

    __slots__ = ('_otherwise_at', 'clauses', 'name')

    def __init__(self, name: str) -> None:
        """Create an empty predicate named ``name``."""
        self.name = name
        self.clauses: list[Clause] = []
        self._otherwise_at: set[int] = set()

    def clause(self, fn: Clause) -> Clause:
        """Register ``fn`` as the next clause (decorator). Returns it unchanged."""
        self.clauses.append(fn)
        return fn

    def otherwise(self, fn: Clause) -> Clause:
        """Register ``fn`` as the first clause after KL1's ``otherwise.`` (decorator).

        It and the clauses after it are tried only once every earlier clause has failed; if
        one suspended instead, the goal waits for that input. Returns ``fn`` unchanged.
        """
        self._otherwise_at.add(len(self.clauses))
        return self.clause(fn)

    def __repr__(self) -> str:
        """Show the name and clause count."""
        return f'Predicate({self.name!r}, {len(self.clauses)} clauses)'


def call(engine: Engine, predicate: Predicate, *args: Value) -> None:
    """Spawn a goal that reduces ``predicate(*args)`` under committed choice."""
    engine.spawn(partial(_reduce, engine, predicate, args))


def _reduce(engine: Engine, predicate: Predicate, args: tuple[Value, ...]) -> None:
    """Try each clause in order; commit to the first, or suspend on what the others awaited.

    The retry is a fresh ``partial`` rather than a closure over itself: a goal that refers to
    itself is a reference cycle, which only CPython's cycle collector can free, whereas this
    way a finished goal -- and every term it held -- is freed by reference counting.
    """
    waiting: list[Var] = []
    for index, clause in enumerate(predicate.clauses):
        if waiting and index in predicate._otherwise_at:
            break  # an otherwise clause waits until everything above it has failed
        verdict = clause(*args)
        if isinstance(verdict, Commit):
            verdict.body(engine)
            return
        if isinstance(verdict, Suspend):
            waiting.extend(verdict.variables)
        # _Fail: fall through to the next clause.
    if not waiting:
        raise NoMatchingClauseError(f'{predicate.name}{args!r}')
    retry_when_any_bound(
        engine, waiting, partial(_reduce, engine, predicate, args), partial(_describe_goal, predicate.name, args)
    )


def bind_from(engine: Engine, inputs: Sequence[Value], fn: Compute, out: Value) -> None:
    """Bind ``out = fn(*inputs)`` once every input is bound -- a dataflow arithmetic goal.

    This is how KL1's ``:=`` (arithmetic assignment) is modelled: the body of a clause
    spawns a small goal that suspends until its operands are available.
    """
    engine.spawn(partial(_attempt, engine, inputs, fn, out))


def _attempt(engine: Engine, inputs: Sequence[Value], fn: Compute, out: Value) -> None:
    """Bind ``out`` if every input is bound, else retry when one binds (a ``partial``, not a cycle)."""
    values = [deref(item) for item in inputs]
    pending = [value for value in values if isinstance(value, Var)]
    if pending:
        retry_when_any_bound(
            engine, pending, partial(_attempt, engine, inputs, fn, out), partial(_describe_bind, out, pending)
        )
    else:
        unify(out, fn(*values))


def retry_when_any_bound(engine: Engine, variables: Sequence[Var], retry: Goal, describe: Describe) -> None:
    """Run ``retry`` once, the first time any of ``variables`` becomes bound.

    Until then the goal is blocked on ``engine`` under ``describe``, so a deadlock report
    can name it.

    Prototype note: waiters from an earlier suspension round are not cancelled. That is
    harmless for goals that suspend on a single variable per round (all current
    examples), but a fuller engine would cancel stale waiters on re-suspension.
    """
    wake = _Wake(engine, retry, describe)
    engine.block(describe)
    for variable in variables:
        engine.when_bound(variable, wake)


class _Wake:
    """The waiter :func:`retry_when_any_bound` parks on each variable: it retries once.

    One slotted object rather than a closure, which would be a function plus a cell per
    captured name: every suspended goal keeps its waiter alive, and the fewer objects those
    are, the less each cycle-collector pass has to traverse.
    """

    __slots__ = ('describe', 'engine', 'fired', 'retry')

    def __init__(self, engine: Engine, retry: Goal, describe: Describe) -> None:
        """Arm a waiter that unblocks ``describe`` on ``engine`` and runs ``retry``."""
        self.engine = engine
        self.retry = retry
        self.describe = describe
        self.fired = False

    def __call__(self) -> None:
        """Retry the goal, unless an earlier waiter of the same suspension already has."""
        if not self.fired:
            self.fired = True
            self.engine.unblock(self.describe)
            self.retry()


_SHOWN_ITEMS = 5
"""How many list elements :func:`show` renders before eliding the rest."""

_SHOWN_DEPTH = 3
"""How deep :func:`show` descends into nested lists and structs."""

_SHOWN_WIDTH = 60
"""The longest text :func:`show` returns."""


def show(value: Value) -> str:
    """Render ``value`` briefly for a report: bounded in length, depth and list items.

    An unbound variable shows as ``_xxxxxx``, the identity its ``repr`` uses, so the same
    variable can be recognised across the goals that share it.
    """
    text = _show(value, _SHOWN_DEPTH)
    return text if len(text) <= _SHOWN_WIDTH else f'{text[: _SHOWN_WIDTH - 3]}...'


def _show(value: Value, depth: int) -> str:
    value = deref(value)
    if isinstance(value, Var):
        return value.label
    if isinstance(value, Nil):
        return '[]'
    if depth == 0 and isinstance(value, Cons | Struct):
        return '...'
    if isinstance(value, Cons):
        items: list[str] = []
        while isinstance(value, Cons) and len(items) < _SHOWN_ITEMS:  # a loop: streams can be long
            items.append(_show(value.head, depth - 1))
            value = deref(value.tail)
        if isinstance(value, Cons):
            rest = '|...'
        elif isinstance(value, Nil):
            rest = ''
        else:
            rest = f'|{_show(value, depth - 1)}'
        return f'[{", ".join(items)}{rest}]'
    if isinstance(value, Struct):
        return f'{value.name}({", ".join(_show(arg, depth - 1) for arg in value.args)})'
    return repr(value)


def _describe_goal(name: str, args: Sequence[Value]) -> str:
    """Describe the goal ``name(*args)`` for a report, each argument through :func:`show`."""
    return f'{name}({", ".join(show(arg) for arg in args)})'


def _describe_bind(out: Value, pending: Sequence[Var]) -> str:
    """Describe a :func:`bind_from` goal waiting on ``pending`` to bind ``out``."""
    return f'{show(out)} := ... (waiting for {", ".join(show(var) for var in pending)})'
