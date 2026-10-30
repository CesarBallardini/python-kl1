r"""KL1 turtles card puzzle via **layered streams**, ported to python-kl1 with the clause DSL.

Faithful port of ``examples/turtles.kl1`` (E. Tick, 1989; "layered-streams: nil check"):
nine square cards, each edge showing the head (``h``) or tail (``t``) of a turtle in one of
four colours (``g``, ``p``, ``o``, ``b``), are laid on a 3x3 grid so that every pair of touching
edges joins a head to a tail of the same colour. ``go(N, A)`` finds the N = 4 solutions::

    go(N,A) :- cards(C), constraints(D), spawn(D,C,begin,A), count(A,N).

    spawn([],_C,S0,S2) :- fromLStoL(S0,S1),final(S1,S2).
    spawn([D|Ds],C,S0,S2) :- orient(1,D,C,S0,S1),spawn(Ds,C,S1,S2).

    orient(_,_,[],_,S) :- S=[].
    orient(I,D,[C|Cs],In,S) :- I>1, I1 := I+1 | rotate(I,D,C,In,S,S1), orient(I1,D,Cs,In,S1).
    orient(1,D,[[T,R,B,L]|Cs],In,S) :- set(In,card(1,T,R,B,L),D,S,S1), orient(2,D,Cs,In,S1).

    set(In,Card,D,Out,T) :-  Out=[[Card|Out1]|T],filter(D,In,Card,Out1).

    filter(_,[],_,O) :- O=[].
    filter(_,begin,_,O) :- O=begin.
    filter(D,[[card(J,_,_,_,_)|_]|Is],C,O) :- card(J,_,_,_,_)=C | filter(D,Is,C,O).
    otherwise.
    filter([x|Ds],[[C1|Ts]|Is],C2,O) :- filter1(yes,C1,C2,Is,Ts,x,Ds,O).
    filter([t|Ds],[[C1|Ts]|Is],C2,O) :- card(_,T,_,_,_)=C1, card(_,_,_,B,_)=C2 |
        flip(T,B,Status), filter1(Status,C1,C2,Is,Ts,t,Ds,O).
    ...                                               % r, b, l likewise

    filter1( no,    _,Card2,Is, _,D,Ds,O) :- filter([D|Ds],Is,Card2,O).
    filter1(yes,Card1,Card2,Is,Ts,D,Ds,O) :-
        filter(Ds,Ts,Card2,O1), send(O1,Card1,O,Os), filter([D|Ds],Is,Card2,Os).

    send([],_,S0,S1) :- S0=S1.
    otherwise.
    send( T,H,S0,S1) :- S0=[[H|T]|S1].

The search is one layered stream (as in ``qlay``): position k's layer is a list of
``[Card | Substream]`` items, the substream being the surviving layer of position k-1 under
that card, down to the atom ``begin``. Constraint row k says how the card at position k must
meet each earlier card, most recent first -- ``x`` (no contact), ``t``/``r``/``b``/``l`` (the
earlier card's top/right/bottom/left edge against the new card's opposite edge). ``filter``
prunes the incoming layer against a newly placed card; ``send`` drops a card whose surviving
substream came back empty -- the *nil check* of the title. Card 1 is placed in one
orientation only, which removes the grid's rotational symmetry.

Substitutions, in source order:

- **The three ``otherwise.``** become :func:`~python_kl1.dsl.otherwise`, each on the first
  clause after it (the clauses that follow in its group stay ``@clause``): ``filter``'s on the
  ``x`` clause of the five constraint clauses, ``send``'s on its default, ``flip``'s on its
  ``no``. ``send``'s is the one a guard-free fallback could not render: its ``T`` is the output
  of a ``filter`` running concurrently, so the default must wait until ``T`` is known not to
  be ``[]``.
- **Guard unifications** such as ``card(J,_,_,_,_) = C`` (C already bound) become
  ``unstruct(c, 'card', 5)`` plus ``guard(j2 == j)``, or just ``unstruct`` to read an edge.
- **List head patterns** ``[T,R,B,L]`` and ``rearrange2``'s nine-element list go through
  :func:`elements`, which fails the clause on a length mismatch as a head unification would.
- **``N-T``** in ``rearrange1`` is the functor ``-(N, T)``, built with ``struct('-', n, t)``
  -- never ``n - t``, which would be arithmetic.
- **``cards/1`` and ``constraints/1``** are single-clause relations telling the constants
  (``CARDS`` and ``CONSTRAINTS``).
- **``main``**'s ``putt(A)`` prints the solutions in KL1 syntax (:func:`render`).

Run it with ``uv run python examples/turtles.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from python_kl1.core import Struct, Value, Var, deref, to_list
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

CARDS: tuple[tuple[str, str, str, str], ...] = (  # [Top, Right, Bottom, Left] per card, numbered 1..9
    ('tg', 'tp', 'hb', 'ho'),
    ('tg', 'tp', 'hb', 'ho'),
    ('tb', 'tp', 'hb', 'ho'),
    ('tg', 'hb', 'hp', 'to'),
    ('to', 'hb', 'hg', 'tp'),
    ('hg', 'hp', 'tb', 'to'),
    ('tb', 'tp', 'hg', 'ho'),
    ('tg', 'to', 'hg', 'hp'),
    ('to', 'tp', 'hg', 'hb'),
)

CONSTRAINTS: tuple[tuple[str, ...], ...] = (  # row k: how position k meets positions k-1, k-2, ..., 0
    (),
    ('t',),
    ('x', 'r'),
    ('t', 'r', 'x'),
    ('x', 'x', 'x', 'l'),
    ('t', 'x', 'x', 'l', 'x'),
    ('x', 'x', 'x', 'x', 'x', 'b'),
    ('l', 'x', 'b', 'x', 'x', 'x', 'x'),
    ('x', 'r', 'x', 'x', 'x', 'b', 'x', 'x'),
)


def build(items: Sequence[Operand]) -> Term:
    """The list term ``[items...]``."""
    result = nil()
    for item in reversed(items):
        result = cons(item, result)
    return result


def elements(term: Term, k: int) -> list[Term]:
    """Head pattern ``[X1, ..., Xk]``: exactly ``k`` elements (fails otherwise, suspends on unbound)."""
    items: list[Term] = []
    rest = term
    for _ in range(k):
        item, rest = uncons(rest)
        items.append(item)
    empty(rest)
    return items


def edges(card: Term) -> tuple[Term, Term, Term, Term, Term]:
    """Head pattern ``card(J, T, R, B, L)``: the card's number and its four edges."""
    j, top, right, bottom, left = unstruct(card, 'card', 5)
    return j, top, right, bottom, left


