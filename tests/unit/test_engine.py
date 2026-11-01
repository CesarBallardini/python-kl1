"""Unit tests for the cooperative engine, including its context-manager scope."""

import pickle

import pytest

from python_kl1.core import DeadlockError, Engine, Var, unify
from python_kl1.core.goal import retry_when_any_bound


@pytest.mark.unit
def test_context_manager_runs_to_quiescence_on_exit() -> None:
    log: list[int] = []

    with Engine() as engine:
        engine.spawn(lambda: log.append(1))
        assert log == []  # nothing runs until the block exits

    assert log == [1]


@pytest.mark.unit
def test_context_manager_skips_run_when_the_block_raises() -> None:
    log: list[int] = []

    with pytest.raises(ValueError, match='boom'), Engine() as engine:
        engine.spawn(lambda: log.append(1))
        raise ValueError('boom')

    assert log == []


@pytest.mark.unit
def test_goals_run_in_fifo_order() -> None:
    engine = Engine()
    log: list[int] = []

    for i in range(5):
        engine.spawn(lambda i=i: log.append(i))
    engine.run()

    assert log == [0, 1, 2, 3, 4]


@pytest.mark.unit
def test_step_reports_whether_a_goal_ran() -> None:
    engine = Engine()
    engine.spawn(lambda: None)

    assert engine.step() is True
    assert engine.step() is False


@pytest.mark.unit
def test_run_on_an_empty_queue_is_a_noop() -> None:
    Engine().run()  # returns without hanging or raising


@pytest.mark.unit
def test_a_goal_may_spawn_another_goal() -> None:
    engine = Engine()
    log: list[str] = []

    def first() -> None:
        log.append('first')
        engine.spawn(lambda: log.append('second'))

    engine.spawn(first)
    engine.run()

    assert log == ['first', 'second']


@pytest.mark.unit
def test_a_suspended_goal_is_blocked_until_it_wakes() -> None:
    engine = Engine()
    awaited = Var()
    log: list[str] = []

    retry_when_any_bound(engine, [awaited], lambda: log.append('ran'), lambda: 'waiter')
    engine.run()
    assert engine.blocked == ('waiter',)

    unify(awaited, 1)
    engine.run()
    assert engine.blocked == ()
    assert log == ['ran']


@pytest.mark.unit
def test_a_goal_waiting_on_two_variables_unblocks_once() -> None:
    engine = Engine()
    first, second = Var(), Var()
    log: list[str] = []

    retry_when_any_bound(engine, [first, second], lambda: log.append('ran'), lambda: 'waiter')
    unify(first, 1)
    unify(second, 2)
    engine.run()  # both waiters fire; a second unblock would raise KeyError

    assert engine.blocked == ()
    assert log == ['ran']


@pytest.mark.unit
def test_run_with_check_reports_a_deadlock() -> None:
    engine = Engine()
    retry_when_any_bound(engine, [Var()], lambda: None, lambda: 'waiter')
    engine.run()  # without check, quiescence is silent

    with pytest.raises(DeadlockError, match=r'^1 goal\(s\) blocked at quiescence: waiter$') as caught:
        engine.run(check=True)
    assert caught.value.blocked == ('waiter',)


@pytest.mark.unit
def test_run_with_check_is_quiet_when_nothing_is_blocked() -> None:
    engine = Engine()
    log: list[int] = []
    engine.spawn(lambda: log.append(1))

    engine.run(check=True)

    assert log == [1]


@pytest.mark.unit
def test_a_deadlock_message_lists_the_first_ten_goals() -> None:
    error = DeadlockError(tuple(f'g{i}' for i in range(12)))

    assert str(error) == '12 goal(s) blocked at quiescence: ' + '; '.join(f'g{i}' for i in range(10)) + (
        '; ... and 2 more'
    )
    assert len(error.blocked) == 12


@pytest.mark.unit
def test_a_deadlock_error_survives_pickling() -> None:
    error = DeadlockError(('a(1)', 'b(2)'))

    # A worker process forwards it this way; the bytes are our own, so S301 does not apply.
    copy = pickle.loads(pickle.dumps(error))  # noqa: S301

    assert copy.blocked == error.blocked
    assert str(copy) == str(error)


@pytest.mark.unit
def test_a_goal_that_suspends_again_is_blocked_once() -> None:
    engine = Engine()
    first, second = Var(), Var()

    def again() -> None:
        retry_when_any_bound(engine, [second], lambda: None, lambda: 'round 2')

    retry_when_any_bound(engine, [first, second], again, lambda: 'round 1')
    unify(first, 1)
    engine.run()
    assert engine.blocked == ('round 2',)  # round 1's stale waiter on `second` is not counted

    unify(second, 2)
    engine.run()
    assert engine.blocked == ()


@pytest.mark.unit
def test_a_goal_that_raises_on_waking_is_no_longer_blocked() -> None:
    engine = Engine()
    awaited = Var()

    def explode() -> None:
        raise ValueError('boom')

    retry_when_any_bound(engine, [awaited], explode, lambda: 'waiter')
    unify(awaited, 1)

    with pytest.raises(ValueError, match='boom'):
        engine.run()
    assert engine.blocked == ()
