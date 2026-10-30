"""Unit tests for the KL1-style clause DSL (class-based relations)."""

import gc

import pytest

from python_kl1.core import (
    NIL,
    Cons,
    Engine,
    NoMatchingClauseError,
    Struct,
    Var,
    deref,
    drain,
    is_bound,
    merge_streams,
    stream_from,
    to_list,
    unify,
)
from python_kl1.dsl import (
    Relation,
    Term,
    call,
    clause,
    cons,
    empty,
    fresh,
    guard,
    merge,
    nil,
    otherwise,
    session,
    struct,
    tell,
    uncons,
    unstruct,
)


class _Not(Relation):
    @clause
    def zero(self, x: Term, r: Term) -> None:
        guard(x == 0)
        tell(r, 1)

    @clause
    def one(self, x: Term, r: Term) -> None:
        guard(x == 1)
        tell(r, 0)


class _Factorial(Relation):
    @clause
    def base(self, n: Term, r: Term) -> None:
        guard(n == 1)
        tell(r, 1)

    @clause
    def step(self, n: Term, r: Term) -> None:
        guard(n > 1)
        r1 = fresh()
        self(n - 1, r1)
        tell(r, r1 * n)


class _Copy(Relation):
    @clause
    def end(self, src: Term, dst: Term) -> None:
        empty(src)
        tell(dst, nil())

    @clause
    def step(self, src: Term, dst: Term) -> None:
        head, tail = uncons(src)
        rest = fresh()
        tell(dst, cons(head, rest))
        self(tail, rest)


class _Filter(Relation):
    @clause
    def at_end(self, p: Term, ins: Term, fs: Term) -> None:
        empty(ins)
        tell(fs, nil())

    @clause
    def keep(self, p: Term, ins: Term, fs: Term) -> None:
        n, ns = uncons(ins)
        guard(n % p != 0)
        f1s = fresh()
        tell(fs, cons(n, f1s))
        self(p, ns, f1s)

    @clause
    def drop(self, p: Term, ins: Term, fs: Term) -> None:
        n, ns = uncons(ins)
        guard(n % p == 0)
        self(p, ns, fs)


_FILTER = _Filter()


class _Sieve(Relation):
    @clause
    def at_end(self, ins: Term, ps: Term) -> None:
        empty(ins)
        tell(ps, nil())

    @clause
    def prime(self, ins: Term, ps: Term) -> None:
        p, ns = uncons(ins)
        p1s = fresh()
        tell(ps, cons(p, p1s))
        fs = fresh()
        _FILTER(p, ns, fs)
        self(fs, p1s)


@pytest.mark.unit
def test_committed_choice_picks_the_matching_clause() -> None:
    assert _Not()(0) == 1


@pytest.mark.unit
def test_guard_suspends_until_input_is_bound() -> None:
    engine = Engine()
    unknown = Var()
    result = Var()

    call(engine, _Not(), unknown, result)
    engine.run()  # both clauses' guards suspend on `unknown`
    assert not is_bound(result)

    unify(unknown, 1)
    engine.run()  # the goal wakes and commits to the second clause
    assert deref(result) == 0


@pytest.mark.unit
def test_factorial_unwinds_recursion() -> None:
    assert _Factorial()(5) == 120


@pytest.mark.unit
def test_relation_is_callable_as_a_top_level_query() -> None:
    assert _Not()(0) == 1
    assert _Factorial()(5) == 120


@pytest.mark.unit
def test_list_patterns_copy_a_stream() -> None:
    engine = Engine()
    source = stream_from(engine, [1, 2, 3])
    result = Var()

    call(engine, _Copy(), source, result)

    assert list(drain(engine, result)) == [1, 2, 3]


@pytest.mark.unit
def test_sieve_pipeline_produces_primes() -> None:
    engine = Engine()
    numbers = stream_from(engine, range(2, 12))
    result = Var()

    call(engine, _Sieve(), numbers, result)

    assert list(drain(engine, result)) == [2, 3, 5, 7, 11]


@pytest.mark.unit
def test_relation_with_no_matching_clause_raises() -> None:
    class _Empty(Relation):
        pass

    engine = Engine()
    call(engine, _Empty(), Var())

    with pytest.raises(NoMatchingClauseError):
        engine.run()