class Cards(Relation):
    """cards(Cards): the nine cards."""

    @clause
    def fact(self, c: Term) -> None:
        """cards(Cards) :- Cards=[[tg,tp,hb,ho],[tg,tp,hb,ho],[tb,tp,hb,ho], ...]."""
        tell(c, build([build(card) for card in CARDS]))


class Constraints(Relation):
    """constraints(D): one row per grid position, in placement order."""

    @clause
    def fact(self, d: Term) -> None:
        """constraints(D) :- D = [[],[t],[x,r],[t,r,x],[x,x,x,l],[t,x,x,l,x], ...]."""
        tell(d, build([build(row) for row in CONSTRAINTS]))


class Flip(Relation):
    """flip(A, B, S): S = yes if edges A and B join a head to a tail of the same colour, else no."""

    @clause
    def green(self, a: Term, b: Term, s: Term) -> None:
        """flip(tg,hg,S) :- S=yes."""
        guard(a == 'tg')
        guard(b == 'hg')
        tell(s, 'yes')

    @clause
    def pink(self, a: Term, b: Term, s: Term) -> None:
        """flip(tp,hp,S) :- S=yes."""
        guard(a == 'tp')
        guard(b == 'hp')
        tell(s, 'yes')

    @clause
    def orange(self, a: Term, b: Term, s: Term) -> None:
        """flip(to,ho,S) :- S=yes."""
        guard(a == 'to')
        guard(b == 'ho')
        tell(s, 'yes')

    @clause
    def blue(self, a: Term, b: Term, s: Term) -> None:
        """flip(tb,hb,S) :- S=yes."""
        guard(a == 'tb')
        guard(b == 'hb')
        tell(s, 'yes')

    @clause
    def green_back(self, a: Term, b: Term, s: Term) -> None:
        """flip(hg,tg,S) :- S=yes."""
        guard(a == 'hg')
        guard(b == 'tg')
        tell(s, 'yes')

    @clause
    def pink_back(self, a: Term, b: Term, s: Term) -> None:
        """flip(hp,tp,S) :- S=yes."""
        guard(a == 'hp')
        guard(b == 'tp')
        tell(s, 'yes')

    @clause
    def orange_back(self, a: Term, b: Term, s: Term) -> None:
        """flip(ho,to,S) :- S=yes."""
        guard(a == 'ho')
        guard(b == 'to')
        tell(s, 'yes')

    @clause
    def blue_back(self, a: Term, b: Term, s: Term) -> None:
        """flip(hb,tb,S) :- S=yes."""
        guard(a == 'hb')
        guard(b == 'tb')
        tell(s, 'yes')

    @otherwise
    def mismatch(self, a: Term, b: Term, s: Term) -> None:
        """The default -- otherwise. flip(_,_,S) :- S=no."""
        tell(s, 'no')


