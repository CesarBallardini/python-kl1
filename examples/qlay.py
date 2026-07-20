r"""KL1 N-Queens via **layered streams**, ported to python-kl1.

Faithful port of ``examples/qlay.kl1`` (A. Okimura, ICOT TR-421): count N-Queens solutions
using the *layered-streams* technique. A partial-solution set is a nested stream whose
elements are ``[Column | SubStream]``; ``filter`` prunes the columns that conflict with a
newly placed queen, ``lastFilter`` flattens the final layer into full solutions, and the
solutions are threaded through a difference list. The marker atom ``begin`` starts an empty
layered stream.

The two KL1 ``otherwise.`` defaults become committed-choice ordering: the skip clauses
(same column, either diagonal) come first, then a guard-free ``keep`` fallback that fires
only when they all failed. Run it with ``uv run python examples/qlay.py``.
"""

from python_kl1.core import Value, Var, deref
from python_kl1.dsl import Relation, Term, clause, cons, empty, fresh, guard, nil, session, tell, uncons


class Filter(Relation):
    """filter(Incoming, I, D, Out): drop layers conflicting with a queen in column I."""

    @clause
    def at_begin(self, incoming: Term, i: Term, d: Term, out: Term) -> None:
        """filter(begin, _, _, Out) :- Out = begin."""
        guard(incoming == 'begin')
        tell(out, 'begin')

    @clause
    def at_end(self, incoming: Term, i: Term, d: Term, out: Term) -> None:
        """filter([], _, _, Out) :- Out = []."""
        empty(incoming)
        tell(out, nil())

    @clause
    def same_column(self, incoming: Term, i: Term, d: Term, out: Term) -> None:
        """filter([[I|_]|Ins], I, D, Out) :- filter(Ins, I, D, Out)."""
        head, ins = uncons(incoming)
        j, _sub = uncons(head)
        guard(j == i)
        self(ins, i, d, out)

    @clause
    def diagonal_down(self, incoming: Term, i: Term, d: Term, out: Term) -> None:
        """filter([[J|_]|Ins], I, D, Out) :- D =:= I-J | filter(Ins, I, D, Out)."""
        head, ins = uncons(incoming)
        j, _sub = uncons(head)
        guard(d == i - j)
        self(ins, i, d, out)

    @clause
    def diagonal_up(self, incoming: Term, i: Term, d: Term, out: Term) -> None:
        """filter([[J|_]|Ins], I, D, Out) :- D =:= J-I | filter(Ins, I, D, Out)."""
        head, ins = uncons(incoming)
        j, _sub = uncons(head)
        guard(d == j - i)
        self(ins, i, d, out)

    @clause
    def keep(self, incoming: Term, i: Term, d: Term, out: Term) -> None:
        """filter([[J|In1]|Ins], I, D, Out) :- Out = [[J|Out1]|Outs], filter(In1,I,D+1,Out1), filter(Ins,I,D,Outs)."""
        head, ins = uncons(incoming)
        j, sub = uncons(head)
        out1 = fresh()
        outs = fresh()
        self(sub, i, d + 1, out1)
        self(ins, i, d, outs)
        tell(out, cons(cons(j, out1), outs))


class LastFilter(Relation):
    r"""lastFilter(Stack, Incoming, I, D, S, T): flatten the final layer into solutions S\T."""

    @clause
    def at_begin(self, stack: Term, incoming: Term, i: Term, d: Term, s: Term, t: Term) -> None:
        """lastFilter(Stack, begin, _, _, S, T) :- S = [Stack|T]."""
        guard(incoming == 'begin')
        tell(s, cons(stack, t))

    @clause
    def at_end(self, stack: Term, incoming: Term, i: Term, d: Term, s: Term, t: Term) -> None:
        """lastFilter(_, [], _, _, S, T) :- S = T."""
        empty(incoming)
        tell(s, t)

    @clause
    def same_column(self, stack: Term, incoming: Term, i: Term, d: Term, s: Term, t: Term) -> None:
        """lastFilter(Stack, [[I|_]|Ins], I, D, S, T) :- lastFilter(Stack, Ins, I, D, S, T)."""
        head, ins = uncons(incoming)
        j, _sub = uncons(head)
        guard(j == i)
        self(stack, ins, i, d, s, t)

    @clause
    def diagonal_down(self, stack: Term, incoming: Term, i: Term, d: Term, s: Term, t: Term) -> None:
        """lastFilter(Stack, [[J|_]|Ins], I, D, S, T) :- D =:= I-J | ..."""
        head, ins = uncons(incoming)
        j, _sub = uncons(head)
        guard(d == i - j)
        self(stack, ins, i, d, s, t)

    @clause
    def diagonal_up(self, stack: Term, incoming: Term, i: Term, d: Term, s: Term, t: Term) -> None:
        """lastFilter(Stack, [[J|_]|Ins], I, D, S, T) :- D =:= J-I | ..."""
        head, ins = uncons(incoming)
        j, _sub = uncons(head)
        guard(d == j - i)
        self(stack, ins, i, d, s, t)

    @clause
    def keep(self, stack: Term, incoming: Term, i: Term, d: Term, s: Term, t: Term) -> None:
        """Keep clause: stack J and recurse into In, then into Ins.

        lastFilter(Stack, [[J|In]|Ins], I, D, S, T) :- lastFilter([J|Stack], In, I, D+1,
        S, SS), lastFilter(Stack, Ins, I, D, SS, T).
        """
        head, ins = uncons(incoming)
        j, sub = uncons(head)
        stitch = fresh()
        self(cons(j, stack), sub, i, d + 1, s, stitch)
        self(stack, ins, i, d, stitch, t)


