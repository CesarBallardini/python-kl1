"""KL1 "counterfeit" Game of Life on a torus, ported to python-kl1 with the clause DSL.

Faithful port of ``examples/life.kl1`` (GOTO 1987 / A. Imai 1991): a two-dimensional torus
of **cell processes**, each linked to its four neighbours by streams (the original uses four
neighbours, not eight, on purpose), with **no world clock** -- a cell advances a generation as
soon as one state from each neighbour has arrived. The entry point counts the live cells
after ``G`` generations::

    go(N) :- life(120,38,38,4,4,L), count_1(L,N).

    life(G,X,Y,DivX,DivY,R) :- true |
        init(X,Y,X,Y,Sinit),
        Config = kumon(X,Y,DivX,DivY),
        make_row(X,Y,Config,G,Sinit,NS1,NS1,NS2,NS2,R,[]).

    init(X,Y,TX,TY,List) :- X > 0 | init_col(X,Y,TX,TY,ColL,X), List = [ColL|List1], init(~(X-1),Y,TX,TY,List1).
    init(0,Y,TX,TY,List) :- true | List = [].
    init_col(X,Y,TX,TY,List,PrevNum) :- Y > 0 |
        rand_0_or_1(X,Y,PrevNum,Rand,NewNum), List = [Rand|List1], init_col(X,~(Y-1),TX,TY,List1,NewNum).
    init_col(X,0,TX,TY,List,_) :- true | List = [].
    rand_0_or_1(X,Y,PrevNum,Rand,NewNum) :- integer(X), integer(Y), integer(PrevNum) |
        NewNum := ( PrevNum >> 3 ) + ( X << 2 ) + ( Y >> 2 ), Rand := NewNum mod 2.

    cell(I,N1,S1,N2,S2,E1,W1,E2,W2,R,G) :- true |
        N2=[I|On], S1=[I|Os], W2=[I|Ow], E1=[I|Oe],
        cell1(I,N1,S2,W1,E2,On,Os,Ow,Oe,R,G).
    cell1(X,[N|Ni],[S|Si],[E|Ei],[W|Wi],On,Os,Ow,Oe,R,G) :- G > 0, G1:=G-1, T1:=S+N, T2:=E+W, T:=T1+T2 |
        change(X,T,Y), On=[Y|On1], Os=[Y|Os1], Ow=[Y|Ow1], Oe=[Y|Oe1],
        cell1(Y,Ni,Si,Ei,Wi,On1,Os1,Ow1,Oe1,R,G1)@lower_priority.
    cell1(X,_,_,_,_,On,Os,Ow,Oe,R,0) :- true | On=[],Os=[],Ow=[],Oe=[],R = X.

    change(0,0,Y) :- true | Y = 1.      change(1,0,Y) :- true | Y = 0.
    change(0,1,Y) :- true | Y = 0.      change(1,1,Y) :- true | Y = 1.
    change(0,2,Y) :- true | Y = 1.      change(1,2,Y) :- true | Y = 0.
    change(0,3,Y) :- true | Y = 0.      change(1,3,Y) :- true | Y = 1.
    change(0,4,Y) :- true | Y = 1.      change(1,4,Y) :- true | Y = 0.

The wiring builds the grid one column at a time. ``make_row`` walks the columns, threading two
**lists of streams** (one stream per cell, one list per direction) from each column to the
next; at the end ``connect_row`` splices the last column's lists onto the first column's --
the east/west wrap of the torus. ``make_col`` walks the cells of a column, threading two
streams from each cell to the next and splicing the last cell's onto the first's -- the
north/south wrap. Every cell first emits its initial state on its four output streams
(``cell``), then runs ``G`` rounds of ``cell1``: read one state from each of the four inputs,
apply ``change`` to its own state ``X`` and the neighbour sum ``T``, emit the new state; at
``G = 0`` it closes its outputs and reports its final state ``R``. ``count_1`` / ``count_sub``
count the ones in the resulting list of columns.

Substitutions, each noted where it happens:

- The DSL has no shifts: ``PrevNum >> 3`` is ``prev // 8``, ``X << 2`` is ``x * 4``,
  ``Y >> 2`` is ``y // 4`` (every operand is non-negative, so they agree).
- ``@lower_priority`` is dropped: the engine has no priorities (it was a scheduling hint).
- ``Config = kumon(X,Y,DivX,DivY)`` and ``compute_node`` only chose a cluster for each process
  (``Node = 0`` in this single-cluster version) and ``TX`` / ``TY`` are threaded but never
  read, so ``DivX``, ``DivY``, ``Config``, ``TX``, ``TY`` and the ``X`` / ``Y`` counters of
  ``make_row`` / ``make_col`` (used only by ``compute_node``) are omitted: ``life(G, X, Y, R)``.
  Clause docstrings below show the clauses in that reduced arity.
- The ``integer/1`` guards of ``rand_0_or_1`` are dropped: ``tell`` already waits for its
  operands, and here they are always bound.
- ``:=`` steps (``G1 := G-1``, ``~(Y-1)``, ``T := ...``) are explicit ``tell``s into fresh
  variables, as in the original, rather than nested expressions.
- The ``change`` table is kept as its ten clauses; it is the closed form ``Y = (X + T + 1) mod 2``.

The program is determinate, so its answer equals a lockstep (synchronous) simulation of the
same torus and rule -- what the test compares it against. Run it with
``uv run python examples/life.py`` (the original's 120 generations of a 38-by-38 torus).
"""