class Send(Relation):
    r"""send(T, H, S0, S1): keep the item ``[H|T]`` in the difference list S0\S1 unless T is ``[]``."""

    @clause
    def drop(self, t: Term, h: Term, s0: Term, s1: Term) -> None:
        """send([],_,S0,S1) :- S0=S1."""
        empty(t)
        tell(s0, s1)

    @otherwise
    def keep(self, t: Term, h: Term, s0: Term, s1: Term) -> None:
        """The default, once T is known not to be [] -- otherwise. send(T,H,S0,S1) :- S0=[[H|T]|S1]."""
        tell(s0, cons(cons(h, t), s1))


class Filter1(Relation):
    """filter1(Status, C1, C2, Is, Ts, D, Ds, O): act on flip's verdict for the earlier card C1."""

    @clause
    def no(self, status: Term, c1: Term, c2: Term, is_: Term, ts: Term, d: Term, ds: Term, o: Term) -> None:
        """filter1(no,_,Card2,Is,_,D,Ds,O) :- filter([D|Ds],Is,Card2,O)."""
        guard(status == 'no')
        _filter(cons(d, ds), is_, c2, o)

    @clause
    def yes(self, status: Term, c1: Term, c2: Term, is_: Term, ts: Term, d: Term, ds: Term, o: Term) -> None:
        """filter1(yes,Card1,Card2,Is,Ts,D,Ds,O) :- filter(Ds,Ts,Card2,O1), send(O1,Card1,O,Os), filter([D|Ds],...)."""
        guard(status == 'yes')
        o1 = fresh()
        os = fresh()
        _filter(ds, ts, c2, o1)
        _send(o1, c1, o, os)
        _filter(cons(d, ds), is_, c2, os)


