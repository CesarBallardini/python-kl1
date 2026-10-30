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

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from python_kl1.core.engine import Engine, Goal
    from python_kl1.core.terms import Value


type Body = Callable[[Engine], None]
"""A clause body: given the engine, it binds results and spawns sub-goals."""

type Clause = Callable[..., ClauseResult]
"""A guarded clause: given the goal's arguments, it returns a verdict."""


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

    __slots__ = ('clauses', 'name')

    def __init__(self, name: str) -> None:
        """Create an empty predicate named ``name``."""
        self.name = name
        self.clauses: list[Clause] = []

    def clause(self, fn: Clause) -> Clause:
        """Register ``fn`` as the next clause (decorator). Returns it unchanged."""
        self.clauses.append(fn)
        return fn

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
    for clause in predicate.clauses:
        verdict = clause(*args)
        if isinstance(verdict, Commit):
            verdict.body(engine)
            return
        if isinstance(verdict, Suspend):
            waiting.extend(verdict.variables)
        # _Fail: fall through to the next clause.
    if not waiting:
        raise NoMatchingClauseError(f'{predicate.name}{args!r}')
    retry_when_any_bound(engine, waiting, partial(_reduce, engine, predicate, args))


def bind_from(engine: Engine, inputs: Sequence[Value], fn: Callable[..., Value], out: Value) -> None:
    """Bind ``out = fn(*inputs)`` once every input is bound -- a dataflow arithmetic goal.

    This is how KL1's ``:=`` (arithmetic assignment) is modelled: the body of a clause
    spawns a small goal that suspends until its operands are available.
    """
    engine.spawn(partial(_attempt, engine, inputs, fn, out))


def _attempt(engine: Engine, inputs: Sequence[Value], fn: Callable[..., Value], out: Value) -> None:
    """Bind ``out`` if every input is bound, else retry when one binds (a ``partial``, not a cycle)."""
    values = [deref(item) for item in inputs]
    pending = [value for value in values if isinstance(value, Var)]
    if pending:
        retry_when_any_bound(engine, pending, partial(_attempt, engine, inputs, fn, out))
    else:
        unify(out, fn(*values))


def retry_when_any_bound(engine: Engine, variables: Sequence[Var], retry: Goal) -> None:
    """Run ``retry`` once, the first time any of ``variables`` becomes bound.

    Prototype note: waiters from an earlier suspension round are not cancelled. That is
    harmless for goals that suspend on a single variable per round (all current
    examples), but a fuller engine would cancel stale waiters on re-suspension.
    """
    fired = False

    def wake() -> None:
        nonlocal fired
        if not fired:
            fired = True
            retry()

    for variable in variables:
        engine.when_bound(variable, wake)