from python_kl1.dsl import Relation, Term, clause, cons, empty, fresh, guard, nil, tell, uncons


class Rand01(Relation):
    """rand_0_or_1(X, Y, PrevNum, Rand, NewNum): the original's deterministic 0/1 generator."""

    @clause
    def go(self, x: Term, y: Term, prev: Term, rand: Term, new: Term) -> None:
        """rand_0_or_1(X,Y,PrevNum,Rand,NewNum) :- integer(X), integer(Y), integer(PrevNum) | ...

        ... NewNum := (PrevNum >> 3) + (X << 2) + (Y >> 2), Rand := NewNum mod 2.
        """
        tell(new, prev // 8 + x * 4 + y // 4)  # >> 3, << 2, >> 2 on non-negative ints
        tell(rand, new % 2)


class InitCol(Relation):
    """init_col(X, Y, List, PrevNum): the initial states of column X, for cells Y, Y-1, ..., 1."""

    rand_0_or_1 = Rand01()

    @clause
    def cell(self, x: Term, y: Term, cells: Term, prev: Term) -> None:
        """init_col(X,Y,[Rand|List1],Prev) :- Y > 0 | rand_0_or_1(X,Y,Prev,Rand,New), init_col(X,Y-1,List1,New)."""
        guard(y > 0)
        rand, new, rest, y1 = fresh(), fresh(), fresh(), fresh()
        self.rand_0_or_1(x, y, prev, rand, new)
        tell(cells, cons(rand, rest))
        tell(y1, y - 1)
        self(x, y1, rest, new)

    @clause
    def done(self, x: Term, y: Term, cells: Term, prev: Term) -> None:
        """init_col(X,0,List,_) :- List = []."""
        guard(y == 0)
        tell(cells, nil())


class Init(Relation):
    """init(X, Y, List): the initial grid -- X columns (x = X, ..., 1), each a list of Y states."""

    init_col = InitCol()

    @clause
    def column(self, x: Term, y: Term, cols: Term) -> None:
        """init(X,Y,[ColL|List1]) :- X > 0 | init_col(X,Y,ColL,X), init(X-1,Y,List1)."""
        guard(x > 0)
        col, rest, x1 = fresh(), fresh(), fresh()
        self.init_col(x, y, col, x)
        tell(cols, cons(col, rest))
        tell(x1, x - 1)
        self(x1, y, rest)

    @clause
    def done(self, x: Term, y: Term, cols: Term) -> None:
        """init(0,Y,List) :- List = []."""
        guard(x == 0)
        tell(cols, nil())


class Change(Relation):
    """change(X, T, Y): the state-transition table, Y = (X + T + 1) mod 2, kept as its ten clauses."""

    @clause
    def c00(self, x: Term, t: Term, y: Term) -> None:
        """change(0,0,Y) :- Y = 1."""
        guard(x == 0)
        guard(t == 0)
        tell(y, 1)

    @clause
    def c01(self, x: Term, t: Term, y: Term) -> None:
        """change(0,1,Y) :- Y = 0."""
        guard(x == 0)
        guard(t == 1)
        tell(y, 0)

    @clause
    def c02(self, x: Term, t: Term, y: Term) -> None:
        """change(0,2,Y) :- Y = 1."""
        guard(x == 0)
        guard(t == 2)
        tell(y, 1)

    @clause
    def c03(self, x: Term, t: Term, y: Term) -> None:
        """change(0,3,Y) :- Y = 0."""
        guard(x == 0)
        guard(t == 3)
        tell(y, 0)

    @clause
    def c04(self, x: Term, t: Term, y: Term) -> None:
        """change(0,4,Y) :- Y = 1."""
        guard(x == 0)
        guard(t == 4)
        tell(y, 1)

    @clause
    def c10(self, x: Term, t: Term, y: Term) -> None:
        """change(1,0,Y) :- Y = 0."""
        guard(x == 1)
        guard(t == 0)
        tell(y, 0)

    @clause
    def c11(self, x: Term, t: Term, y: Term) -> None:
        """change(1,1,Y) :- Y = 1."""
        guard(x == 1)
        guard(t == 1)
        tell(y, 1)

    @clause
    def c12(self, x: Term, t: Term, y: Term) -> None:
        """change(1,2,Y) :- Y = 0."""
        guard(x == 1)
        guard(t == 2)
        tell(y, 0)

    @clause
    def c13(self, x: Term, t: Term, y: Term) -> None:
        """change(1,3,Y) :- Y = 1."""
        guard(x == 1)
        guard(t == 3)
        tell(y, 1)

    @clause
    def c14(self, x: Term, t: Term, y: Term) -> None:
        """change(1,4,Y) :- Y = 0."""
        guard(x == 1)
        guard(t == 4)
        tell(y, 0)


class Cell1(Relation):
    """cell1(X, Ni, Si, Ei, Wi, On, Os, Ow, Oe, R, G): run G generations of one cell, then report its state R."""

    change = Change()

    @clause
    def generation(
        self, x: Term, ns: Term, ss: Term, es: Term, ws: Term, on: Term, os: Term, ow: Term, oe: Term, r: Term, g: Term
    ) -> None:
        """cell1(X,[N|Ni],[S|Si],[E|Ei],[W|Wi],On,Os,Ow,Oe,R,G) :- G > 0, G1:=G-1, T1:=S+N, T2:=E+W, T:=T1+T2 | ...

        ... change(X,T,Y), On=[Y|On1], Os=[Y|Os1], Ow=[Y|Ow1], Oe=[Y|Oe1],
        cell1(Y,Ni,Si,Ei,Wi,On1,Os1,Ow1,Oe1,R,G1)@lower_priority.
        """
        guard(g > 0)
        n, ni = uncons(ns)
        s, si = uncons(ss)
        e, ei = uncons(es)
        w, wi = uncons(ws)
        t, y, g1 = fresh(), fresh(), fresh()
        tell(t, n + s + e + w)  # T1 := S+N, T2 := E+W, T := T1+T2
        tell(g1, g - 1)
        self.change(x, t, y)
        on1, os1, ow1, oe1 = fresh(), fresh(), fresh(), fresh()
        tell(on, cons(y, on1))
        tell(os, cons(y, os1))
        tell(ow, cons(y, ow1))
        tell(oe, cons(y, oe1))
        self(y, ni, si, ei, wi, on1, os1, ow1, oe1, r, g1)  # @lower_priority: no priorities in this engine

    @clause
    def final(
        self, x: Term, ns: Term, ss: Term, es: Term, ws: Term, on: Term, os: Term, ow: Term, oe: Term, r: Term, g: Term
    ) -> None:
        """cell1(X,_,_,_,_,On,Os,Ow,Oe,R,0) :- On=[], Os=[], Ow=[], Oe=[], R = X."""
        guard(g == 0)
        tell(on, nil())
        tell(os, nil())
        tell(ow, nil())
        tell(oe, nil())
        tell(r, x)


class Cell(Relation):
    """cell(I, N1, S1, N2, S2, E1, W1, E2, W2, R, G): a cell with initial state I, four inputs and four outputs."""

    cell1 = Cell1()

    @clause
    def start(
        self, i: Term, n1: Term, s1: Term, n2: Term, s2: Term, e1: Term, w1: Term, e2: Term, w2: Term, r: Term, g: Term
    ) -> None:
        """cell(I,N1,S1,N2,S2,E1,W1,E2,W2,R,G) :- N2=[I|On], S1=[I|Os], W2=[I|Ow], E1=[I|Oe], ...

        ... cell1(I,N1,S2,W1,E2,On,Os,Ow,Oe,R,G). Outputs: N2, S1, W2, E1; inputs: N1, S2, W1, E2.
        """
        on, os, ow, oe = fresh(), fresh(), fresh(), fresh()
        tell(n2, cons(i, on))
        tell(s1, cons(i, os))
        tell(w2, cons(i, ow))
        tell(e1, cons(i, oe))
        self.cell1(i, n1, s2, w1, e2, on, os, ow, oe, r, g)


class MakeCol(Relation):
    """make_col(G, I_col, Ns1, Sn1, Ns2, Sn2, Ew1, We1, Ew2, We2, Ch, Ct): a column of cells, wired north/south."""

    cell = Cell()

    @clause
    def cell_at(
        self,
        g: Term,
        cells: Term,
        ns1: Term,
        sn1: Term,
        ns2: Term,
        sn2: Term,
        ew1: Term,
        we1: Term,
        ew2: Term,
        we2: Term,
        ch: Term,
        ct: Term,
    ) -> None:
        """make_col(G,[I|Is],[N1|Ns1],[S1|Ssn1],[N2|Ns2],[S2|Ssn2],Ew1,We1,Ew2,We2,[R|Chs],Ct) :- ...

        ... cell(I,N1,S1,N2,S2,Ew1,WE1,Ew2,WE2,R,G), make_col(G,Is,Ns1,Ssn1,Ns2,Ssn2,WE1,We1,WE2,We2,Chs,Ct).
        """
        i, rest = uncons(cells)
        n1, ns1_rest = uncons(ns1)
        n2, ns2_rest = uncons(ns2)
        s1, ssn1, s2, ssn2 = fresh(), fresh(), fresh(), fresh()
        tell(sn1, cons(s1, ssn1))
        tell(sn2, cons(s2, ssn2))
        r, chs = fresh(), fresh()
        tell(ch, cons(r, chs))
        we1_next, we2_next = fresh(), fresh()  # WE1, WE2: shared with the next cell (its east side)
        self.cell(i, n1, s1, n2, s2, ew1, we1_next, ew2, we2_next, r, g)
        self(g, rest, ns1_rest, ssn1, ns2_rest, ssn2, we1_next, we1, we2_next, we2, chs, ct)

    @clause
    def wrap(
        self,
        g: Term,
        cells: Term,
        ns1: Term,
        sn1: Term,
        ns2: Term,
        sn2: Term,
        ew1: Term,
        we1: Term,
        ew2: Term,
        we2: Term,
        ch: Term,
        ct: Term,
    ) -> None:
        """make_col(_,[],_,Sn1,_,Sn2,Ew1,We1,Ew2,We2,Ch,Ct) :- Ch = Ct, Ew1 = We1, Ew2 = We2, Sn1 = [], Sn2 = []."""
        empty(cells)
        tell(ch, ct)
        tell(ew1, we1)  # Ew1 = We1: the last cell's west input is the first cell's east output (torus)
        tell(we2, ew2)  # Ew2 = We2: the first cell's east input is the last cell's west output (torus)
        tell(sn1, nil())
        tell(sn2, nil())


class ConnectRow(Relation):
    """connect_row(Ns1, Sn1, Ns2, Sn2, S1, S2): link the last column's streams to the first column's, cell by cell."""

    @clause
    def link(self, ns1: Term, sn1: Term, ns2: Term, sn2: Term, s1: Term, s2: Term) -> None:
        """connect_row([N1|Ns1],Sn1,[N2|Ns2],Sn2,S1,S2) :- N1 = S1, N2 = S2, Sn1=[Ss1|Ssn1], Sn2=[Ss2|Ssn2], ...

        ... connect_row(Ns1,Ssn1,Ns2,Ssn2,Ss1,Ss2).
        """
        n1, ns1_rest = uncons(ns1)
        n2, ns2_rest = uncons(ns2)
        tell(s1, n1)  # N1 = S1: the first column reads (S1) what the last column writes (N1)
        tell(n2, s2)  # N2 = S2: the last column reads (N2) what the first column writes (S2)
        ss1, ssn1, ss2, ssn2 = fresh(), fresh(), fresh(), fresh()
        tell(sn1, cons(ss1, ssn1))
        tell(sn2, cons(ss2, ssn2))
        self(ns1_rest, ssn1, ns2_rest, ssn2, ss1, ss2)

    @clause
    def done(self, ns1: Term, sn1: Term, ns2: Term, sn2: Term, s1: Term, s2: Term) -> None:
        """connect_row([],_,[],_,_,_)."""
        empty(ns1)
        empty(ns2)


class MakeRow(Relation):
    """make_row(G, Init, Ns1, Sn1, Ns2, Sn2, Rh, Rt): spawn the columns, wired east/west; Rh/Rt is the result list."""

    make_col = MakeCol()
    connect_row = ConnectRow()

    @clause
    def column(self, g: Term, cols: Term, ns1: Term, sn1: Term, ns2: Term, sn2: Term, rh: Term, rt: Term) -> None:
        """make_row(G,[I_col|Is],Ns1,Sn1,Ns2,Sn2,[C|Rhs],Rt) :- ...

        ... make_col(G,I_col,Ns1,S1,Ns2,S2,EW1,EW1,EW2,EW2,C,[]), make_row(G,Is,S1,Sn1,S2,Sn2,Rhs,Rt).
        """
        col, rest = uncons(cols)
        c, rhs = fresh(), fresh()
        tell(rh, cons(c, rhs))
        s1, s2, ew1, ew2 = fresh(), fresh(), fresh(), fresh()
        self.make_col(g, col, ns1, s1, ns2, s2, ew1, ew1, ew2, ew2, c, nil())
        self(g, rest, s1, sn1, s2, sn2, rhs, rt)

    @clause
    def wrap(self, g: Term, cols: Term, ns1: Term, sn1: Term, ns2: Term, sn2: Term, rh: Term, rt: Term) -> None:
        """make_row(_,[],Ns1,Sn1,Ns2,Sn2,Rh,Rt) :- Rh = Rt, Sn1=[S1|Ssn1], Sn2=[S2|Ssn2], ...

        ... connect_row(Ns1,Ssn1,Ns2,Ssn2,S1,S2) -- splice the last column's lists onto the first column's (torus).
        """
        empty(cols)
        tell(rh, rt)
        s1, ssn1, s2, ssn2 = fresh(), fresh(), fresh(), fresh()
        tell(sn1, cons(s1, ssn1))
        tell(sn2, cons(s2, ssn2))
        self.connect_row(ns1, ssn1, ns2, ssn2, s1, s2)


class CountSub(Relation):
    """count_sub(L, N, NFinal): NFinal = N + the number of 1s in L."""

    @clause
    def one(self, states: Term, n: Term, nf: Term) -> None:
        """count_sub([1|L],N,NFinal) :- count_sub(L,N+1,NFinal)."""
        h, rest = uncons(states)
        guard(h == 1)
        n1 = fresh()
        tell(n1, n + 1)
        self(rest, n1, nf)

    @clause
    def zero(self, states: Term, n: Term, nf: Term) -> None:
        """count_sub([0|L],N,NFinal) :- count_sub(L,N,NFinal)."""
        h, rest = uncons(states)
        guard(h == 0)
        self(rest, n, nf)

    @clause
    def done(self, states: Term, n: Term, nf: Term) -> None:
        """count_sub([],N,NFinal) :- NFinal = N."""
        empty(states)
        tell(nf, n)


class Count1(Relation):
    """count_1(L, N): N is the number of 1s in the list of columns L."""

    count_sub = CountSub()

    @clause
    def column(self, cols: Term, n: Term) -> None:
        """count_1([SubL|L],N) :- count_sub(SubL,0,SubN), count_1(L,N2), N := SubN + N2."""
        sub, rest = uncons(cols)
        subn, n2 = fresh(), fresh()
        self.count_sub(sub, 0, subn)
        self(rest, n2)
        tell(n, subn + n2)

    @clause
    def done(self, cols: Term, n: Term) -> None:
        """count_1([],N) :- N = 0."""
        empty(cols)
        tell(n, 0)


class Life(Relation):
    """life(G, X, Y, R): run G generations on an X-by-Y torus; R is the list of columns of final states."""

    init = Init()
    make_row = MakeRow()

    @clause
    def go(self, g: Term, x: Term, y: Term, r: Term) -> None:
        """life(G,X,Y,R) :- init(X,Y,Sinit), make_row(G,Sinit,NS1,NS1,NS2,NS2,R,[])."""
        sinit, ns1, ns2 = fresh(), fresh(), fresh()
        self.init(x, y, sinit)
        self.make_row(g, sinit, ns1, ns1, ns2, ns2, r, nil())


class Go(Relation):
    """go(G, X, Y, N): N is the number of live cells after G generations of an X-by-Y torus."""

    life = Life()
    count_1 = Count1()

    @clause
    def count(self, g: Term, x: Term, y: Term, n: Term) -> None:
        """go(N) :- life(120,38,38,4,4,L), count_1(L,N) -- with the sizes as arguments."""
        states = fresh()
        self.life(g, x, y, states)
        self.count_1(states, n)


go = Go()

GENERATIONS, WIDTH, HEIGHT = 120, 38, 38  # life.kl1's go/1


def life_count(g: int, x: int, y: int) -> int:
    """Return the number of live cells after ``g`` generations of the ``x``-by-``y`` torus (go/1 with sizes)."""
    count = go(g, x, y)
    if not isinstance(count, int):
        raise TypeError(f'life did not run to completion: {count!r}')
    return count


def main() -> None:
    """Print the live-cell count for life.kl1's go/1: 120 generations of the 38-by-38 torus."""
    print(life_count(GENERATIONS, WIDTH, HEIGHT))


if __name__ == '__main__':
    main()