class Filter(Relation):
    """filter(D, In, Card, O): the layer In, pruned against the newly placed Card under constraint row D."""

    @clause
    def at_end(self, d: Term, ins: Term, c: Term, o: Term) -> None:
        """filter(_,[],_,O) :- O=[]."""
        empty(ins)
        tell(o, nil())

    @clause
    def at_begin(self, d: Term, ins: Term, c: Term, o: Term) -> None:
        """filter(_,begin,_,O) :- O=begin."""
        guard(ins == 'begin')
        tell(o, 'begin')

    @clause
    def same_card(self, d: Term, ins: Term, c: Term, o: Term) -> None:
        """filter(D,[[card(J,_,_,_,_)|_]|Is],C,O) :- card(J,_,_,_,_)=C | filter(D,Is,C,O)."""
        item, is_ = uncons(ins)
        c1, _ts = uncons(item)
        j1 = edges(c1)[0]
        j2 = edges(c)[0]
        guard(j1 == j2)
        self(d, is_, c, o)

    @otherwise
    def no_contact(self, d: Term, ins: Term, c: Term, o: Term) -> None:
        """No contact -- otherwise. filter([x|Ds],[[C1|Ts]|Is],C2,O) :- filter1(yes,C1,C2,Is,Ts,x,Ds,O)."""
        how, ds = uncons(d)
        guard(how == 'x')
        item, is_ = uncons(ins)
        c1, ts = uncons(item)
        _filter1('yes', c1, c, is_, ts, how, ds, o)

    @clause
    def top(self, d: Term, ins: Term, c: Term, o: Term) -> None:
        """filter([t|Ds],[[C1|Ts]|Is],C2,O) :- card(_,T,_,_,_)=C1, card(_,_,_,B,_)=C2 | flip(T,B,S), ..."""
        how, ds = uncons(d)
        guard(how == 't')
        item, is_ = uncons(ins)
        c1, ts = uncons(item)
        status = fresh()
        _flip(edges(c1)[1], edges(c)[3], status)
        _filter1(status, c1, c, is_, ts, how, ds, o)

    @clause
    def right(self, d: Term, ins: Term, c: Term, o: Term) -> None:
        """filter([r|Ds],[[C1|Ts]|Is],C2,O) :- card(_,_,R,_,_)=C1, card(_,_,_,_,L)=C2 | flip(R,L,S), ..."""
        how, ds = uncons(d)
        guard(how == 'r')
        item, is_ = uncons(ins)
        c1, ts = uncons(item)
        status = fresh()
        _flip(edges(c1)[2], edges(c)[4], status)
        _filter1(status, c1, c, is_, ts, how, ds, o)

    @clause
    def bottom(self, d: Term, ins: Term, c: Term, o: Term) -> None:
        """filter([b|Ds],[[C1|Ts]|Is],C2,O) :- card(_,_,_,B,_)=C1, card(_,T,_,_,_)=C2 | flip(B,T,S), ..."""
        how, ds = uncons(d)
        guard(how == 'b')
        item, is_ = uncons(ins)
        c1, ts = uncons(item)
        status = fresh()
        _flip(edges(c1)[3], edges(c)[1], status)
        _filter1(status, c1, c, is_, ts, how, ds, o)

    @clause
    def left(self, d: Term, ins: Term, c: Term, o: Term) -> None:
        """filter([l|Ds],[[C1|Ts]|Is],C2,O) :- card(_,_,_,_,L)=C1, card(_,_,R,_,_)=C2 | flip(L,R,S), ..."""
        how, ds = uncons(d)
        guard(how == 'l')
        item, is_ = uncons(ins)
        c1, ts = uncons(item)
        status = fresh()
        _flip(edges(c1)[4], edges(c)[2], status)
        _filter1(status, c1, c, is_, ts, how, ds, o)


class Set(Relation):
    r"""set(In, Card, D, Out, T): add the item ``[Card | filter(D, In, Card)]`` to the layer Out\T."""

    @clause
    def place(self, ins: Term, card: Term, d: Term, out: Term, t: Term) -> None:
        """set(In,Card,D,Out,T) :- Out=[[Card|Out1]|T],filter(D,In,Card,Out1)."""
        out1 = fresh()
        tell(out, cons(cons(card, out1), t))
        _filter(d, ins, card, out1)


class Rotate(Relation):
    r"""rotate(I, D, [T,R,B,L], In, S0, S4): card I in its four orientations, in the layer S0\S4."""

    @clause
    def four_ways(self, i: Term, d: Term, c: Term, ins: Term, s0: Term, s4: Term) -> None:
        """rotate(I,D,[T,R,B,L],In,S0,S4) :- set(In,card(I,T,R,B,L),D,S0,S1), ... set(In,card(I,L,T,R,B),D,S3,S4)."""
        top, right, bottom, left = elements(c, 4)
        s1, s2, s3 = fresh(), fresh(), fresh()
        _set(ins, struct('card', i, top, right, bottom, left), d, s0, s1)
        _set(ins, struct('card', i, right, bottom, left, top), d, s1, s2)
        _set(ins, struct('card', i, bottom, left, top, right), d, s2, s3)
        _set(ins, struct('card', i, left, top, right, bottom), d, s3, s4)


