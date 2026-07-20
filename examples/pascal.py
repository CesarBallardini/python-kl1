"""KL1 Pascal's triangle, ported to python-kl1 with the clause DSL.

In the spirit of ``examples/pascal.kl1``: each row is the previous one shifted and added
(``next = zipWith(+) (0:Row) (Row ++ [0])``), computed in a single pass by carrying the
previous element::

    next_row(C, [],      [C]).
    next_row(C, [X|Xs], [C+X|Rest]) :- next_row(X, Xs, Rest).

The per-row KL1 step is a relation; the Python driver iterates it N times. Run it with
``uv run python examples/pascal.py``.
"""

from python_kl1.core import Value, Var, stream_from, to_list
from python_kl1.dsl import Relation, Term, clause, cons, empty, fresh, nil, session, tell, uncons


class NextRow(Relation):
    """next_row(Carry, Row, Out): Out is the next Pascal row (running shift-and-add)."""

    @clause
    def done(self, carry: Term, row: Term, out: Term) -> None:
        """next_row(C, [], [C])."""
        empty(row)
        tell(out, cons(carry, nil()))

    @clause
    def step(self, carry: Term, row: Term, out: Term) -> None:
        """next_row(C, [X|Xs], [C+X|Rest]) :- next_row(X, Xs, Rest)."""
        x, rest = uncons(row)
        rest_out = fresh()
        tell(out, cons(carry + x, rest_out))
        self(x, rest, rest_out)


next_row = NextRow()


def rows(n: int) -> list[list[Value]]:
    """Return the first ``n`` rows of Pascal's triangle."""
    result: list[list[Value]] = []
    row: list[Value] = [1]
    for _ in range(n):
        result.append(row)
        with session() as engine:
            out = Var()
            next_row(0, stream_from(engine, row), out)  # carry starts at 0
            engine.run()
            row = to_list(out)
    return result


def main() -> None:
    """Print the first six rows of Pascal's triangle."""
    for row in rows(6):
        print(row)


if __name__ == '__main__':
    main()
