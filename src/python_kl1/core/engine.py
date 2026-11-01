"""A minimal cooperative scheduler -- the prototype runtime substrate.

Goals run by *interleaving* on a single thread (the book's "simulation of
parallelism by interleaving", section 3.11): a FIFO queue of runnable thunks,
drained until quiescence. This keeps :mod:`python_kl1.core.logicvar` and
:mod:`python_kl1.core.stream` substrate-agnostic -- a threaded or asyncio engine
can replace this later without touching them.

A *goal* (:data:`Goal`) is a zero-argument callable. Running it may bind variables
(waking other goals) and :meth:`spawn` further goals. A goal that must wait for data
registers with :meth:`when_bound` instead of blocking.

A goal suspended on data also *blocks* itself (:meth:`Engine.block`) until it wakes, so at
quiescence :attr:`Engine.blocked` names the goals waiting on data nothing produced -- a
deadlock, which :meth:`Engine.run` reports as :class:`DeadlockError` when asked to check.
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

type Describe = Callable[[], str]
"""A lazy description of a blocked goal, formatted only when a report asks for it."""

_REPORTED = 10
"""How many blocked goals a :class:`DeadlockError` message lists before summarising."""


class DeadlockError(Exception):
    """Raised when the engine reaches quiescence with goals still waiting for data."""

    def __init__(self, blocked: tuple[str, ...]) -> None:
        """Record the descriptions of the ``blocked`` goals, listing the first few."""
        listed = '; '.join(blocked[:_REPORTED])
        more = f'; ... and {len(blocked) - _REPORTED} more' if len(blocked) > _REPORTED else ''
        super().__init__(f'{len(blocked)} goal(s) blocked at quiescence: {listed}{more}')
        self.blocked = blocked

    def __reduce__(self) -> tuple[type[DeadlockError], tuple[tuple[str, ...]]]:
        """Pickle from ``blocked``, not the message: unpickling calls ``__init__`` again."""
        return type(self), (self.blocked,)


class Engine:
    """A deterministic FIFO run-queue of runnable goals."""

    __slots__ = ('_blocked', '_queue')

    def __init__(self) -> None:
        """Create an engine with an empty run-queue and no blocked goals."""
        self._queue: deque[Goal] = deque()
        self._blocked: dict[Describe, None] = {}  # insertion-ordered, so reports are stable

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

    def block(self, describe: Describe) -> None:
        """Record a goal as waiting for data, until :meth:`unblock` gets the same ``describe``."""
        self._blocked[describe] = None

    def unblock(self, describe: Describe) -> None:
        """Forget a goal recorded by :meth:`block` -- it has woken."""
        del self._blocked[describe]

    @property
    def blocked(self) -> tuple[str, ...]:
        """Describe the goals still waiting for data, oldest first.

        At quiescence a non-empty answer means deadlock: nothing left to run can bind
        what these goals wait on.
        """
        return tuple(describe() for describe in self._blocked)

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

    def run(self, *, check: bool = False) -> None:
        """Run goals until the queue drains (quiescence).

        With ``check``, raise :class:`DeadlockError` if goals are still blocked then.
        """
        while self.step():
            pass
        if check and self._blocked:
            raise DeadlockError(self.blocked)

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