class Orient(Relation):
    """orient(I, D, Cards, In, S): the layer S of every card I.. in every orientation, against In."""

    @clause
    def done(self, i: Term, d: Term, cs: Term, ins: Term, s: Term) -> None:
        """orient(_,_,[],_,S) :- S=[]."""
        empty(cs)
        tell(s, nil())

    @clause
    def rotated(self, i: Term, d: Term, cs: Term, ins: Term, s: Term) -> None:
        """orient(I,D,[C|Cs],In,S) :- I>1, I1 := I+1 | rotate(I,D,C,In,S,S1), orient(I1,D,Cs,In,S1)."""
        c, rest = uncons(cs)
        guard(i > 1)
        s1 = fresh()
        _rotate(i, d, c, ins, s, s1)
        self(i + 1, d, rest, ins, s1)

    @clause
    def first(self, i: Term, d: Term, cs: Term, ins: Term, s: Term) -> None:
        """orient(1,D,[[T,R,B,L]|Cs],In,S) :- set(In,card(1,T,R,B,L),D,S,S1), orient(2,D,Cs,In,S1)."""
        guard(i == 1)
        c, rest = uncons(cs)
        top, right, bottom, left = elements(c, 4)
        s1 = fresh()
        _set(ins, struct('card', 1, top, right, bottom, left), d, s, s1)
        self(2, d, rest, ins, s1)


class FromLStoS(Relation):
    r"""fromLStoS(LS, Stack, L0, L1): every root-to-``begin`` path of the layered stream LS, onto L0\L1."""

    @clause
    def at_begin(self, ls: Term, stack: Term, l0: Term, l1: Term) -> None:
        """fromLStoS(begin,Stack,L0,L1) :- L0=[Stack|L1]."""
        guard(ls == 'begin')
        tell(l0, cons(stack, l1))

    @clause
    def at_end(self, ls: Term, stack: Term, l0: Term, l1: Term) -> None:
        """fromLStoS([],_,L0,L1) :- L0=L1."""
        empty(ls)
        tell(l0, l1)

    @clause
    def step(self, ls: Term, stack: Term, l0: Term, l2: Term) -> None:
        """fromLStoS([[A|LS1]|Rest],Stack,L0,L2) :- fromLStoS(LS1,[A|Stack],L0,L1), fromLStoS(Rest,Stack,L1,L2)."""
        item, rest = uncons(ls)
        a, ls1 = uncons(item)
        l1 = fresh()
        self(ls1, cons(a, stack), l0, l1)
        self(rest, stack, l1, l2)


class FromLStoL(Relation):
    """fromLStoL(LS, L): the layered stream LS flattened into a list of solutions (cards by position)."""

    @clause
    def flatten(self, ls: Term, lst: Term) -> None:
        """fromLStoL(LS,L) :- fromLStoS(LS,[],L,[])."""
        _from_ls_to_s(ls, nil(), lst, nil())


class Rearrange1(Relation):
    """rearrange1(Cards, R): each card(N,T,_,_,_) as the pair N-T."""

    @clause
    def done(self, cs: Term, r: Term) -> None:
        """rearrange1([],R) :- R=[]."""
        empty(cs)
        tell(r, nil())

    @clause
    def step(self, cs: Term, r: Term) -> None:
        """rearrange1([card(N,T,_,_,_)|Cs],R) :- R=[N-T|Rs], rearrange1(Cs,Rs)."""
        c, rest = uncons(cs)
        n, t, _r, _b, _l = edges(c)
        rs = fresh()
        tell(r, cons(struct('-', n, t), rs))
        self(rest, rs)


class Rearrange2(Relation):
    """rearrange2(Ms, R): from placement order to grid order."""

    @clause
    def permute(self, ms: Term, r: Term) -> None:
        """rearrange2([M5,M2,M6,M3,M4,M1,M8,M7,M9],R) :- R=[M1,M2,M3,M4,M5,M6,M7,M8,M9]."""
        m5, m2, m6, m3, m4, m1, m8, m7, m9 = elements(ms, 9)
        tell(r, build([m1, m2, m3, m4, m5, m6, m7, m8, m9]))


class Rearrange(Relation):
    """rearrange(A, B): one solution, from cards by position to N-T pairs by grid cell."""

    @clause
    def both(self, a: Term, b: Term) -> None:
        """rearrange(A,B) :- rearrange1(A,C),rearrange2(C,B)."""
        c = fresh()
        _rearrange1(a, c)
        _rearrange2(c, b)


