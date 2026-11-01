"""Every example runs to quiescence with no goal left blocked.

Re-runs the example tests with every :meth:`Engine.run` checked, so a goal still waiting
at the end -- a reader on a stream nobody closed, a server nobody told to stop -- fails as
:class:`DeadlockError` across the DSL, goal, stream and engine layers together.
"""

import inspect
from collections.abc import Callable

import pytest

from python_kl1.core import Engine
from tests.unit import test_examples

type ExampleTest = Callable[[], None]

EXAMPLE_TESTS: list[ExampleTest] = [
    function
    for name, function in inspect.getmembers(test_examples, inspect.isfunction)
    if name.startswith('test_') and function.__module__ == test_examples.__name__
]


@pytest.mark.integration
@pytest.mark.parametrize('example_test', EXAMPLE_TESTS, ids=lambda test: test.__name__.removeprefix('test_'))
def test_an_example_leaves_nothing_blocked(example_test: ExampleTest, monkeypatch: pytest.MonkeyPatch) -> None:
    unchecked_run = Engine.run
    runs = 0

    def checked_run(engine: Engine, *, check: bool = False) -> None:  # `check` is overridden: always on
        nonlocal runs
        runs += 1
        unchecked_run(engine, check=True)

    monkeypatch.setattr(Engine, 'run', checked_run)
    example_test()

    assert runs > 0  # the example went through at least one checked run
