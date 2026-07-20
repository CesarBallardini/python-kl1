"""KL1 Towers of Hanoi, ported to python-kl1 with the clause DSL.

In the spirit of ``examples/hanoi.kl1``: produce the list of moves that shifts ``N`` disks
from one peg to another::

    hanoi(0, _, _, _, Moves, Tail) :- Moves = Tail.
    hanoi(N, From, To, Via, Moves, Tail) :- N > 0 |
        hanoi(N-1, From, Via, To, Moves, M1),
        M1 = [move(From, To) | M2],
        hanoi(N-1, Via, To, From, M2, Tail).

``Moves`` / ``Tail`` form a **difference list** (O(1) concatenation of the two sub-sequences
around the big-disk move); ``move(From, To)`` is a **functor**. Run it with
``uv run python examples/hanoi.py``.
"""

from python_kl1.core import NIL, Struct, Var, deref, drain
from python_kl1.dsl import Relation, Term, clause, cons, fresh, guard, session, struct, tell


class Hanoi(Relation):
    """hanoi(N, From, To, Via, Moves, Tail): the moves shifting N disks From -> To via Via."""

    @clause
    def base(self, n: Term, source: Term, dest: Term, spare: Term, moves: Term, tail: Term) -> None:
        """hanoi(0, _, _, _, Moves, Tail) :- Moves = Tail."""
        guard(n == 0)
        tell(moves, tail)

    @clause
    def step(self, n: Term, source: Term, dest: Term, spare: Term, moves: Term, tail: Term) -> None:
        """hanoi(N, From, To, Via, ...) :- N > 0 | (N-1 From->Via), move(From,To), (N-1 Via->To)."""
        guard(n > 0)
        mid = fresh()
        self(n - 1, source, spare, dest, moves, mid)
        rest = fresh()
        tell(mid, cons(struct('move', source, dest), rest))
        self(n - 1, spare, dest, source, rest, tail)


hanoi = Hanoi()


def main() -> None:
    """Print the moves to shift 3 disks from peg a to peg c."""
    with session() as engine:
        moves = Var()
        hanoi(3, 'a', 'c', 'b', moves, NIL)
        engine.run()
        for raw in drain(engine, moves):
            move = deref(raw)
            if isinstance(move, Struct):
                print(f'{move.args[0]} -> {move.args[1]}')


if __name__ == '__main__':
    main()
