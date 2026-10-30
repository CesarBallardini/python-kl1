"""KL1-style clause DSL -- syntactic sugar over the committed-choice goal layer.

A relation is a :class:`Relation` subclass; its clauses are methods marked with
:func:`clause`, reading like their ``.kl1`` source::

    class Factorial(Relation):
        @clause                       # fact(1, R) :- R = 1.
        def base(self, n, r):
            guard(n == 1)
            tell(r, 1)

        @clause                       # fact(N,R) :- N>1 | fact(N-1,R1), R := R1*N.
        def step(self, n, r):
            guard(n > 1)
            r1 = fresh()
            self(n - 1, r1)           # recurse: spawn a sub-goal
            tell(r, r1 * n)

    factorial = Factorial()
    factorial(5)                      # 120

Clause arguments arrive as :class:`Term` objects whose operators build logic
expressions (``n - 1``, ``r1 * n``) and guards (``n == 1``, ``n > 1``):

- ``guard(cond)`` tests a guard: it **suspends** the goal if ``cond``'s inputs are
  still unbound, and **fails** the clause if ``cond`` is false;
- ``tell(target, expr)`` is KL1's ``=`` / ``:=`` -- it binds ``target``, first
  waiting for any unbound variables in ``expr``;
- ``fresh()`` makes a new logic variable (as a Term, so it composes with operators);
- ``uncons`` / ``empty`` are the list head patterns ``[H|T]`` / ``[]``; ``cons`` /
  ``nil`` construct list cells for ``tell``;
- ``merge(*streams)`` is KL1's many-to-one ``merge``: a fair fan-in of several streams
  into one (``tell(out, merge(xs, ys))`` binds an output to it);
- calling ``self`` (or another relation) inside a body spawns a concurrent sub-goal;
- calling a relation ``rel(*inputs)`` at top level runs it and returns the bound result;
  inside a :func:`session` it spawns lazily instead (you pass and read the output vars).

The first clause whose guards pass **commits** (committed choice, no backtracking);
its body then runs. If none commits but some suspended, the goal is retried when any
awaited variable binds. This is sugar only -- it drives the same
:class:`~python_kl1.core.engine.Engine` as the raw goal layer.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, ClassVar

from python_kl1.core.engine import Engine
from python_kl1.core.goal import NoMatchingClauseError, bind_from, retry_when_any_bound
from python_kl1.core.logicvar import Var, deref, unify
from python_kl1.core.stream import merge_streams
from python_kl1.core.terms import NIL, Cons, Struct

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from python_kl1.core.terms import Value


type Operand = Term | Value
"""What a clause may combine or bind: a DSL :class:`Term` or a raw logic value."""


# --- expression / guard term algebra ---------------------------------------


@dataclass(frozen=True, slots=True)
class _Const:
    """A constant leaf (a logic value)."""

    value: Value


@dataclass(frozen=True, slots=True)
class _Ref:
    """A logic-variable leaf."""

    var: Var


@dataclass(frozen=True, slots=True)
class _Op:
    """An arithmetic node: ``op`` applied to two sub-terms."""

    op: str
    left: Term
    right: Term


type _Node = _Const | _Ref | _Op


def _arith(op: str, left: Value, right: Value) -> Value:
    """Evaluate an arithmetic node over two resolved values (numbers only)."""
    if not isinstance(left, int | float) or not isinstance(right, int | float):
        raise TypeError(f'arithmetic {op!r} needs numbers, got {left!r} and {right!r}')
    if op == '+':
        return left + right
    if op == '-':
        return left - right
    if op == '*':
        return left * right
    if op == 'mod':
        return left % right
    return left // right


def _compare(op: str, left: Value, right: Value) -> bool:
    """Evaluate a guard comparison over two resolved values."""
    if op == '==':
        return left == right
    if op == '!=':
        return left != right
    if not isinstance(left, int | float) or not isinstance(right, int | float):
        raise TypeError(f'comparison {op!r} needs numbers, got {left!r} and {right!r}')
    if op == '<':
        return left < right
    if op == '<=':
        return left <= right
    if op == '>':
        return left > right
    return left >= right


class Term:
    """A clause-DSL term: a variable, constant, or arithmetic expression over them.

    Arithmetic operators build larger terms; comparison operators build guards
    (:class:`Cond`). Terms are evaluated lazily -- only when a guard is checked or a
    ``tell`` fires, and only once their variable leaves are bound.
    """

    __slots__ = ('_node',)

    def __init__(self, node: _Node) -> None:
        """Wrap an internal expression ``node``."""
        self._node = node

    def __add__(self, other: Operand) -> Term:
        return _op('+', self, other)

    def __radd__(self, other: Operand) -> Term:
        return _op('+', other, self)

    def __sub__(self, other: Operand) -> Term:
        return _op('-', self, other)

    def __rsub__(self, other: Operand) -> Term:
        return _op('-', other, self)

    def __mul__(self, other: Operand) -> Term:
        return _op('*', self, other)

    def __rmul__(self, other: Operand) -> Term:
        return _op('*', other, self)

    def __mod__(self, other: Operand) -> Term:
        return _op('mod', self, other)

    def __rmod__(self, other: Operand) -> Term:
        return _op('mod', other, self)

    def __floordiv__(self, other: Operand) -> Term:
        return _op('//', self, other)

    def __rfloordiv__(self, other: Operand) -> Term:
        return _op('//', other, self)

    # Comparisons build guards rather than booleans (ORM-style overloading); the
    # __eq__/__ne__ overrides deliberately differ from object's bool signature.
    def __eq__(self, other: Operand) -> Cond:  # type: ignore[override]
        return Cond('==', self, other)

    def __ne__(self, other: Operand) -> Cond:  # type: ignore[override]
        return Cond('!=', self, other)

    def __lt__(self, other: Operand) -> Cond:
        return Cond('<', self, other)

    def __le__(self, other: Operand) -> Cond:
        return Cond('<=', self, other)

    def __gt__(self, other: Operand) -> Cond:
        return Cond('>', self, other)

    def __ge__(self, other: Operand) -> Cond:
        return Cond('>=', self, other)

    # Defining __eq__ already makes Term unhashable (Python sets __hash__ = None),
    # which is what we want -- terms are transient and never used as keys.

    def __repr__(self) -> str:
        return f'Term({self._node!r})'


class _Pending:
    """Marker: a guard cannot be decided until these variables bind."""

    __slots__ = ('variables',)

    def __init__(self, variables: list[Var]) -> None:
        """Record the variables the guard is waiting on."""
        self.variables = variables


class Cond:
    """A guard: a comparison between two terms, checkable to true/false/pending."""

    __slots__ = ('left', 'op', 'right')

    def __init__(self, op: str, left: Operand, right: Operand) -> None:
        """Build a comparison ``left op right`` (operands are wrapped into Terms)."""
        self.op = op
        self.left = _wrap(left)
        self.right = _wrap(right)

    def check(self) -> _Pending | bool:
        """Evaluate the guard, or report which variables it is still waiting on."""
        pending = _pending_vars(self.left) + _pending_vars(self.right)
        if pending:
            return _Pending(pending)
        return _compare(self.op, _value(self.left), _value(self.right))

    def __repr__(self) -> str:
        return f'Cond({self.op!r}, {self.left!r}, {self.right!r})'


def _op(op: str, left: Operand, right: Operand) -> Term:
    return Term(_Op(op, _wrap(left), _wrap(right)))


def _wrap(value: Operand) -> Term:
    if isinstance(value, Term):
        return value
    if isinstance(value, Var):
        return Term(_Ref(value))
    return Term(_Const(value))


def _pending_vars(term: Term) -> list[Var]:
    node = term._node
    if isinstance(node, _Const):
        return []
    if isinstance(node, _Ref):
        current = deref(node.var)
        return [current] if isinstance(current, Var) else []
    return _pending_vars(node.left) + _pending_vars(node.right)


def _value(term: Term) -> Value:
    node = term._node
    if isinstance(node, _Const):
        return node.value
    if isinstance(node, _Ref):
        return deref(node.var)
    return _arith(node.op, _value(node.left), _value(node.right))


def _root_var(term: Term) -> Var:
    node = term._node
    if isinstance(node, _Ref):
        return node.var
    raise TypeError(f'tell target must be a variable, not {term!r}')


def _resolve(term: Term) -> Value:
    """Dereference a term to its current concrete value (a Var if still unbound)."""
    node = term._node
    if isinstance(node, _Ref):
        return deref(node.var)
    if isinstance(node, _Const):
        return node.value
    return _value(term)


def _as_value(term_or_value: Operand) -> Value:
    """The underlying logic object of a term (its Var or value), for building cells."""
    if isinstance(term_or_value, Term):
        node = term_or_value._node
        if isinstance(node, _Ref):
            return node.var
        if isinstance(node, _Const):
            return node.value
        return _value(term_or_value)
    return term_or_value


# --- clause body vocabulary -------------------------------------------------


# These are control-flow signals, not errors, so the N818 'Error' suffix would misname them.
class _ClauseFail(Exception):  # noqa: N818
    """Internal: raised by a failed guard to reject the current clause."""


class _ClauseSuspend(Exception):  # noqa: N818
    """Internal: raised by an undecidable guard to suspend the goal."""

    def __init__(self, variables: list[Var]) -> None:
        """Record the variables to wake on."""
        super().__init__()
        self.variables = variables


_ENGINE_STACK: list[Engine] = []


def _engine() -> Engine:
    if not _ENGINE_STACK:
        raise RuntimeError('DSL body used outside a running clause')
    return _ENGINE_STACK[-1]


def fresh() -> Term:
    """Create a fresh logic variable as a Term (so it composes with operators)."""
    return Term(_Ref(Var()))


def guard(condition: Cond | bool) -> None:
    """Assert a guard: fail the clause if false, suspend the goal if undecidable."""
    if isinstance(condition, bool):
        if not condition:
            raise _ClauseFail
        return
    outcome = condition.check()
    if isinstance(outcome, _Pending):
        raise _ClauseSuspend(outcome.variables)
    if not outcome:
        raise _ClauseFail


def tell(target: Term, expr: Operand) -> None:
    """Bind ``target`` to ``expr`` (KL1 ``=`` / ``:=``), waiting for its unbound vars."""
    engine = _engine()
    term = _wrap(expr)
    out = _root_var(target)
    pending = _pending_vars(term)
    if pending:
        bind_from(engine, pending, lambda *_: _value(term), out)
    else:
        unify(out, _value(term))


def uncons(term: Term) -> tuple[Term, Term]:
    """Head pattern ``[Head|Tail]``.

    Returns ``(head, tail)`` if ``term`` is a cons cell; **suspends** the goal if it is
    still unbound; **fails** the clause if it is anything else (e.g. the empty list).
    """
    value = _resolve(term)
    if isinstance(value, Var):
        raise _ClauseSuspend([value])
    if isinstance(value, Cons):
        return _wrap(value.head), _wrap(value.tail)
    raise _ClauseFail


def empty(term: Term) -> None:
    """Head pattern ``[]``.

    Succeeds if ``term`` is the empty list; **suspends** the goal if it is still unbound;
    **fails** the clause otherwise (e.g. a cons cell).
    """
    value = _resolve(term)
    if isinstance(value, Var):
        raise _ClauseSuspend([value])
    if value is NIL:
        return
    raise _ClauseFail


def cons(head: Operand, tail: Operand) -> Term:
    """Construct the list cell ``[head | tail]`` as a term (for use in :func:`tell`)."""
    return Term(_Const(Cons(_as_value(head), _as_value(tail))))


def nil() -> Term:
    """The empty list ``[]`` as a term (for use in :func:`tell`)."""
    return Term(_Const(NIL))


def struct(name: str, *args: Operand) -> Term:
    """Construct a compound term ``name(*args)`` -- a functor -- for use in :func:`tell`.

    For example ``struct('deposit', 100)`` builds the message ``deposit(100)``; a
    reply variable rides along as ``struct('balance', fresh())``.
    """
    return Term(_Const(Struct(name, tuple(_as_value(arg) for arg in args))))


def unstruct(term: Term, name: str, arity: int) -> tuple[Term, ...]:
    """Head pattern ``name(A1, ..., A_arity)`` -- destructure a functor.

    Returns the argument terms if ``term`` is the functor ``name`` of ``arity`` args;
    **suspends** the goal if ``term`` is still unbound; **fails** the clause otherwise
    (wrong name, arity, or type)::

        (amount,) = unstruct(msg, 'deposit', 1)
    """
    value = _resolve(term)
    if isinstance(value, Var):
        raise _ClauseSuspend([value])
    if isinstance(value, Struct) and value.name == name and len(value.args) == arity:
        return tuple(_wrap(arg) for arg in value.args)
    raise _ClauseFail


def merge(*streams: Operand) -> Term:
    """Fair many-to-one merge of ``streams`` -- KLIC's ``generic:new(merge, In, Out)``.

    Returns the merged stream as a term: pass it straight to a consumer, or bind an
    output argument to it with ``tell(out, merge(xs, ys))``. Elements are forwarded as
    they arrive on any input (fairly, never in a fixed order) and the result closes once
    every input has closed. To give a new client its own input into a running merge --
    KLIC's ``In = {In1, In2}`` split -- nest: ``tell(ins, merge(in1, in2))``.
    """
    return _wrap(merge_streams(_engine(), *(_as_value(stream) for stream in streams)))


class _ClauseMethod:
    """Marker wrapping a method flagged as a clause; unwrapped at subclass creation."""

    __slots__ = ('fn',)

    def __init__(self, fn: Callable[..., None]) -> None:
        """Hold the underlying clause method ``fn``."""
        self.fn = fn


def clause(method: Callable[..., None]) -> _ClauseMethod:
    """Mark a :class:`Relation` method as a clause (decorator).

    Clauses are collected, in definition order, when the subclass is created; the first
    whose guards pass commits.
    """
    return _ClauseMethod(method)


class Relation:
    """Base class for a KL1 relation: subclass it and mark clauses with :func:`clause`.

    The clauses are methods; calling an instance runs the relation as a query::

        class Factorial(Relation):
            @clause
            def base(self, n, r):
                guard(n == 1)
                tell(r, 1)

            @clause
            def step(self, n, r):
                guard(n > 1)
                r1 = fresh()
                self(n - 1, r1)     # recurse: spawn a sub-goal
                tell(r, r1 * n)

        factorial = Factorial()
        factorial(5)                # 120
    """

    _clause_methods: ClassVar[tuple[Callable[..., None], ...]] = ()

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Collect the subclass's :func:`clause`-marked methods, in definition order."""
        super().__init_subclass__(**kwargs)
        methods: list[Callable[..., None]] = []
        for name, value in list(vars(cls).items()):
            if isinstance(value, _ClauseMethod):
                setattr(cls, name, value.fn)  # unwrap: leave a normal method on the class
                methods.append(value.fn)
        cls._clause_methods = tuple(methods)

    def __init__(self) -> None:
        """Bind this instance's clauses (each becomes a callable taking the goal args)."""
        self.name: str = type(self).__name__
        self._clauses: list[Callable[..., None]] = [partial(method, self) for method in self._clause_methods]

    def __call__(self, *args: Operand) -> Value | None:
        """Query a relation, or spawn a sub-goal.

        Outside a :func:`session` (and outside a clause body), ``rel(*inputs)`` is the
        **eager** query: it makes an engine, appends a fresh output variable, runs to
        quiescence, and returns its value -- an atom, or a stream (a chain of cons cells;
        use :func:`~python_kl1.core.stream.to_list` to materialise it).

        Inside a :func:`session` or a clause body -- where an engine is already on the
        stack -- ``rel(*args)`` instead **spawns** a goal with exactly the arguments given
        (you pass the output variables) and returns ``None``; the results are futures you
        read with ``deref`` once you drive the engine.
        """
        if _ENGINE_STACK:
            call(_engine(), self, *args)
            return None
        engine = Engine()
        result = Var()
        call(engine, self, *args, result)
        engine.run()
        return deref(result)

    def __repr__(self) -> str:
        return f'{type(self).__name__}({len(self._clauses)} clauses)'