class _Add(Relation):
    @clause
    def go(self, a: Term, b: Term, r: Term) -> None:
        tell(r, a + b)


class _Poly(Relation):
    @clause
    def go(self, a: Term, r: Term) -> None:
        tell(r, a * 2 + 1)


class _Reflected(Relation):
    @clause
    def go(self, a: Term, r: Term) -> None:
        tell(r, 10 - a)  # reflected __rsub__


class _FloorDiv(Relation):
    @clause
    def go(self, a: Term, r: Term) -> None:
        tell(r, a // 2)


class _Sign(Relation):
    @clause
    def negative(self, n: Term, r: Term) -> None:
        guard(n < 0)
        tell(r, 'neg')

    @clause
    def zero(self, n: Term, r: Term) -> None:
        guard(n == 0)
        tell(r, 'zero')

    @clause
    def positive(self, n: Term, r: Term) -> None:
        guard(n > 0)
        tell(r, 'pos')


class _Head(Relation):
    @clause
    def go(self, xs: Term, r: Term) -> None:
        head, _tail = uncons(xs)
        tell(r, head)


class _Never(Relation):
    @clause
    def go(self, r: Term) -> None:
        guard(False)
        tell(r, 'unreachable')


class _BadTell(Relation):
    @clause
    def go(self, a: Term, r: Term) -> None:
        tell(a + 1, r)  # target is an expression, not a variable


class _AddNonNumbers(Relation):
    @clause
    def go(self, a: Term, r: Term) -> None:
        tell(r, a + a)


@pytest.mark.unit
def test_query_with_multiple_inputs() -> None:
    assert _Add()(3, 4) == 7
    assert _Add()(10, 20) == 30


@pytest.mark.unit
def test_nested_arithmetic_expression() -> None:
    assert _Poly()(5) == 11


@pytest.mark.unit
def test_reflected_subtraction() -> None:
    assert _Reflected()(3) == 7


@pytest.mark.unit
def test_floor_division() -> None:
    assert _FloorDiv()(7) == 3


@pytest.mark.unit
@pytest.mark.parametrize(('value', 'expected'), [(-5, 'neg'), (0, 'zero'), (7, 'pos')])
def test_comparison_guards(value: int, expected: str) -> None:
    assert _Sign()(value) == expected


@pytest.mark.unit
def test_uncons_on_empty_list_fails_the_clause() -> None:
    engine = Engine()
    result = Var()
    call(engine, _Head(), NIL, result)

    with pytest.raises(NoMatchingClauseError):
        engine.run()


@pytest.mark.unit
def test_uncons_suspends_on_an_unbound_stream() -> None:
    engine = Engine()
    stream = Var()
    result = Var()
    call(engine, _Head(), stream, result)
    engine.run()
    assert not is_bound(result)

    unify(stream, Cons(42, Var()))
    engine.run()
    assert deref(result) == 42


@pytest.mark.unit
def test_false_guard_fails_the_clause() -> None:
    engine = Engine()
    result = Var()
    call(engine, _Never(), result)

    with pytest.raises(NoMatchingClauseError):
        engine.run()


@pytest.mark.unit
def test_tell_to_a_non_variable_raises() -> None:
    engine = Engine()
    call(engine, _BadTell(), Var(), Var())

    with pytest.raises(TypeError):
        engine.run()


@pytest.mark.unit
def test_arithmetic_on_non_numbers_raises() -> None:
    engine = Engine()
    call(engine, _AddNonNumbers(), 'x', Var())

    with pytest.raises(TypeError):
        engine.run()


class _Count(Relation):
    """count(N, Xs): Xs is the stream N, N-1, ..., 1."""

    @clause
    def done(self, n: Term, xs: Term) -> None:
        guard(n == 0)
        tell(xs, nil())

    @clause
    def more(self, n: Term, xs: Term) -> None:
        guard(n > 0)
        rest = fresh()
        tell(xs, cons(n, rest))
        self(n - 1, rest)


class _Doubler(Relation):
    @clause
    def go(self, a: Term, r: Term) -> None:
        tell(r, a * 2)


class _DoubleThenIncrement(Relation):
    """Compound relation: uses _Doubler, then adds one."""

    doubler = _Doubler()

    @clause
    def go(self, a: Term, r: Term) -> None:
        doubled = fresh()
        self.doubler(a, doubled)
        tell(r, doubled + 1)


@pytest.mark.unit
def test_calling_returns_a_stream_value() -> None:
    # A stream-producing relation binds its output var to a chain of cons cells.
    with session() as engine:
        result = Var()
        _Count()(3, result)
        engine.run()
        assert to_list(result) == [3, 2, 1]


@pytest.mark.unit
def test_a_woken_reduction_leaves_no_cyclic_garbage() -> None:
    # A goal that retries itself through a closure is a reference cycle, which only the
    # cycle collector can free; with the collector off, nothing may be left for it to find.
    factorial = _Factorial()  # an instance and its bound clauses form a cycle; keep it alive
    n = Var()
    result = Var()
    gc.collect()
    gc.disable()
    try:
        with session() as engine:
            factorial(n, result)
            engine.run()  # suspends on n
            unify(n, 5)
            engine.run()  # wakes; each tell(r, r1 * n) waits on r1
        assert deref(result) == 120
        assert gc.collect() == 0
    finally:
        gc.enable()


@pytest.mark.unit
def test_session_calls_are_lazy_futures() -> None:
    with session() as engine:
        result = Var()
        _Factorial()(5, result)  # spawn -- result is a future
        assert not is_bound(result)  # nothing has run yet

        engine.run()
        assert deref(result) == 120


@pytest.mark.unit
def test_session_supports_lazy_stream_consumption() -> None:
    with session() as engine:
        stream = Var()
        _Count()(5, stream)  # spawn -- stream is a future

        prefix = []
        for value in drain(engine, stream):
            prefix.append(value)
            if len(prefix) == 2:
                break  # take a prefix without materialising the whole stream

    assert prefix == [5, 4]


@pytest.mark.unit
def test_session_composes_relations_via_dataflow() -> None:
    with session() as engine:
        fact = Var()
        doubled = Var()
        _Factorial()(3, fact)  # fact = 3! = 6 (eventually)
        _Doubler()(fact, doubled)  # thread the still-unresolved `fact` into another goal

        engine.run()
        assert deref(doubled) == 12


@pytest.mark.unit
def test_relation_composes_a_sub_relation() -> None:
    assert _DoubleThenIncrement()(5) == 11


class _Box(Relation):
    @clause
    def go(self, a: Term, r: Term) -> None:
        tell(r, struct('box', a))


class _Unbox(Relation):
    @clause
    def go(self, boxed: Term, r: Term) -> None:
        (value,) = unstruct(boxed, 'box', 1)
        tell(r, value)


@pytest.mark.unit
def test_struct_construction_in_a_body() -> None:
    assert _Box()(7) == Struct('box', (7,))


@pytest.mark.unit
def test_unstruct_destructures_a_functor() -> None:
    assert _Unbox()(Struct('box', (42,))) == 42


@pytest.mark.unit
def test_unstruct_fails_the_clause_on_a_wrong_functor() -> None:
    engine = Engine()
    result = Var()
    call(engine, _Unbox(), Struct('other', (1,)), result)

    with pytest.raises(NoMatchingClauseError):
        engine.run()


class _MergeInto(Relation):
    """merge2(Xs, Ys, Zs): Zs is the fair merge of Xs and Ys -- generic:new(merge, {Xs, Ys}, Zs)."""

    @clause
    def go(self, xs: Term, ys: Term, zs: Term) -> None:
        tell(zs, merge(xs, ys))


class _Fork(Relation):
    """A client that splits its merge input in two (KLIC's In = {In1, In2}) and uses both halves."""

    @clause
    def go(self, ins: Term) -> None:
        mine, helper = fresh(), fresh()
        tell(ins, merge(mine, helper))
        tell(mine, cons('me', nil()))
        tell(helper, cons('helper', nil()))


@pytest.mark.unit
def test_merge_in_a_clause_body_binds_an_output_stream() -> None:
    with session() as engine:
        merged = Var()
        _MergeInto()(stream_from(engine, [1, 2]), stream_from(engine, ['a', 'b']), merged)
        engine.run()
        items = to_list(merged)  # a proper list: the merge closed once both inputs ended

    assert len(items) == 4
    assert set(items) == {1, 2, 'a', 'b'}


@pytest.mark.unit
def test_splitting_a_merge_input_admits_a_new_client() -> None:
    # The outer merge sees `client` close only once both halves of the split have closed.
    with session() as engine:
        client, other = Var(), Var()
        shared = merge_streams(engine, client, other)
        _Fork()(client)
        unify(other, Cons('other', NIL))
        engine.run()
        items = to_list(shared)

    assert len(items) == 3
    assert set(items) == {'me', 'helper', 'other'}


class _Classify(Relation):
    @clause
    def zero(self, x: Term, r: Term) -> None:
        guard(x == 0)
        tell(r, 'zero')

    @otherwise
    def other(self, x: Term, r: Term) -> None:
        tell(r, 'other')


class _GuardFreeFallback(Relation):
    """The same relation with a trailing guard-free @clause instead of @otherwise."""

    @clause
    def zero(self, x: Term, r: Term) -> None:
        guard(x == 0)
        tell(r, 'zero')

    @clause
    def other(self, x: Term, r: Term) -> None:
        tell(r, 'other')


class _TwoGroups(Relation):
    """p(X,_,R) :- X =:= 1 | R = a.  otherwise.  p(_,Y,R) :- Y =:= 1 | R = b.
    p(X,_,R) :- X =:= 2 | R = c.  otherwise.  p(_,_,R) :- R = d.
    """

    @clause
    def a(self, x: Term, y: Term, r: Term) -> None:
        guard(x == 1)
        tell(r, 'a')

    @otherwise
    def b(self, x: Term, y: Term, r: Term) -> None:
        guard(y == 1)
        tell(r, 'b')

    @clause
    def c(self, x: Term, y: Term, r: Term) -> None:
        guard(x == 2)
        tell(r, 'c')

    @otherwise
    def d(self, x: Term, y: Term, r: Term) -> None:
        tell(r, 'd')


class _PositiveOnly(Relation):
    @clause
    def zero(self, x: Term, r: Term) -> None:
        guard(x == 0)
        tell(r, 'zero')

    @otherwise
    def positive(self, x: Term, r: Term) -> None:
        guard(x > 0)
        tell(r, 'positive')


@pytest.mark.unit
def test_otherwise_waits_while_an_earlier_clause_is_suspended() -> None:
    with session() as engine:
        x, result = Var(), Var()
        _Classify()(x, result)
        engine.run()
        assert not is_bound(result)  # zero is waiting on x, so the default must not commit

        unify(x, 0)
        engine.run()
        assert deref(result) == 'zero'


@pytest.mark.unit
def test_otherwise_commits_once_every_earlier_clause_has_failed() -> None:
    assert _Classify()(5) == 'other'
    assert _Classify()(0) == 'zero'


@pytest.mark.unit
def test_a_group_member_is_tried_when_the_otherwise_clause_suspends() -> None:
    # x = 2, y unbound: a fails, b (opening the group) waits on y, and c -- in b's group --
    # is still tried and commits, exactly as in KL1.
    with session() as engine:
        y, result = Var(), Var()
        _TwoGroups()(2, y, result)
        engine.run()
        assert deref(result) == 'c'


@pytest.mark.unit
def test_a_second_otherwise_waits_for_the_first_group() -> None:
    with session() as engine:
        y, result = Var(), Var()
        _TwoGroups()(3, y, result)
        engine.run()
        assert not is_bound(result)  # b is waiting on y, so d must not commit

        unify(y, 1)
        engine.run()
        assert deref(result) == 'b'

    assert _TwoGroups()(3, 5) == 'd'


@pytest.mark.unit
def test_otherwise_raises_when_nothing_matches_and_nothing_waits() -> None:
    with pytest.raises(NoMatchingClauseError):
        _PositiveOnly()(-1)


@pytest.mark.unit
def test_a_guard_free_fallback_commits_early_where_otherwise_waits() -> None:
    # The trap @otherwise exists for: a guard-free clause commits while zero still waits.
    with session() as engine:
        x, early, waited = Var(), Var(), Var()
        _GuardFreeFallback()(x, early)
        _Classify()(x, waited)
        engine.run()
        unify(x, 0)
        engine.run()

    assert deref(early) == 'other'
    assert deref(waited) == 'zero'
