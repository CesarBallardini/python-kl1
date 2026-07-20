"""KL1 quicksort, ported to python-kl1 with the clause DSL.

Mirrors ``ch03-metamorphosis/qsort.kl1`` (and ``examples/qsort.kl1``)::

    qsort([], Sorted, Tail)        :- Sorted = Tail.
    qsort([X|L], Sorted, Tail)     :- part(L, X, Lesser, Greater),
                                      qsort(Greater, GSorted, Tail),
                                      qsort(Lesser, Sorted, [X|GSorted]).
    part([], _, [], []).
    part([H|T], P, [H|L], G) :- H =< P | part(T, P, L, G).
    part([H|T], P, L, [H|G]) :- H  > P | part(T, P, L, G).

``Sorted`` / ``Tail`` form a **difference list**: the O(1)-concatenation trick that lets
quicksort avoid ``append``. Run it with ``uv run python examples/qsort.py``.
"""

from python_kl1.core import NIL, Var, drain, stream_from
from python_kl1.dsl import Relation, Term, clause, cons, empty, fresh, guard, nil, session, tell, uncons


class Partition(Relation):
    """partition(Xs, Pivot, Lesser, Greater): split Xs into <= and > Pivot."""

    @clause
    def done(self, xs: Term, pivot: Term, lesser: Term, greater: Term) -> None:
        """part([], _, [], [])."""
        empty(xs)
        tell(lesser, nil())
        tell(greater, nil())

    @clause
    def lesser(self, xs: Term, pivot: Term, lesser: Term, greater: Term) -> None:
        """part([H|T], P, [H|L], G) :- H =< P | ..."""
        head, rest = uncons(xs)
        guard(head <= pivot)
        rest_lesser = fresh()
        tell(lesser, cons(head, rest_lesser))
        self(rest, pivot, rest_lesser, greater)

    @clause
    def greater(self, xs: Term, pivot: Term, lesser: Term, greater: Term) -> None:
        """part([H|T], P, L, [H|G]) :- H > P | ..."""
        head, rest = uncons(xs)
        guard(head > pivot)
        rest_greater = fresh()
        tell(greater, cons(head, rest_greater))
        self(rest, pivot, lesser, rest_greater)


class QSort(Relation):
    """qsort(Unsorted, Sorted, Tail): quicksort with a difference-list accumulator."""

    partition = Partition()

    @clause
    def at_end(self, xs: Term, sorted_run: Term, tail: Term) -> None:
        """qsort([], Sorted, Tail) :- Sorted = Tail."""
        empty(xs)
        tell(sorted_run, tail)

    @clause
    def recurse(self, xs: Term, sorted_run: Term, tail: Term) -> None:
        """qsort([X|L], Sorted, Tail) :- part(L,X,Le,Gr), qsort(Gr,GS,Tail), qsort(Le,Sorted,[X|GS])."""
        pivot, rest = uncons(xs)
        lesser = fresh()
        greater = fresh()
        self.partition(rest, pivot, lesser, greater)
        greater_sorted = fresh()
        self(greater, greater_sorted, tail)
        self(lesser, sorted_run, cons(pivot, greater_sorted))


qsort = QSort()


def main() -> None:
    """Sort a fixed list (matching qsort.kl1)."""
    with session() as engine:
        numbers = stream_from(engine, [3, 1, 4, 1, 5, 9, 2, 6])
        result = Var()
        qsort(numbers, result, NIL)  # Tail = []
        print(list(drain(engine, result)))


if __name__ == '__main__':
    main()
