"""Unit tests for the cooperative engine, including its context-manager scope."""

import pytest

from python_kl1.core import Engine


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