class Final(Relation):
    """final(Solutions, Out): every solution rearranged."""

    @clause
    def done(self, xs: Term, out: Term) -> None:
        """final([],Out) :- Out=[]."""
        empty(xs)
        tell(out, nil())

    @clause
    def step(self, xs: Term, out: Term) -> None:
        """final([A|As],Out) :- Out = [R|Out1], rearrange(A,R), final(As,Out1)."""
        a, rest = uncons(xs)
        r = fresh()
        out1 = fresh()
        tell(out, cons(r, out1))
        _rearrange(a, r)
        self(rest, out1)


class Spawn(Relation):
    """spawn(D, C, S0, S2): one layer per constraint row, then the flattened, rearranged solutions S2."""

    @clause
    def done(self, d: Term, c: Term, s0: Term, s2: Term) -> None:
        """spawn([],_C,S0,S2) :- fromLStoL(S0,S1),final(S1,S2)."""
        empty(d)
        s1 = fresh()
        _from_ls_to_l(s0, s1)
        _final(s1, s2)

    @clause
    def layer(self, d: Term, c: Term, s0: Term, s2: Term) -> None:
        """spawn([D|Ds],C,S0,S2) :- orient(1,D,C,S0,S1),spawn(Ds,C,S1,S2)."""
        row, rest = uncons(d)
        s1 = fresh()
        _orient(1, row, c, s0, s1)
        self(rest, c, s1, s2)


class CountFrom(Relation):
    """count(L, M, N): N = M + length(L)."""

    @clause
    def done(self, xs: Term, m: Term, n: Term) -> None:
        """count([],M,N) :- M = N."""
        empty(xs)
        tell(n, m)

    @clause
    def more(self, xs: Term, m: Term, n: Term) -> None:
        """count([_|Xs],M,N) :- M1 := M+1, count(Xs,M1,N)."""
        _x, rest = uncons(xs)
        self(rest, m + 1, n)


class Count(Relation):
    """count(L, N): N = length(L)."""

    count_from = CountFrom()

    @clause
    def start(self, xs: Term, n: Term) -> None:
        """count(L,N) :- count(L,0,N)."""
        self.count_from(xs, 0, n)


class Go(Relation):
    """go(N, A): A is the list of solutions, N how many there are."""

    cards = Cards()
    constraints = Constraints()
    count = Count()

    @clause
    def solve(self, n: Term, a: Term) -> None:
        """go(N,A) :- cards(C), constraints(D), spawn(D,C,begin,A), count(A,N)."""
        c = fresh()
        d = fresh()
        self.cards(c)
        self.constraints(d)
        _spawn(d, c, 'begin', a)
        self.count(a, n)


_flip = Flip()
_send = Send()
_filter1 = Filter1()
_filter = Filter()
_set = Set()
_rotate = Rotate()
_orient = Orient()
_from_ls_to_s = FromLStoS()
_from_ls_to_l = FromLStoL()
_rearrange1 = Rearrange1()
_rearrange2 = Rearrange2()
_rearrange = Rearrange()
_final = Final()
_spawn = Spawn()
go = Go()

type Pair = tuple[Value, Value]
"""One grid cell of a solution: the card number N and the edge T on top (KL1's ``N-T``)."""


def solve() -> tuple[Value, list[list[Pair]]]:
    """Run ``go(N, A)``; return N and the solutions as lists of ``(N, T)`` pairs in grid order."""
    with session() as engine:
        n = Var()
        a = Var()
        go(n, a)
        engine.run()
    solutions: list[list[Pair]] = []
    for solution in to_list(a):
        cells: list[Pair] = []
        for cell in to_list(solution):
            if not isinstance(cell, Struct) or cell.name != '-':
                raise TypeError(f'turtles did not run to completion: {cell!r}')
            number, top = cell.args
            cells.append((deref(number), deref(top)))
        solutions.append(cells)
    return deref(n), solutions


def render(solutions: Sequence[Sequence[Pair]]) -> str:
    """The solutions in KL1 syntax, as ``putt(A)`` prints them: ``[[5-tb,2-hg,...],...]``."""
    return '[' + ','.join('[' + ','.join(f'{n}-{t}' for n, t in cells) + ']' for cells in solutions) + ']'


def main() -> None:
    """Print A as turtles.kl1's main does, then N."""
    n, solutions = solve()
    print(render(solutions))
    print(f'N = {n}')


if __name__ == '__main__':
    main()