class Q(Relation):
    """q(I, N, Incoming, Out): try columns I..N in the current row, extending the layers."""

    sift = Filter()

    @clause
    def emit(self, i: Term, n: Term, incoming: Term, out: Term) -> None:
        """q(I, N, In, Out) :- I =< N | filter(In, I, 1, Out1), q(I+1, N, In, Outs), Out = [[I|Out1]|Outs]."""
        guard(i <= n)
        out1 = fresh()
        self.sift(incoming, i, 1, out1)
        outs = fresh()
        self(i + 1, n, incoming, outs)
        tell(out, cons(cons(i, out1), outs))

    @clause
    def done(self, i: Term, n: Term, incoming: Term, out: Term) -> None:
        """q(I, N, _, Out) :- I > N | Out = []."""
        guard(i > n)
        tell(out, nil())


class LastQ(Relation):
    """lastQ(I, N, Incoming, Out): the final row -- flatten each column into full solutions."""

    last_filter = LastFilter()

    @clause
    def emit(self, i: Term, n: Term, incoming: Term, out: Term) -> None:
        """lastQ(I, N, In, Out) :- I =< N | lastFilter([I], In, I, 1, Out, Out1), lastQ(I+1, N, In, Out1)."""
        guard(i <= n)
        out1 = fresh()
        self.last_filter(cons(i, nil()), incoming, i, 1, out, out1)
        self(i + 1, n, incoming, out1)

    @clause
    def done(self, i: Term, n: Term, incoming: Term, out: Term) -> None:
        """lastQ(I, N, _, Out) :- I > N | Out = []."""
        guard(i > n)
        tell(out, nil())


class Queen(Relation):
    """queen(I, N, Incoming, Out): place one queen per row, chaining the layered streams."""

    q = Q()
    last_q = LastQ()

    @clause
    def row(self, i: Term, n: Term, incoming: Term, out: Term) -> None:
        """queen(I, N, In, Out) :- I < N | q(1, N, In, Mid), queen(I+1, N, Mid, Out)."""
        guard(i < n)
        mid = fresh()
        self.q(1, n, incoming, mid)
        self(i + 1, n, mid, out)

    @clause
    def last_row(self, i: Term, n: Term, incoming: Term, out: Term) -> None:
        """queen(N, N, In, Out) :- lastQ(1, N, In, Out)."""
        guard(i == n)
        self.last_q(1, n, incoming, out)


class Count(Relation):
    """count(Xs, Acc, N): N = Acc + length(Xs)."""

    @clause
    def more(self, xs: Term, acc: Term, out: Term) -> None:
        """count([_|Xs], Acc, N) :- count(Xs, Acc+1, N)."""
        _head, rest = uncons(xs)
        self(rest, acc + 1, out)

    @clause
    def done(self, xs: Term, acc: Term, out: Term) -> None:
        """count([], N, N)."""
        empty(xs)
        tell(out, acc)


_queen = Queen()
_count = Count()


def count_solutions(n: int) -> Value:
    """Return the number of N-Queens solutions (go(N, M) in qlay.kl1)."""
    with session() as engine:
        solutions = Var()
        total = Var()
        _queen(1, n, 'begin', solutions)  # queen(1, N, begin, A)
        _count(solutions, 0, total)  # count(A, 0, N)
        engine.run()
        return deref(total)


def main() -> None:
    """Print the solution count for a few board sizes."""
    for n in (4, 5, 6, 8):
        print(f'{n}-queens: {count_solutions(n)} solutions')


if __name__ == '__main__':
    main()