def call(engine: Engine, relation: Relation, *args: Operand) -> None:
    """Spawn a goal reducing ``relation(*args)`` under committed choice."""
    wrapped = [_wrap(arg) for arg in args]
    engine.spawn(partial(_reduce, engine, relation, args, wrapped))


def _reduce(engine: Engine, relation: Relation, args: tuple[Operand, ...], wrapped: list[Term]) -> None:
    """Try each clause in order; commit to the first, or suspend on what the others awaited.

    The retry is a fresh ``partial`` rather than a closure over itself: a goal that refers to
    itself is a reference cycle, which only CPython's cycle collector can free, whereas this
    way a finished goal -- and every term it held -- is freed by reference counting.
    """
    waiting: list[Var] = []
    for clause in relation._clauses:
        _ENGINE_STACK.append(engine)
        try:
            clause(*wrapped)
        except _ClauseFail:
            continue
        except _ClauseSuspend as suspended:
            waiting.extend(suspended.variables)
            continue
        finally:
            _ENGINE_STACK.pop()
        return  # committed -- the body has already run
    if not waiting:
        raise NoMatchingClauseError(f'{relation.name}{args!r}')
    retry_when_any_bound(engine, waiting, partial(_reduce, engine, relation, args, wrapped))


@contextmanager
def session() -> Iterator[Engine]:
    """Open a lazy KL1 session, yielding the engine that backs it.

    Inside the ``with`` block, calling a relation ``rel(*args)`` **spawns** it on the
    session's engine with exactly the arguments given (you create and pass the output
    variables yourself) and returns ``None`` -- so results are *futures*: logic variables
    you read with ``deref`` once you drive the engine. Nothing runs until you demand it,
    which makes it uniform (everything is a ``Var``), composable (thread an unresolved
    variable into further goals) and safe for unbounded streams::

        with session() as engine:
            r = Var()
            factorial(5, r)                 # spawn -- r is a future
            engine.run()                    # (or step / drain) drive the computation
            deref(r)                        # 120

    Outside a session, ``rel(*inputs)`` is instead the eager query (runs to quiescence and
    returns the value).
    """
    engine = Engine()
    _ENGINE_STACK.append(engine)
    try:
        yield engine
    finally:
        _ENGINE_STACK.pop()
