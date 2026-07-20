"""A minimal cooperative scheduler -- the prototype runtime substrate.

Goals run by *interleaving* on a single thread (the book's "simulation of
parallelism by interleaving", section 3.11): a FIFO queue of runnable thunks,
drained until quiescence. This keeps :mod:`python_kl1.core.logicvar` and
:mod:`python_kl1.core.stream` substrate-agnostic -- a threaded or asyncio engine
can replace this later without touching them.

A *goal* (:data:`Goal`) is a zero-argument callable. Running it may bind variables
(waking other goals) and :meth:`spawn` further goals. A goal that must wait for data
registers with :meth:`when_bound` instead of blocking.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from python_kl1.core.logicvar import Var, deref

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from python_kl1.core.terms import Value


type Goal = Callable[[], None]
"""A runnable unit of work: a zero-argument callable scheduled on the engine."""


class Engine:
    """A deterministic FIFO run-queue of runnable goals."""

    __slots__ = ('_queue',)

    def __init__(self) -> None:
        """Create an engine with an empty run-queue."""
        self._queue: deque[Goal] = deque()

    def spawn(self, goal: Goal) -> None:
        """Enqueue ``goal`` to run on a future turn."""
        self._queue.append(goal)

    def when_bound(self, term: Value, cont: Goal) -> None:
        """Schedule ``cont`` once ``term`` is bound; suspend on it until then.

        If ``term`` is already bound, ``cont`` is enqueued immediately; otherwise
        a waiter is parked on the variable and enqueues ``cont`` when it binds.
        Either way ``cont`` runs via the queue, never inline, so binding stays a
        cheap enqueue and goals interleave fairly.
        """
        target = deref(term)
        if isinstance(target, Var):
            target.waiters.append(lambda: self.spawn(cont))
        else:
            self.spawn(cont)

    def step(self) -> bool:
        """Run a single goal. Return ``True`` if one ran, ``False`` if the queue was empty.

        This is the hook that lets a stream be consumed as a native Python
        iterator (see :func:`python_kl1.core.stream.drain`): a caller can pump the
        engine one goal at a time and interleave its own code between turns.
        """
        if not self._queue:
            return False
        self._queue.popleft()()
        return True

    def run(self) -> None:
        """Run goals until the queue drains (quiescence)."""
        while self.step():
            pass

    def __enter__(self) -> Engine:
        """Enter an engine scope; spawn goals inside the ``with`` block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Run queued goals to quiescence on a clean exit (skipped if the block raised)."""
        if exc_type is None:
            self.run()
