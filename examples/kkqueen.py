r"""KL1 N-Queens (candidate / non-candidate formulation), ported to python-kl1.

Faithful port of ``examples/kkqueen.kl1`` (K. Kumon / E. Tick / T. Chikayama): count the
number of N-Queens solutions. Solutions accumulate in a **difference list** threaded through
the whole search (``I`` / ``O``), so no `merge` is needed. Columns are a shrinking candidate
pool; each row places one queen and removes its column; the board (placed columns) is scanned
for diagonal conflicts.

The KL1 guard disjunction ``(T =:= P+D ; T =:= P-D) | I=O`` becomes committed-choice
ordering: a guarded ``safe`` clause (``T =\= P+D`` and ``T =\= P-D``), then a guard-free
``conflict`` fallback that fires exactly when ``safe`` failed. Run it with
``uv run python examples/kkqueen.py``.
"""

from python_kl1.core import NIL, Value, Var, deref
from python_kl1.dsl import Relation, Term, clause, cons, empty, fresh, guard, nil, session, tell, uncons


class Gen(Relation):
    """gen(N, Xs): Xs is the column pool [N, N-1, ..., 1]."""

    @clause
    def positive(self, n: Term, xs: Term) -> None:
        """gen(N, [N|Xs]) :- N > 0 | gen(N-1, Xs)."""
        guard(n > 0)
        rest = fresh()
        tell(xs, cons(n, rest))
        self(n - 1, rest)

    @clause
    def zero(self, n: Term, xs: Term) -> None:
        """gen(0, [])."""
        guard(n == 0)
        tell(xs, nil())


class Concat(Relation):
    """concat(Xs, Ys, Zs): Zs = Xs ++ Ys."""

    @clause
    def done(self, xs: Term, ys: Term, zs: Term) -> None:
        """concat([], Y, Y)."""
        empty(xs)
        tell(zs, ys)

    @clause
    def step(self, xs: Term, ys: Term, zs: Term) -> None:
        """concat([W|X], Y, [W|Z]) :- concat(X, Y, Z)."""
        head, rest = uncons(xs)
        rest_zs = fresh()
        tell(zs, cons(head, rest_zs))
        self(rest, ys, rest_zs)


class Count(Relation):
    """count(Xs, Acc, N): N = Acc + length(Xs)."""

    @clause
    def done(self, xs: Term, acc: Term, out: Term) -> None:
        """count([], N, N)."""
        empty(xs)
        tell(out, acc)

    @clause
    def step(self, xs: Term, acc: Term, out: Term) -> None:
        """count([_|Xs], Acc, N) :- count(Xs, Acc+1, N)."""
        _head, rest = uncons(xs)
        self(rest, acc + 1, out)


class Check(Relation):
    """check(Scan, T, D, U, C, Board, I, O): is column T safe against Board's diagonals?"""

    @clause
    def placed(self, scan: Term, t: Term, d: Term, u: Term, c: Term, board: Term, i: Term, o: Term) -> None:
        """check([], T, _, U, C, B, I, O) :- concat(U, C, N), queen(N, [], [T|B], I, O)."""
        empty(scan)
        remaining = fresh()
        _concat(u, c, remaining)
        _queen(remaining, NIL, cons(t, board), i, o)

    @clause
    def safe(self, scan: Term, t: Term, d: Term, u: Term, c: Term, board: Term, i: Term, o: Term) -> None:
        r"""check([P|R], T, D, ...) :- T =\= P+D, T =\= P-D | check(R, T, D+1, ...)."""
        p, rest = uncons(scan)
        guard(t != p + d)
        guard(t != p - d)
        self(rest, t, d + 1, u, c, board, i, o)

    @clause
    def conflict(self, scan: Term, t: Term, d: Term, u: Term, c: Term, board: Term, i: Term, o: Term) -> None:
        """check([P|_], T, D, ...) :- (T =:= P+D ; T =:= P-D) | I = O."""
        uncons(scan)  # Scan is non-empty and `safe` failed => a diagonal conflict; no solution.
        tell(i, o)


class Queen(Relation):
    r"""queen(U, C, Board, I, O): search placing one queen per row; solutions accumulate in I\O."""

    @clause
    def solution(self, u: Term, c: Term, board: Term, i: Term, o: Term) -> None:
        """queen([], [], Board, I, O) :- I = [Board|O]  (pool empty -> a full solution)."""
        empty(u)
        empty(c)
        tell(i, cons(board, o))

    @clause
    def dead_end(self, u: Term, c: Term, board: Term, i: Term, o: Term) -> None:
        """queen([], [_|_], _, I, O) :- I = O  (this row's candidates are exhausted)."""
        empty(u)
        uncons(c)  # C non-empty
        tell(i, o)

    @clause
    def place(self, u: Term, c: Term, board: Term, i: Term, o: Term) -> None:
        """queen([P|U], C, Board, I, O) :- check(Board, P, 1, U, C, Board, I, I1), queen(U, [P|C], Board, I1, O)."""
        p, rest = uncons(u)
        i1 = fresh()
        _check(board, p, 1, rest, c, board, i, i1)
        self(rest, cons(p, c), board, i1, o)


_gen = Gen()
_concat = Concat()
_count = Count()
_check = Check()
_queen = Queen()


def count_solutions(n: int) -> Value:
    """Return the number of N-Queens solutions (go(N, M) in kkqueen.kl1)."""
    with session() as engine:
        columns = Var()
        solutions = Var()
        total = Var()
        _gen(n, columns)  # gen(N, L)
        _queen(columns, NIL, NIL, solutions, NIL)  # queen(L, [], [], X, [])
        _count(solutions, 0, total)  # count(X, 0, M)
        engine.run()
        return deref(total)


def main() -> None:
    """Print the solution count for a few board sizes."""
    for n in (4, 5, 6, 8):
        print(f'{n}-queens: {count_solutions(n)} solutions')


if __name__ == '__main__':
    main()
