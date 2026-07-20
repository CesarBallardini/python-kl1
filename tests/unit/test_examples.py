"""Assert the example programs compute their KL1-correct results.

Imports each example's public entry point and checks the value it produces, so the
shipped example relations are verified (not just that the scripts run).
"""

import pytest

from examples.bank_account import account
from examples.deriv import deriv, show
from examples.factorial import factorial
from examples.hanoi import hanoi
from examples.kkqueen import count_solutions as queens_count
from examples.not_gate import not_gate
from examples.pascal import rows as pascal_rows
from examples.qlay import count_solutions as qlay_count
from examples.qsort import qsort
from examples.sieve import primes
from python_kl1.core import NIL, Engine, Struct, Var, deref, stream_from, to_list
from python_kl1.dsl import call, session


@pytest.mark.unit
def test_factorial_example() -> None:
    assert factorial(1) == 1
    assert factorial(5) == 120
    assert factorial(11) == 39916800  # matches fact.kl1


@pytest.mark.unit
def test_not_gate_example() -> None:
    assert not_gate(0) == 1
    assert not_gate(1) == 0


@pytest.mark.unit
def test_sieve_example() -> None:
    with session() as engine:
        result = Var()
        primes(30, result)
        engine.run()
        assert to_list(result) == [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]  # matches primes_sieve.kl1


@pytest.mark.unit
def test_bank_account_example() -> None:
    engine = Engine()
    reply = Var()
    stream = stream_from(
        engine,
        [Struct('deposit', (100,)), Struct('deposit', (50,)), Struct('debit', (30,)), Struct('balance', (reply,))],
    )

    call(engine, account, stream, 0)
    engine.run()

    assert deref(reply) == 120  # 100 + 50 - 30, matches bank_account.kl1


@pytest.mark.unit
def test_qsort_example() -> None:
    with session() as engine:
        result = Var()
        qsort(stream_from(engine, [3, 1, 4, 1, 5, 9, 2, 6]), result, NIL)
        engine.run()
        assert to_list(result) == [1, 1, 2, 3, 4, 5, 6, 9]


@pytest.mark.unit
def test_deriv_example() -> None:
    expr = Struct('plus', (Struct('times', ('x', 'x')), 'x'))  # x*x + x
    with session() as engine:
        d = Var()
        deriv(expr, d)
        engine.run()
        assert show(d) == '(((x * 1) + (x * 1)) + 1)'  # 2x + 1, unsimplified


@pytest.mark.unit
def test_hanoi_example() -> None:
    with session() as engine:
        moves = Var()
        hanoi(3, 'a', 'c', 'b', moves, NIL)
        engine.run()
        moves_list = to_list(moves)

    assert len(moves_list) == 7  # 2**3 - 1
    assert moves_list[0] == Struct('move', ('a', 'c'))
    assert moves_list[-1] == Struct('move', ('a', 'c'))


@pytest.mark.unit
def test_pascal_example() -> None:
    assert pascal_rows(6)[-1] == [1, 5, 10, 10, 5, 1]


@pytest.mark.unit
def test_kkqueen_example() -> None:
    assert queens_count(6) == 4
    assert queens_count(8) == 92  # the canonical N=8 solution count


@pytest.mark.unit
def test_qlay_example() -> None:
    assert qlay_count(6) == 4
    assert qlay_count(8) == 92  # layered-streams N-Queens, same counts
