"""Unit tests for the committed-choice goal layer."""

import gc

import pytest

from python_kl1.core import (
    Engine,
    NoMatchingClauseError,
    Predicate,
    Value,
    Var,
    bind,
    bind_from,
    call,
    commit,
    deref,
    fail,
    is_bound,
    suspend,
    unify,
)


def _sum(x: Value, y: Value) -> Value:
    assert isinstance(x, int)
    assert isinstance(y, int)
    return x + y


def _make_not() -> Predicate:
    predicate = Predicate('not')

    @predicate.clause
    def _zero(x, r):
        value = deref(x)
        if isinstance(value, Var):
            return suspend(value)
        if value == 0:
            return commit(lambda engine: unify(r, 1))
        return fail()

    @predicate.clause
    def _one(x, r):
        value = deref(x)
        if isinstance(value, Var):
            return suspend(value)
        if value == 1:
            return commit(lambda engine: unify(r, 0))
        return fail()

    return predicate


@pytest.mark.unit
def test_not_commits_when_input_ready() -> None:
    engine = Engine()
    result = Var()

    call(engine, _make_not(), 0, result)
    engine.run()

    assert deref(result) == 1


@pytest.mark.unit
def test_not_suspends_until_input_bound() -> None:
    engine = Engine()
    unknown = Var()
    result = Var()

    call(engine, _make_not(), unknown, result)
    engine.run()  # suspends -- input not yet bound
    assert not is_bound(result)

    unify(unknown, 1)
    engine.run()  # the parked goal wakes and commits
    assert deref(result) == 0


def _make_factorial() -> Predicate:
    factorial = Predicate('factorial')

    @factorial.clause
    def _base(n, r):
        value = deref(n)
        if isinstance(value, Var):
            return suspend(value)
        if value == 1:
            return commit(lambda engine: unify(r, 1))
        return fail()

    @factorial.clause
    def _recur(n, r):
        value = deref(n)
        if isinstance(value, Var):
            return suspend(value)
        if isinstance(value, int) and value > 1:

            def _body(engine: Engine) -> None:
                sub_result = Var()
                call(engine, factorial, value - 1, sub_result)

                def _times(sub: Value) -> Value:
                    assert isinstance(sub, int)
                    return sub * value

                bind_from(engine, [sub_result], _times, r)

            return commit(_body)
        return fail()

    return factorial


@pytest.mark.unit
def test_factorial_unwinds_recursion() -> None:
    engine = Engine()
    result = Var()

    call(engine, _make_factorial(), 5, result)
    engine.run()

    assert deref(result) == 120


@pytest.mark.unit
def test_no_matching_clause_raises() -> None:
    predicate = Predicate('reject')

    @predicate.clause
    def _reject(x):
        return fail()

    engine = Engine()
    call(engine, predicate, 1)

    with pytest.raises(NoMatchingClauseError):
        engine.run()


@pytest.mark.unit
def test_bind_from_waits_for_all_inputs() -> None:
    engine = Engine()
    a = Var()
    b = Var()
    out = Var()

    bind_from(engine, [a, b], _sum, out)
    engine.run()
    assert not is_bound(out)

    bind(a, 3)
    engine.run()
    assert not is_bound(out)  # still waiting on b

    bind(b, 4)
    engine.run()
    assert deref(out) == 7


@pytest.mark.unit
def test_bind_from_with_bound_inputs_fires_immediately() -> None:
    engine = Engine()
    a = Var()
    b = Var()
    out = Var()
    bind(a, 3)
    bind(b, 4)

    bind_from(engine, [a, b], _sum, out)
    engine.run()

    assert deref(out) == 7


@pytest.mark.unit
def test_committed_choice_takes_the_first_matching_clause() -> None:
    predicate = Predicate('pick')

    @predicate.clause
    def _first(r):
        return commit(lambda engine: unify(r, 'first'))

    @predicate.clause
    def _second(r):
        return commit(lambda engine: unify(r, 'second'))

    engine = Engine()
    result = Var()
    call(engine, predicate, result)
    engine.run()

    assert deref(result) == 'first'


@pytest.mark.unit
def test_a_woken_reduction_leaves_no_cyclic_garbage() -> None:
    # A goal that retries itself through a closure is a reference cycle, which only the
    # cycle collector can free; with the collector off, nothing may be left for it to find.
    factorial = _make_factorial()  # the predicate and its clauses form a cycle; keep it alive
    n = Var()
    result = Var()
    gc.collect()
    gc.disable()
    try:
        engine = Engine()
        call(engine, factorial, n, result)
        engine.run()  # suspends on n
        unify(n, 5)
        engine.run()  # wakes; bind_from waits on each sub-result in turn
        assert deref(result) == 120
        assert gc.collect() == 0
    finally:
        gc.enable()


@pytest.mark.unit
def test_predicate_repr_shows_name_and_count() -> None:
    predicate = Predicate('p')

    @predicate.clause
    def _c(x):
        return fail()

    text = repr(predicate)
    assert 'p' in text
    assert '1' in text
