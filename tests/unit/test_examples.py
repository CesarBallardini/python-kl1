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
from examples.life import life_count
from examples.mastermind import go as mastermind_go
from examples.merge import go as merge_go
from examples.merge import merge_count
from examples.not_gate import not_gate
from examples.pascal import rows as pascal_rows
from examples.pp import pp
from examples.puzzle import count_packings
from examples.qlay import count_solutions as qlay_count
from examples.qsort import qsort
from examples.sieve import primes
from examples.wave import final_states as wave_states
from examples.wave import go as wave_go
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


@pytest.mark.unit
def test_merge_example() -> None:
    assert merge_count(0) == 0
    assert merge_count(1) == 1
    assert merge_count(7) == 7  # K one-element streams in, K elements out, and the merge closes

    with session() as engine:
        merge_go(0, 10)  # merge.kl1's go/2 over a shorter range: every total must unify with its K
        engine.run()


@pytest.mark.unit
def test_pp_example() -> None:
    assert to_list(pp(12)) == list(range(12, -1, -1))  # pp.kl1's main: 12, 11, ..., 0
    assert to_list(pp(0)) == [0]  # r closes L at the first 0 it reads


@pytest.mark.unit
def test_mastermind_example() -> None:
    assert mastermind_go(1, 3) == 1  # only the code itself solves in one guess
    assert mastermind_go(3, 2) == 0  # colours {1, 2} can never produce the 3 in [2, 1, 3, 2]
    assert mastermind_go(2, 3) == 81  # brute-force reference; mastermind.kl1's own go(3, 3) = 860 is main()'s job


def reference_count(g: int, x: int, y: int) -> int:
    """Lockstep simulation of life.kl1's torus: its init generator and its change table (Y = (X + T + 1) mod 2)."""
    cols: list[list[int]] = []
    for cx in range(x, 0, -1):  # init: columns X..1, PrevNum starts at the column's X
        prev = cx
        col: list[int] = []
        for cy in range(y, 0, -1):  # init_col: cells Y..1
            prev = (prev >> 3) + (cx << 2) + (cy >> 2)
            col.append(prev % 2)
        cols.append(col)
    for _ in range(g):  # T = 4-neighbour sum on the torus
        cols = [
            [
                (cols[i][j] + cols[i - 1][j] + cols[(i + 1) % x][j] + cols[i][j - 1] + cols[i][(j + 1) % y] + 1) % 2
                for j in range(y)
            ]
            for i in range(x)
        ]
    return sum(map(sum, cols))


@pytest.mark.unit
def test_life_example() -> None:
    # The dataflow program is determinate, so it must agree with a synchronous simulation of the same torus.
    for g, x, y in [(1, 3, 3), (5, 6, 6), (10, 8, 5), (7, 9, 9), (30, 20, 20)]:
        assert life_count(g, x, y) == reference_count(g, x, y)
    assert life_count(1, 3, 3) == 5
    assert life_count(30, 20, 20) == 200  # life.kl1's go/1 (120, 38, 38) gives 711 in ~23 s; main() runs it


@pytest.mark.unit
def test_wave_example() -> None:
    states = wave_states(6, 2)  # wave.kl1's main: go(6,2,S) -- a 6 x 4 x 6 block, two rounds
    assert len(states) == 144  # every node reports, so none of them deadlocked
    assert set(states) == {3}  # initial state 1, incremented once per round
    assert wave_states(5, 2) == []  # D =< 5: the otherwise clause answers no and spawns nothing

    with session() as engine:
        answer, states_var = Var(), Var()
        wave_go(6, 1, answer, states_var)
        engine.run()
    assert deref(answer) == 'yes'
    assert to_list(states_var) == [2] * 144


@pytest.mark.unit
def test_puzzle_example() -> None:
    # go() -- the full 5x4x3 box, puzzle.kl1's 65 -- takes ~20 s, so main() runs it. A 5x3x3 box packed with two
    # 4x3x1, two 3x2x1 and the 3x3x1 piece still fires direct, 2-layer and 3-layer template orientations alike:
    # 32 packings, per an independent brute-force packer.
    layer = tuple('v' if x < 5 and y < 3 else 'z' for y in range(5) for x in range(6))  # 30 cells, BOARD's strides
    assert count_packings(layer * 3 + ('z',) * 30, [['a', 'b'], ['d', 'e'], ['f'], []]) == 32
    # One 5x4 layer with a 4x3x1 and a 4x2x1: 3x4 beside 2x4, either way round.
    assert count_packings((('v',) * 5 + ('z',)) * 4 + ('z',) * 36, [[], ['d'], [], ['g']]) == 2
