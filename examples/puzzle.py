"""KLIC's ``puzzle`` benchmark (E. Tick, 1988), ported to python-kl1 with the clause DSL.

Mirrors ``kl1c/examples/puzzle.kl1``: pack a 5x4x3 box that has a chip in one corner with seven
pieces -- three 3x2x1, two 4x3x1, one 3x3x1 and one 4x2x1 -- and count the packings::

    go(N) :- make_board(Board), play(Board, [[a,b,c],[d,e],[f],[g]], L, [], 0, []), count(L, N).

The board is a flat list of 120 cells: three layers of four rows of five vacant ``v`` cells,
every row and every layer closed by ``z`` sentinels, plus a fourth all-``z`` layer, so that a
piece can be matched against the list without ever running off an edge. ``play`` walks the
list: at a ``v`` it tries every orientation of every piece kind that still has pieces, at any
other cell it moves on, and an exhausted board is a solution. Each orientation is a relation
that either head-unifies its footprint with the front of the board -- the ``v`` cells it needs
and the don't-care cells between them -- and keeps playing on the board with the footprint
stamped with the piece's mark ``M``, or (``otherwise``) passes the solution stream through
untouched. The small pieces spell their footprint out directly; the large ones hand a list of
codewords to ``match``, Tick's "abstract template matching routine", which consumes the board
one codeword at a time (``vsssss2`` stands for ``[v,_,_,_,_,_,v,_,_,_,_,_]``) while copying
the don't-care cells onto the new board.

Solutions are collected in difference lists: each clause gets the head ``S0`` and tail ``S1``
of its segment of the solution stream, and the orientations of a piece are chained ``S0, S1,
..., Sk``, so the whole search is one concurrent all-solutions dataflow computation with no
backtracking. ``go()`` answers 65, as the original's header promises. The original prints
nothing but N; ``main()`` does the same. ``count_packings`` runs the same search over a board
and piece list of your choosing, which is how the tests keep to a smaller box. Run it with
``uv run python examples/puzzle.py``.
"""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING

from python_kl1.core import Var, to_list
from python_kl1.dsl import (
    Relation,
    Term,
    clause,
    cons,
    empty,
    fresh,
    guard,
    nil,
    otherwise,
    session,
    struct,
    tell,
    uncons,
    unstruct,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from python_kl1.dsl import Operand

_ROW = ('v',) * 5 + ('z',)  # five cells and a sentinel
_LAYER = _ROW * 4 + ('z',) * 6  # four rows and a sentinel row: 30 cells
BOARD = ('z',) + _LAYER[1:] + _LAYER * 2 + ('z',) * 30  # the chip in the corner, two more layers, a sentinel layer
PIECES = (('a', 'b', 'c'), ('d', 'e'), ('f',), ('g',))  # the marks of the 3x2x1, 4x3x1, 3x3x1 and 4x2x1 pieces

CODEWORDS = {  # match's vocabulary, as head patterns: 'v' must be vacant, '_' is a don't-care cell
    'ssssss1': '______',
    'ssssss2': '____________',
    'vvssss1': 'vv____',
    'vvvsss1': 'vvv___',
    'vvvvss1': 'vvvv__',
    'vsssss1': 'v_____',
    'vsssss2': 'v_____v_____',
    'vsssss3': 'v_____v_____v_____',
}


def head(board: Term, spec: str) -> tuple[list[Term], Term]:
    """Head-unify the front of ``board`` with ``spec``, one cell per character: ``v`` or a don't-care ``_``.

    Returns the matched cells and the rest of the board. Like a failed head unification it fails
    the clause when a required ``v`` is anything else or the board runs out; it suspends on an
    unbound cell.
    """
    cells: list[Term] = []
    rest = board
    for required in spec:
        cell, rest = uncons(rest)
        if required == 'v':
            guard(cell == 'v')
        cells.append(cell)
    return cells, rest


def stamp(cells: Sequence[Term], spec: str, mark: Term) -> list[Term]:
    """The matched ``cells`` with every required ``v`` replaced by the piece's ``mark``."""
    return [mark if required == 'v' else cell for cell, required in zip(cells, spec, strict=True)]


def build(cells: Sequence[Operand], tail: Term) -> Term:
    """The list term ``[cells... | tail]``."""
    result = tail
    for cell in reversed(cells):
        result = cons(cell, result)
    return result


def four(pieces: Term) -> list[Term]:
    """Head pattern ``[P1, P2, P3, P4]``: the remaining marks of the four piece kinds."""
    kinds, rest = head(pieces, '____')
    empty(rest)
    return kinds


def placed(code: Operand, n: Term, a: Term) -> Term:
    """``[[Code|N] | A]``: the solution so far, extended with orientation ``Code`` placed at step ``N``."""
    return cons(cons(code, n), a)


class CountFrom(Relation):
    """count(L, M, N): N is M plus the length of L."""

    @clause
    def at_end(self, xs: Term, m: Term, n: Term) -> None:
        """count([], M, N) :- M = N."""
        empty(xs)
        tell(n, m)

    @clause
    def more(self, xs: Term, m: Term, n: Term) -> None:
        """count([_|Xs], M, N) :- M1 := M+1, count(Xs, M1, N)."""
        _, rest = uncons(xs)
        self(rest, m + 1, n)


class Count(Relation):
    """count(L, N): N is the length of L."""

    count_from = CountFrom()

    @clause
    def start(self, xs: Term, n: Term) -> None:
        """count(L, N) :- count(L, 0, N)."""
        self.count_from(xs, 0, n)


class Match(Relation):
    """match(Codes, Board, B, M, j(NewBoard, Pieces, S0, S1, N, A, Code)): Tick's template matcher.

    Consumes ``Board`` one codeword of ``Codes`` at a time, checking the vacant cells the codeword
    demands and copying the cells, stamped with ``M``, onto ``B``. When the codewords run out the
    rest of the board is appended and ``play`` resumes on ``NewBoard`` -- the head of the copy --
    with the placement recorded. Any mismatch on the way passes the solution stream through
    untouched (``otherwise``). The original's match/11 merely packs the ``j/7`` term; the pieces
    here build it themselves.
    """

    @clause
    def done(self, codes: Term, board: Term, b: Term, m: Term, j: Term) -> None:
        """The codewords are exhausted: close the copy and keep playing on it.

        match([], Board, Rest, _, j(NewBoard, Pieces, S0, S1, N, A, Code)) :- N1 := N+1 |
            Rest = Board, play(NewBoard, Pieces, S0, S1, N1, [[Code|N]|A]).
        """
        empty(codes)
        new_board, pieces, s0, s1, n, a, code = unstruct(j, 'j', 7)
        tell(b, board)
        play(new_board, pieces, s0, s1, n + 1, placed(code, n, a))

    @clause
    def ssssss1(self, codes: Term, board: Term, b: Term, m: Term, j: Term) -> None:
        """match([ssssss1|R], [X1,...,X6|Xs], B, M, J) :- B = [X1,...,X6|Bs], match(R, Xs, Bs, M, J)."""
        self.codeword('ssssss1', codes, board, b, m, j)

    @clause
    def ssssss2(self, codes: Term, board: Term, b: Term, m: Term, j: Term) -> None:
        """match([ssssss2|R], [X1,...,Xc|Xs], B, M, J) :- B = [X1,...,Xc|Bs], match(R, Xs, Bs, M, J)."""
        self.codeword('ssssss2', codes, board, b, m, j)

    @clause
    def vvssss1(self, codes: Term, board: Term, b: Term, m: Term, j: Term) -> None:
        """match([vvssss1|R], [v,v,X1,X2,X3,X4|Xs], B, M, J) :- B = [M,M,X1,X2,X3,X4|Bs], match(R, Xs, Bs, M, J)."""
        self.codeword('vvssss1', codes, board, b, m, j)

    @clause
    def vvvsss1(self, codes: Term, board: Term, b: Term, m: Term, j: Term) -> None:
        """match([vvvsss1|R], [v,v,v,X1,X2,X3|Xs], B, M, J) :- B = [M,M,M,X1,X2,X3|Bs], match(R, Xs, Bs, M, J)."""
        self.codeword('vvvsss1', codes, board, b, m, j)

    @clause
    def vvvvss1(self, codes: Term, board: Term, b: Term, m: Term, j: Term) -> None:
        """match([vvvvss1|R], [v,v,v,v,X1,X2|Xs], B, M, J) :- B = [M,M,M,M,X1,X2|Bs], match(R, Xs, Bs, M, J)."""
        self.codeword('vvvvss1', codes, board, b, m, j)

    @clause
    def vsssss1(self, codes: Term, board: Term, b: Term, m: Term, j: Term) -> None:
        """match([vsssss1|R], [v,X1,X2,X3,X4,X5|Xs], B, M, J) :- B = [M,X1,X2,X3,X4,X5|Bs], match(R, Xs, Bs, M, J)."""
        self.codeword('vsssss1', codes, board, b, m, j)

    @clause
    def vsssss2(self, codes: Term, board: Term, b: Term, m: Term, j: Term) -> None:
        """Twelve cells, the first and the seventh vacant.

        match([vsssss2|R], [v,X1,...,X5, v,X6,...,Xa|Xs], B, M, J) :-
            B = [M,X1,...,X5, M,X6,...,Xa|Bs], match(R, Xs, Bs, M, J).
        """
        self.codeword('vsssss2', codes, board, b, m, j)

    @clause
    def vsssss3(self, codes: Term, board: Term, b: Term, m: Term, j: Term) -> None:
        """Eighteen cells, the first, seventh and thirteenth vacant.

        match([vsssss3|R], [v,X1,...,X5, v,X6,...,Xa, v,Xb,...,Xf|Xs], B, M, J) :-
            B = [M,X1,...,X5, M,X6,...,Xa, M,Xb,...,Xf|Bs], match(R, Xs, Bs, M, J).
        """
        self.codeword('vsssss3', codes, board, b, m, j)

    @otherwise
    def no_fit(self, codes: Term, board: Term, b: Term, m: Term, j: Term) -> None:
        """Nothing matched: pass the solution stream through.

        otherwise. match(_, _, _, _, j(_, _, S0, S1, _, _, _)) :- S0 = S1.
        """
        _, _, s0, s1, _, _, _ = unstruct(j, 'j', 7)
        tell(s0, s1)

    def codeword(self, name: str, codes: Term, board: Term, b: Term, m: Term, j: Term) -> None:
        """The body the codeword clauses share: match ``name`` at the front of the board and copy it onto B."""
        code, more = uncons(codes)
        guard(code == name)
        spec = CODEWORDS[name]
        cells, rest = head(board, spec)
        bs = fresh()
        tell(b, build(stamp(cells, spec, m), bs))
        self(more, rest, bs, m, j)


matcher = Match()


class DirectPiece(Relation):
    """pXYZ(Board, M, Pieces, S0, S1, N, A): an orientation that spells its footprint out in its head.

    ``spec`` is the head pattern, one character per cell from the front of the board (``v`` must
    be vacant, ``_`` is a don't-care that is copied along); ``drop`` is how many leading cells
    the new board omits -- the vacant cells of the first row, which the piece fills and ``play``
    never needs to see again.
    """

    def __init__(self, code: int, spec: str, drop: int) -> None:
        """Make the orientation tagged ``code`` (421 for 4x2x1, as in the original) with footprint ``spec``."""
        super().__init__()
        self.name = f'p{code}'
        self.code = code
        self.spec = spec
        self.drop = drop

    @clause
    def place(self, board: Term, m: Term, pieces: Term, s0: Term, s1: Term, n: Term, a: Term) -> None:
        """Place the piece at the front of the board and keep playing past it.

        p421([v,v,v,v,X1,X2, v,v,v,v|R], M, Pieces, S0, S1, N, A) :- N1 := N+1 |
            play([X1,X2, M,M,M,M|R], Pieces, S0, S1, N1, [[421|N]|A]).
        """
        cells, rest = head(board, self.spec)
        new_board = build(stamp(cells, self.spec, m)[self.drop :], rest)
        play(new_board, pieces, s0, s1, n + 1, placed(self.code, n, a))

    @otherwise
    def no_fit(self, board: Term, m: Term, pieces: Term, s0: Term, s1: Term, n: Term, a: Term) -> None:
        """The piece does not fit here: pass the solution stream through.

        otherwise. p421(_, _, _, S0, S1, _, _) :- S0 = S1.
        """
        tell(s0, s1)


class TemplatePiece(Relation):
    """pXYZ(Board, M, Pieces, S0, S1, N, A): an orientation that describes its footprint to ``match``."""

    def __init__(self, code: int, codewords: Sequence[str]) -> None:
        """Make the orientation tagged ``code`` whose footprint ``match`` reads from ``codewords``."""
        super().__init__()
        self.name = f'p{code}'
        self.code = code
        self.codewords = tuple(codewords)

    @clause
    def place(self, board: Term, m: Term, pieces: Term, s0: Term, s1: Term, n: Term, a: Term) -> None:
        """Hand the footprint to match, which keeps playing on a fit.

        p142(Board, M, Pieces, S0, S1, N, A) :-
            match([vsssss2, vsssss2, ssssss1, vsssss2, vsssss2],
                  Board, NewBoard, M, NewBoard, Pieces, S0, S1, N, A, 142).
        """
        new_board = fresh()
        matcher(
            build(self.codewords, nil()), board, new_board, m, struct('j', new_board, pieces, s0, s1, n, a, self.code)
        )


# The orientations of each piece, in the original's order (p321 = 3x2x1: X by Y by Z cells).
p321 = DirectPiece(321, 'vvv___vvv', 3)
p213 = TemplatePiece(213, ('vvssss1', 'ssssss2', 'ssssss2', 'vvssss1', 'ssssss2', 'ssssss2', 'vvssss1'))
p132 = TemplatePiece(132, ('vsssss3', 'ssssss2', 'vsssss3'))
p231 = DirectPiece(231, 'vv____vv____vv', 2)
p312 = TemplatePiece(312, ('vvvsss1', 'ssssss2', 'ssssss2', 'vvvsss1'))
p123 = TemplatePiece(123, ('vsssss2', 'ssssss2', 'ssssss1', 'vsssss2', 'ssssss2', 'ssssss1', 'vsssss2'))

p431 = DirectPiece(431, 'vvvv__vvvv__vvvv', 4)
p143 = TemplatePiece(143, ('vsssss2', 'vsssss2', 'ssssss1', 'vsssss2', 'vsssss2', 'ssssss1', 'vsssss2', 'vsssss2'))
p341 = DirectPiece(341, 'vvv___vvv___vvv___vvv', 3)
p413 = TemplatePiece(413, ('vvvvss1', 'ssssss2', 'ssssss2', 'vvvvss1', 'ssssss2', 'ssssss2', 'vvvvss1'))

p331 = DirectPiece(331, 'vvv___vvv___vvv', 3)
p313 = TemplatePiece(313, ('vvvsss1', 'ssssss2', 'ssssss2', 'vvvsss1', 'ssssss2', 'ssssss2', 'vvvsss1'))
p133 = TemplatePiece(133, ('vsssss3', 'ssssss2', 'vsssss3', 'ssssss2', 'vsssss3'))

p421 = DirectPiece(421, 'vvvv__vvvv', 4)
p142 = TemplatePiece(142, ('vsssss2', 'vsssss2', 'ssssss1', 'vsssss2', 'vsssss2'))
p241 = DirectPiece(241, 'vv____vv____vv____vv', 2)
p412 = TemplatePiece(412, ('vvvvss1', 'ssssss2', 'ssssss2', 'vvvvss1'))


class Fill(Relation):
    """fillK(Pieces, Board, S0, Sk, N, A): try every orientation of the next piece of kind K at the front of the board.

    ``Pieces`` lists the remaining marks of the four kinds; the K-th list gives up its head ``M``
    and the orientations are chained through the solution stream ``S0, S1, ..., Sk``. The
    original writes fill1 .. fill4 out by hand; here one relation is parameterised by K.
    """

    def __init__(self, kind: int, orientations: Sequence[Relation]) -> None:
        """Make the filler for the ``kind``-th piece list, with its ``orientations`` in the original's order."""
        super().__init__()
        self.name = f'fill{kind + 1}'
        self.kind = kind
        self.orientations = tuple(orientations)

    @clause
    def place(self, pieces: Term, board: Term, s0: Term, sk: Term, n: Term, a: Term) -> None:
        """Take the kind's next mark and try each orientation with it.

        fill1([[M|P1], P2, P3, P4], Board, S0, S6, N, A) :- Pieces = [P1,P2,P3,P4],
            p321(Board, M, Pieces, S0, S1, N, A), p213(Board, M, Pieces, S1, S2, N, A), ...,
            p123(Board, M, Pieces, S5, S6, N, A).
        """
        kinds = four(pieces)
        m, rest = uncons(kinds[self.kind])
        kinds[self.kind] = rest
        remaining = build(kinds, nil())
        links = [s0, *(fresh() for _ in self.orientations[1:]), sk]
        for orientation, (before, after) in zip(self.orientations, pairwise(links), strict=True):
            orientation(board, m, remaining, before, after, n, a)

    @clause
    def none_left(self, pieces: Term, board: Term, s0: Term, s1: Term, n: Term, a: Term) -> None:
        """fill1([[], _, _, _], _, S0, S1, _, _) :- S0 = S1."""
        empty(four(pieces)[self.kind])
        tell(s0, s1)


class Play(Relation):
    """play(Board, Pieces, S0, S1, N, A): the packings reachable from Board, as the difference list S0 .. S1."""

    fill1 = Fill(0, (p321, p213, p132, p231, p312, p123))
    fill2 = Fill(1, (p431, p143, p341, p413))
    fill3 = Fill(2, (p331, p313, p133))
    fill4 = Fill(3, (p421, p142, p241, p412))

    @clause
    def solved(self, board: Term, pieces: Term, s0: Term, s1: Term, n: Term, a: Term) -> None:
        """play([], _, S0, S1, _, A) :- S0 = [A|S1]."""
        empty(board)
        tell(s0, cons(a, s1))

    @clause
    def fill(self, board: Term, pieces: Term, s0: Term, s4: Term, n: Term, a: Term) -> None:
        """A vacant spot: try to fill it with each kind of piece.

        play(Board, Pieces, S0, S4, N, A) :- [v|_] = Board |
            fill1(Pieces, Board, S0, S1, N, A), fill2(Pieces, Board, S1, S2, N, A),
            fill3(Pieces, Board, S2, S3, N, A), fill4(Pieces, Board, S3, S4, N, A).
        """
        cell, _ = uncons(board)
        guard(cell == 'v')
        s1, s2, s3 = fresh(), fresh(), fresh()
        self.fill1(pieces, board, s0, s1, n, a)
        self.fill2(pieces, board, s1, s2, n, a)
        self.fill3(pieces, board, s2, s3, n, a)
        self.fill4(pieces, board, s3, s4, n, a)

    @otherwise
    def skip(self, board: Term, pieces: Term, s0: Term, s1: Term, n: Term, a: Term) -> None:
        """Not a vacant cell: move on.

        otherwise. play([_|Rest], Pieces, S0, S1, N, A) :- N1 := N+1, play(Rest, Pieces, S0, S1, N1, A).
        """
        _, rest = uncons(board)
        self(rest, pieces, s0, s1, n + 1, a)


play = Play()


class MakeBoard(Relation):
    """make_board(X): the 120-cell board -- the chip in the corner, the vacant cells and the z sentinels."""

    @clause
    def board(self, x: Term) -> None:
        """make_board(X) :- X = [z,v,v,v,v,z, v,v,v,v,v,z, ..., z,z,z,z,z,z]."""
        tell(x, build(BOARD, nil()))


class Go(Relation):
    """go(N): N is the number of packings."""

    make_board = MakeBoard()
    count = Count()

    @clause
    def solve(self, n: Term) -> None:
        """go(N) :- make_board(Board), play(Board, [[a,b,c],[d,e],[f],[g]], L, [], 0, []), count(L, N)."""
        board = fresh()
        self.make_board(board)
        solutions = fresh()
        play(board, build([build(kind, nil()) for kind in PIECES], nil()), solutions, nil(), 0, nil())
        self.count(solutions, n)


go = Go()


def count_packings(board: Sequence[str], pieces: Sequence[Sequence[str]]) -> int:
    """Count the packings of ``board`` -- cells as in ``BOARD`` -- with ``pieces``, marks per kind as in ``PIECES``.

    The body of ``go`` with its two constants as parameters, so that smaller puzzles can be posed.
    """
    with session() as engine:
        solutions = Var()
        play(build(board, nil()), build([build(kind, nil()) for kind in pieces], nil()), solutions, nil(), 0, nil())
        engine.run()
    return len(to_list(solutions))


def main() -> None:
    """Run ``go(N)`` as puzzle.kl1's main does and print N."""
    print(go())


if __name__ == '__main__':
    main()
