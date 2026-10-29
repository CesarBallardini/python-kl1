"""KLIC's ``wave`` program -- a 3-D mesh of communicating processes -- ported to python-kl1.

Mirrors ``kl1c/examples/wave.kl1`` (I. Foster's *Waves*, translated from Strand by E. Tick)::

    main :- true | go6_2.
    go6_2 :- true | go(6,2,S).

    go(D,Stop,S) :- D > 5, Stop > 0 |                       % D dimensional cube
        IDim := D - 2,                                      % 1 =< i =< D-1
        S=yes,
        planes(0,D,Ks,Stop,done,Done,Go),                   % spawn structure
        gen(IDim,D,Ks),                                     % close edge streams
        start(Done,Go).                                     % begin computation
    otherwise.
    go(_,_,S) :- true | S=no.

    planes(K,D,Ks,Stop,L,R,Go) :- K < D |                   % spawn planes in K
        K1 := K + 1, gen1(D,Js),
        plane(1,K,D,Js,Ks,NKs,Stop,L,M,Go),                 % spawn one plane
        planes(K1,D,NKs,Stop,M,R,Go).                       % rest recursively
    planes(K,K,Ks,_,L,R,_) :- true | R = L, end(Ks).        % all done

    plane(I,K,D,Js,[Ks|Kss],NKs,Stop,L,R,Go) :- true |      % spawn colums in I
        I1 := I + 1, NKs = [Ks1|Kss1],
        col(I,0,K,D,{[],_},Js,Js1,Ks,Ks1,Stop,L,M,Go),      % spawn one column
        plane(I1,K,D,Js1,Kss,Kss1,Stop,M,R,Go).             % rest recursively
    plane(_,_,_,Js,[],NKs,_,L,R,_) :- true | R = L, NKs = [], end1(Js).

    col(I,J,K,D,S,[W|Ws],Es,[B|Bs],Fs,Stop,L,R,Go) :- true |% spawn a column
        J1 := J + 1, Max := D - 1, End := D - 2,
        Es = [{Eo,Ei}|Es1], Fs = [{Fo,Fi}|Fs1],             % spawn point I,J,K
        pt(I,J,K,End,Max,{Ni,No},{Ei,Eo},S,W,B,{Fi,Fo},1,Stop,L,M,Go),
        col(I,J1,K,D,{No,Ni},Ws,Es1,Bs,Fs1,Stop,M,R,Go).
    col(_,_,_,_,{_,So},[],Es,[],Fs,_,L,R,_) :- true |       % all points spawned
        R = L, So = [], Es = [], Fs = [].

    pt(I,J,K,E,_,{Ni,No},{Ei,Eo},{Si,So},{Wi,Wo},{Bi,Bo},{Fi,Fo},IS,Stop,L,R,Go):-
        2 =< I, I < E, 1 =< J, J =< E, 1 =< K, K =< E |
        R = L,                                              % Interior Point
        filter(Go,Ni,So,send(IS),Is,I1,Os,O1),              % deal with step msgs
        filter(Go,Ei,Wo,send(IS),I1,I2,O1,O2),
        filter(Go,Si,No,none,I2,I3,O2,O3),
        filter(Go,Wi,Eo,none,I3,I4,O3,O4),
        filter(Go,Bi,Fo,none,I4,I5,O4,O5),
        filter(Go,Fi,Bo,send(IS),I5,[],O5,[]),
        node(I,J,K,Is,Os,IS,Stop).
    pt(1,J,K,E,_,{Ni,No},{Ei,Eo},{Si,So},{Wi,Wo},{Bi,Bo},{Fi,Fo},IS,Stop,L,R,Go):-
        1 =< J, J =< E, 1 =< K, K =< E |
        Eo = [step(0,S1,A1),step(1,S2,A2)|Eo1],             % Low I Boundary
        acknowledged(A1,A2,L,R),
        route(Go,Ni,Ei,Si,Wi,Bi,Fi,No,Eo1,So,Wo,Bo,Fo,Os),
        node(1,J,K,[S1,S2],Os,IS,Stop).
    pt(I,J,0,E,_,{Ni,No},{Ei,Eo},{Si,So},{Wi,Wo},{Bi,Bo},{Fi,Fo},IS,Stop,L,R,Go):-
        1 =< I, I =< E, 1 =< J, J =< E |
        K1 := E - 2, Fo = [step(K1,S1,A1)|Fo1],             % Low K Boundary
        acknowledged(A1,L,R),
        route(Go,Ni,Ei,Si,Wi,Bi,Fi,No,Eo,So,Wo,Bo,Fo1,Os),
        node(I,J,0,[S1],Os,IS,Stop).
    % ... plus the mirror images: the high I face (I = E) sends its two steps west, the
    % high K face (K = Max) one step back, the low / high J faces one step north / south.

    filter(Go,[step(0,S,A)|Is],Os,IM,Ib,Ie,Ob,Oe) :- true | % step at destination
        Ob = [S|Ob1], A = ack, filter(Go,Is,Os,IM,Ib,Ie,Ob1,Oe).
    filter(Go,[step(N,S,A)|Is],Os,IM,Ib,Ie,Ob,Oe) :-        % step to be routed
        N > 0 | N1 := N - 1, Os = [step(N1,S,A)|Os1], filter(Go,Is,Os1,IM,Ib,Ie,Ob,Oe).
    filter(go,I,O,send(IS),Ib,Ie,Ob,Oe) :- true |           % all done, initiate
        Ib = [I|Ie], O = [IS|O1], Ob = [O1|Oe].             % send state behind
    filter(go,I,O,none,Ib,Ie,Ob,Oe) :- true |               % all done
        Ib = [I|Ie], Ob = [O|Oe].

    route(Go,Ni,Ei,Si,Wi,Bi,Fi,No,Eo,So,Wo,Bo,Fo,Os) :- true |
        bfilter(Go,Ni,So,Os,O1), bfilter(Go,Ei,Wo,O1,O2),
        bfilter(Go,Si,No,O2,O3), bfilter(Go,Wi,Eo,O3,O4),
        bfilter(Go,Bi,Fo,O4,O5), bfilter(Go,Fi,Bo,O5,[]).

    bfilter(Go,[step(0,S,A)|Is],Os,Ob,Oe) :- true | Ob = [S|Ob1], A = ack, bfilter(Go,Is,Os,Ob1,Oe).
    bfilter(Go,[step(N,S,A)|Is],Os,Ob,Oe) :- N > 0 |
        N1 := N - 1, Os = [step(N1,S,A)|Os1], bfilter(Go,Is,Os1,Ob,Oe).
    bfilter(go,_,O,Ob,Oe) :- true | Ob=Oe, O=[].            % all done

    node(I,J,K,Is,Os,State,Stop) :- Stop > 0 |              % still iterating
        Stop1 := Stop-1,
        getin(Is,Vals,Is1),                                 % recv from neighbors
        compute(I,J,K,Vals,State,NewState),                 % compute local value
        putout(NewState,Os,Os1),                            % send to neighbors
        node(I,J,K,Is1,Os1,NewState,Stop1).                 % do it again
    node(_,_,_,_,_,_,0) :- true | true.                     % time to stop

    getin([[V|Vs]|Ss],Vo,Is1) :- true | Vo = [V|Vs1], Is1 = [Vs|Ss1], getin(Ss,Vs1,Ss1).
    getin([[]|Ss],Vs,Is1) :- true | getin(Ss,Vs,Is1).      % skip closed strms
    getin([],Vs,Is1) :- true | Vs=[], Is1=[].

    compute(I,J,K,L,S,NS) :- true | checklist(L,Sync), show(Sync,I,J,K,L,S,NS).
    checklist([L|Ls],Sync) :- integer(L) | checklist(Ls,Sync).
    checklist([],    Sync) :-       true | Sync = [].
    show(Sync,I,J,K,L,S,NS) :- wait(Sync) | NS := S + 1.

    putout(State,[S|Ss],So) :- true | S = [State|S1], So = [S1|Ss1], putout(State,Ss,Ss1).
    putout(_,[],So) :- true | So=[].

    start(done,Go) :- true | Go=go.                         % begin when spawned
    acknowledged(ack,L,R) :- true | R=L.                    % close cct if acked
    acknowledged(ack,ack,L,R) :- true | R=L.                % close if two asks

    gen(N,D,Ks) :-  N>0 | N1 := N-1, Ks=[Ks1|Kss], gen1(D,Ks1), gen(N1,D,Kss).
    gen(0,_,Ks) :- true | Ks=[].
    gen1(N,Ks)  :-  N>0 | N1 := N-1, Ks = [{[],_}|Ks1], gen1(N1,Ks1).
    gen1(0,Ks)  :- true | Ks=[].
    end([S|Ss]) :- true | end1(S), end(Ss).
    end([]) :- true | true.
    end1([{_,O}|Ss]) :- true | O=[], end1(Ss).
    end1([]) :- true | true.

``go(D, Stop, S)`` builds a D x (D-2) x D block of ``node`` processes -- ``planes`` spawns the
K planes, ``plane`` the I columns of each, ``col`` the J points of each column -- with every
pair of neighbours joined by a 2-vector ``{In, Out}`` of streams, and the six faces of the
block closed (``gen``/``gen1`` on the low faces, ``end``/``end1`` and ``col``'s last clause on
the high ones). The run has two phases. **Wiring:** each face point sends ``step(N, S, A)``
requests into the block; ``filter`` (interior points) and ``bfilter`` (face points) forward
them with N decremented until the point N hops away adopts the stream ``S`` as one of its
outputs and binds the acknowledgement ``A = ack``. The ``L``/``R`` pair threaded through every
point is a barrier: the atom ``done`` travels the chain only as far as the ``acknowledged``
goals let it, so it reaches ``start`` once every request has landed, and ``Go = go`` then
tells every filter to hand its remaining streams to its node. **Iteration:** for ``Stop``
rounds each node reads one value from every open input (``getin``), waits until all of them
are integers (``checklist``/``show``), increments its state, and writes it to every output
(``putout``). The original's only answer is ``S = yes``, bound before any of this runs; its
real result is that the 144 processes (D = 6) all terminate without deadlock.

Substitutions, in source order:

- the 2-vectors ``{A, B}`` are the functor ``io(A, B)`` -- :func:`link` builds one and
  :func:`links` destructures a point's six at once, as ``pt``'s head does;
- ``acknowledged/3`` and ``acknowledged/4`` are two relations (a ``Relation``'s clauses share
  one arity), ``Acknowledged`` and ``BothAcknowledged``;
- ``integer(L)`` is ``guard(v >= 0)``: states are counts, so the comparison is the type test,
  and like the original it is what makes ``checklist`` wait for the neighbour's value;
- ``wait(Sync)`` is ``empty(sync)`` -- ``checklist`` binds ``Sync`` to ``[]``;
- ``go``'s ``otherwise`` is a trailing guard-free clause. That is safe because ``D`` and
  ``Stop`` are bound when ``go`` runs, so the first clause *fails* rather than suspends
  (contrast ``mastermind``, whose inputs arrive concurrently and whose negated guards must be
  written out);
- KL1's ``L``/``R`` are ``left``/``right`` (``l`` is not a usable Python name).

One deliberate deviation: ``S = yes`` says nothing about the mesh, so the port threads a
result difference list ``States/States1`` through ``planes -> plane -> col -> pt -> node``
and ``node``'s stopping clause reports its final state on it. ``go/3`` thus becomes
``go(D, Stop, S, States)``; :func:`final_states` runs it and returns the list -- 144 states,
all ``1 + Stop``. Run it with ``uv run python examples/wave.py``.
"""

from python_kl1.core import Value, Var, to_list
from python_kl1.dsl import (
    Operand,
    Relation,
    Term,
    clause,
    cons,
    empty,
    fresh,
    guard,
    nil,
    session,
    struct,
    tell,
    uncons,
    unstruct,
)

type Pair = tuple[Term, Term]
"""A link's two streams, (in, out), as ``pt``'s head patterns ``{Ni,No}`` ... ``{Fi,Fo}`` name them."""


def link(ins: Operand, outs: Operand) -> Term:
    """KL1's 2-vector ``{In, Out}`` joining two neighbours, as the term ``io(In, Out)``."""
    return struct('io', ins, outs)


def links(n: Term, e: Term, s: Term, w: Term, b: Term, f: Term) -> tuple[Pair, Pair, Pair, Pair, Pair, Pair]:
    """Head patterns ``{Ni,No},{Ei,Eo},{Si,So},{Wi,Wo},{Bi,Bo},{Fi,Fo}``: a point's six links, split."""
    ni, no = unstruct(n, 'io', 2)
    ei, eo = unstruct(e, 'io', 2)
    si, so = unstruct(s, 'io', 2)
    wi, wo = unstruct(w, 'io', 2)
    bi, bo = unstruct(b, 'io', 2)
    fi, fo = unstruct(f, 'io', 2)
    return (ni, no), (ei, eo), (si, so), (wi, wo), (bi, bo), (fi, fo)


class GetIn(Relation):
    """getin(Is, Vals, Is1): one value from every open input stream; Is1 holds the tails."""

    @clause
    def one(self, ins: Term, vals: Term, ins1: Term) -> None:
        """getin([[V|Vs]|Ss],Vo,Is1) :- Vo = [V|Vs1], Is1 = [Vs|Ss1], getin(Ss,Vs1,Ss1)."""
        s, ss = uncons(ins)
        v, vs = uncons(s)
        vs1 = fresh()
        ss1 = fresh()
        tell(vals, cons(v, vs1))
        tell(ins1, cons(vs, ss1))
        self(ss, vs1, ss1)

    @clause
    def skip(self, ins: Term, vals: Term, ins1: Term) -> None:
        """getin([[]|Ss],Vs,Is1) :- getin(Ss,Vs,Is1).  -- skip closed streams."""
        s, ss = uncons(ins)
        empty(s)
        self(ss, vals, ins1)

    @clause
    def done(self, ins: Term, vals: Term, ins1: Term) -> None:
        """getin([],Vs,Is1) :- Vs=[], Is1=[]."""
        empty(ins)
        tell(vals, nil())
        tell(ins1, nil())


class CheckList(Relation):
    """checklist(Vals, Sync): Sync becomes [] once every value read has actually arrived."""

    @clause
    def one(self, vals: Term, sync: Term) -> None:
        """checklist([L|Ls],Sync) :- integer(L) | checklist(Ls,Sync)."""
        v, vs = uncons(vals)
        guard(v >= 0)  # integer(L): a state is a count, so this is the type test -- and the wait for V
        self(vs, sync)

    @clause
    def done(self, vals: Term, sync: Term) -> None:
        """checklist([],Sync) :- Sync = []."""
        empty(vals)
        tell(sync, nil())


class Show(Relation):
    """show(Sync, I, J, K, Vals, S, NS): once Sync is bound, the new state is S + 1."""

    @clause
    def step(self, sync: Term, i: Term, j: Term, k: Term, vals: Term, s: Term, ns: Term) -> None:
        """show(Sync,I,J,K,L,S,NS) :- wait(Sync) | NS := S + 1."""
        empty(sync)  # wait(Sync): checklist binds Sync to [], so the [] pattern is the wait
        tell(ns, s + 1)


class Compute(Relation):
    """compute(I, J, K, Vals, S, NS): the local step -- wait for the neighbours' values, then count."""

    checklist = CheckList()
    show = Show()

    @clause
    def step(self, i: Term, j: Term, k: Term, vals: Term, s: Term, ns: Term) -> None:
        """compute(I,J,K,L,S,NS) :- checklist(L,Sync), show(Sync,I,J,K,L,S,NS)."""
        sync = fresh()
        self.checklist(vals, sync)
        self.show(sync, i, j, k, vals, s, ns)


class PutOut(Relation):
    """putout(State, Os, Os1): write State to every output stream; Os1 holds the new tails."""

    @clause
    def one(self, state: Term, outs: Term, outs1: Term) -> None:
        """putout(State,[S|Ss],So) :- S = [State|S1], So = [S1|Ss1], putout(State,Ss,Ss1)."""
        s, ss = uncons(outs)
        s1 = fresh()
        ss1 = fresh()
        tell(s, cons(state, s1))
        tell(outs1, cons(s1, ss1))
        self(state, ss, ss1)

    @clause
    def done(self, state: Term, outs: Term, outs1: Term) -> None:
        """putout(_,[],So) :- So=[]."""
        empty(outs)
        tell(outs1, nil())


class Node(Relation):
    """node(I, J, K, Is, Os, State, Stop, States, States1): Stop rounds of read-all, count, write-all."""

    getin = GetIn()
    compute = Compute()
    putout = PutOut()

    @clause
    def step(
        self, i: Term, j: Term, k: Term, ins: Term, outs: Term, state: Term, stop: Term, states: Term, states1: Term
    ) -> None:
        """One round, then again with Stop - 1.

        node(I,J,K,Is,Os,State,Stop) :- Stop > 0 | Stop1 := Stop-1, getin(Is,Vals,Is1),
        compute(I,J,K,Vals,State,NewState), putout(NewState,Os,Os1), node(I,J,K,Is1,Os1,NewState,Stop1).
        """
        guard(stop > 0)
        vals = fresh()
        ins1 = fresh()
        new_state = fresh()
        outs1 = fresh()
        self.getin(ins, vals, ins1)
        self.compute(i, j, k, vals, state, new_state)
        self.putout(new_state, outs, outs1)
        self(i, j, k, ins1, outs1, new_state, stop - 1, states, states1)

    @clause
    def halt(
        self, i: Term, j: Term, k: Term, ins: Term, outs: Term, state: Term, stop: Term, states: Term, states1: Term
    ) -> None:
        """node(_,_,_,_,_,_,0) :- true.  -- plus the port's report of the final state: States = [State|States1]."""
        guard(stop == 0)
        tell(states, cons(state, states1))


class BFilter(Relation):
    """bfilter(Go, In, Out, Ob, Oe): a face point's router for one direction, closed when Go arrives."""

    @clause
    def arrived(self, go: Term, src: Term, dst: Term, ob: Term, oe: Term) -> None:
        """bfilter(Go,[step(0,S,A)|Is],Os,Ob,Oe) :- Ob = [S|Ob1], A = ack, bfilter(Go,Is,Os,Ob1,Oe)."""
        msg, rest = uncons(src)
        hops, s, a = unstruct(msg, 'step', 3)
        guard(hops == 0)
        ob1 = fresh()
        tell(ob, cons(s, ob1))
        tell(a, 'ack')
        self(go, rest, dst, ob1, oe)

    @clause
    def forward(self, go: Term, src: Term, dst: Term, ob: Term, oe: Term) -> None:
        """bfilter(Go,[step(N,S,A)|Is],Os,Ob,Oe) :- N > 0 | N1 := N - 1, Os = [step(N1,S,A)|Os1], bfilter(...)."""
        msg, rest = uncons(src)
        hops, s, a = unstruct(msg, 'step', 3)
        guard(hops > 0)
        dst1 = fresh()
        tell(dst, cons(struct('step', hops - 1, s, a), dst1))
        self(go, rest, dst1, ob, oe)

    @clause
    def done(self, go: Term, src: Term, dst: Term, ob: Term, oe: Term) -> None:
        """bfilter(go,_,O,Ob,Oe) :- Ob=Oe, O=[]."""
        guard(go == 'go')
        tell(ob, oe)
        tell(dst, nil())


class Route(Relation):
    """route(Go, Ni..Fi, No..Fo, Os): a face point's six routers; Os collects the streams it must feed."""

    bfilter = BFilter()

    @clause
    def faces(
        self,
        go: Term,
        ni: Term,
        ei: Term,
        si: Term,
        wi: Term,
        bi: Term,
        fi: Term,
        no: Term,
        eo: Term,
        so: Term,
        wo: Term,
        bo: Term,
        fo: Term,
        outs: Term,
    ) -> None:
        """Six bfilters, each forwarding one input to the opposite output.

        route(Go,Ni,Ei,Si,Wi,Bi,Fi,No,Eo,So,Wo,Bo,Fo,Os) :- bfilter(Go,Ni,So,Os,O1), bfilter(Go,Ei,Wo,O1,O2),
        bfilter(Go,Si,No,O2,O3), bfilter(Go,Wi,Eo,O3,O4), bfilter(Go,Bi,Fo,O4,O5), bfilter(Go,Fi,Bo,O5,[]).
        """
        out1 = fresh()
        out2 = fresh()
        out3 = fresh()
        out4 = fresh()
        out5 = fresh()
        self.bfilter(go, ni, so, outs, out1)
        self.bfilter(go, ei, wo, out1, out2)
        self.bfilter(go, si, no, out2, out3)
        self.bfilter(go, wi, eo, out3, out4)
        self.bfilter(go, bi, fo, out4, out5)
        self.bfilter(go, fi, bo, out5, nil())


class Filter(Relation):
    """filter(Go, In, Out, Mode, Ib, Ie, Ob, Oe): an interior point's router for one direction.

    Until Go arrives it forwards step requests; then the rest of In joins the node's inputs
    (Ib/Ie) and Out its outputs (Ob/Oe), after an initial state is sent when Mode is send(IS).
    """

    @clause
    def arrived(self, go: Term, src: Term, dst: Term, mode: Term, ib: Term, ie: Term, ob: Term, oe: Term) -> None:
        """filter(Go,[step(0,S,A)|Is],Os,IM,Ib,Ie,Ob,Oe) :- Ob = [S|Ob1], A = ack, filter(Go,Is,Os,IM,Ib,Ie,Ob1,Oe)."""
        msg, rest = uncons(src)
        hops, s, a = unstruct(msg, 'step', 3)
        guard(hops == 0)
        ob1 = fresh()
        tell(ob, cons(s, ob1))
        tell(a, 'ack')
        self(go, rest, dst, mode, ib, ie, ob1, oe)

    @clause
    def forward(self, go: Term, src: Term, dst: Term, mode: Term, ib: Term, ie: Term, ob: Term, oe: Term) -> None:
        """Route a step one hop further.

        filter(Go,[step(N,S,A)|Is],Os,IM,Ib,Ie,Ob,Oe) :- N > 0 |
            N1 := N - 1, Os = [step(N1,S,A)|Os1], filter(Go,Is,Os1,IM,Ib,Ie,Ob,Oe).
        """
        msg, rest = uncons(src)
        hops, s, a = unstruct(msg, 'step', 3)
        guard(hops > 0)
        dst1 = fresh()
        tell(dst, cons(struct('step', hops - 1, s, a), dst1))
        self(go, rest, dst1, mode, ib, ie, ob, oe)

    @clause
    def go_send(self, go: Term, src: Term, dst: Term, mode: Term, ib: Term, ie: Term, ob: Term, oe: Term) -> None:
        """filter(go,I,O,send(IS),Ib,Ie,Ob,Oe) :- Ib = [I|Ie], O = [IS|O1], Ob = [O1|Oe]."""
        guard(go == 'go')
        (init,) = unstruct(mode, 'send', 1)
        dst1 = fresh()
        tell(ib, cons(src, ie))
        tell(dst, cons(init, dst1))
        tell(ob, cons(dst1, oe))

    @clause
    def go_none(self, go: Term, src: Term, dst: Term, mode: Term, ib: Term, ie: Term, ob: Term, oe: Term) -> None:
        """filter(go,I,O,none,Ib,Ie,Ob,Oe) :- Ib = [I|Ie], Ob = [O|Oe]."""
        guard(go == 'go')
        guard(mode == 'none')
        tell(ib, cons(src, ie))
        tell(ob, cons(dst, oe))


class Acknowledged(Relation):
    """acknowledged(A, L, R): pass the barrier token on once the one request has landed."""

    @clause
    def acked(self, a: Term, left: Term, right: Term) -> None:
        """acknowledged(ack,L,R) :- R=L."""
        guard(a == 'ack')
        tell(right, left)


class BothAcknowledged(Relation):
    """acknowledged(A1, A2, L, R): pass the barrier token on once both requests have landed."""

    @clause
    def acked(self, a1: Term, a2: Term, left: Term, right: Term) -> None:
        """acknowledged(ack,ack,L,R) :- R=L."""
        guard(a1 == 'ack')
        guard(a2 == 'ack')
        tell(right, left)


class Pt(Relation):
    """pt(I, J, K, End, Max, N, E, S, W, B, F, IS, Stop, L, R, Go, States, States1): one point of the block.

    The six links N..F are {In, Out} pairs seen from this point; End = D - 2 and Max = D - 1 bound
    the coordinates (1 =< I =< End, 0 =< J, K =< Max). The first clause is the interior; the other
    six are the faces, each of which requests states from the points one or two hops inward.
    """

    filter = Filter()
    route = Route()
    node = Node()
    acknowledged = Acknowledged()
    both_acknowledged = BothAcknowledged()

    @clause
    def interior(
        self,
        i: Term,
        j: Term,
        k: Term,
        end: Term,
        last: Term,
        n: Term,
        e: Term,
        s: Term,
        w: Term,
        b: Term,
        f: Term,
        init: Term,
        stop: Term,
        left: Term,
        right: Term,
        go: Term,
        states: Term,
        states1: Term,
    ) -> None:
        """Interior point: six filters, then the node.

        pt(I,J,K,E,_,{Ni,No},{Ei,Eo},{Si,So},{Wi,Wo},{Bi,Bo},{Fi,Fo},IS,Stop,L,R,Go) :-
            2 =< I, I < E, 1 =< J, J =< E, 1 =< K, K =< E |
            R = L, filter(Go,Ni,So,send(IS),Is,I1,Os,O1), filter(Go,Ei,Wo,send(IS),I1,I2,O1,O2),
            filter(Go,Si,No,none,I2,I3,O2,O3), filter(Go,Wi,Eo,none,I3,I4,O3,O4),
            filter(Go,Bi,Fo,none,I4,I5,O4,O5), filter(Go,Fi,Bo,send(IS),I5,[],O5,[]),
            node(I,J,K,Is,Os,IS,Stop).
        """
        guard(i >= 2)
        guard(i < end)
        guard(j >= 1)
        guard(j <= end)
        guard(k >= 1)
        guard(k <= end)
        (ni, no), (ei, eo), (si, so), (wi, wo), (bi, bo), (fi, fo) = links(n, e, s, w, b, f)
        tell(right, left)
        ins = fresh()
        in1 = fresh()
        in2 = fresh()
        in3 = fresh()
        in4 = fresh()
        in5 = fresh()
        outs = fresh()
        out1 = fresh()
        out2 = fresh()
        out3 = fresh()
        out4 = fresh()
        out5 = fresh()
        send = struct('send', init)
        self.filter(go, ni, so, send, ins, in1, outs, out1)
        self.filter(go, ei, wo, send, in1, in2, out1, out2)
        self.filter(go, si, no, 'none', in2, in3, out2, out3)
        self.filter(go, wi, eo, 'none', in3, in4, out3, out4)
        self.filter(go, bi, fo, 'none', in4, in5, out4, out5)
        self.filter(go, fi, bo, send, in5, nil(), out5, nil())
        self.node(i, j, k, ins, outs, init, stop, states, states1)

    @clause
    def low_i(
        self,
        i: Term,
        j: Term,
        k: Term,
        end: Term,
        last: Term,
        n: Term,
        e: Term,
        s: Term,
        w: Term,
        b: Term,
        f: Term,
        init: Term,
        stop: Term,
        left: Term,
        right: Term,
        go: Term,
        states: Term,
        states1: Term,
    ) -> None:
        """Low I face: ask the two points to the east for their states.

        pt(1,J,K,E,_,{Ni,No},{Ei,Eo},{Si,So},{Wi,Wo},{Bi,Bo},{Fi,Fo},IS,Stop,L,R,Go) :-
            1 =< J, J =< E, 1 =< K, K =< E |
            Eo = [step(0,S1,A1),step(1,S2,A2)|Eo1], acknowledged(A1,A2,L,R),
            route(Go,Ni,Ei,Si,Wi,Bi,Fi,No,Eo1,So,Wo,Bo,Fo,Os), node(1,J,K,[S1,S2],Os,IS,Stop).
        """
        guard(i == 1)
        guard(j >= 1)
        guard(j <= end)
        guard(k >= 1)
        guard(k <= end)
        (ni, no), (ei, eo), (si, so), (wi, wo), (bi, bo), (fi, fo) = links(n, e, s, w, b, f)
        s1 = fresh()
        a1 = fresh()
        s2 = fresh()
        a2 = fresh()
        eo1 = fresh()
        outs = fresh()
        tell(eo, cons(struct('step', 0, s1, a1), cons(struct('step', 1, s2, a2), eo1)))
        self.both_acknowledged(a1, a2, left, right)
        self.route(go, ni, ei, si, wi, bi, fi, no, eo1, so, wo, bo, fo, outs)
        self.node(1, j, k, cons(s1, cons(s2, nil())), outs, init, stop, states, states1)

    @clause
    def high_i(
        self,
        i: Term,
        j: Term,
        k: Term,
        end: Term,
        last: Term,
        n: Term,
        e: Term,
        s: Term,
        w: Term,
        b: Term,
        f: Term,
        init: Term,
        stop: Term,
        left: Term,
        right: Term,
        go: Term,
        states: Term,
        states1: Term,
    ) -> None:
        """High I face: ask the two points to the west for their states.

        pt(E,J,K,E,_,{Ni,No},{Ei,Eo},{Si,So},{Wi,Wo},{Bi,Bo},{Fi,Fo},IS,Stop,L,R,Go) :-
            1 =< J, J =< E, 1 =< K, K =< E |
            Wo = [step(0,S1,A1),step(1,S2,A2)|Wo1], acknowledged(A1,A2,L,R),
            route(Go,Ni,Ei,Si,Wi,Bi,Fi,No,Eo,So,Wo1,Bo,Fo,Os), node(E,J,K,[S1,S2],Os,IS,Stop).
        """
        guard(i == end)
        guard(j >= 1)
        guard(j <= end)
        guard(k >= 1)
        guard(k <= end)
        (ni, no), (ei, eo), (si, so), (wi, wo), (bi, bo), (fi, fo) = links(n, e, s, w, b, f)
        s1 = fresh()
        a1 = fresh()
        s2 = fresh()
        a2 = fresh()
        wo1 = fresh()
        outs = fresh()
        tell(wo, cons(struct('step', 0, s1, a1), cons(struct('step', 1, s2, a2), wo1)))
        self.both_acknowledged(a1, a2, left, right)
        self.route(go, ni, ei, si, wi, bi, fi, no, eo, so, wo1, bo, fo, outs)
        self.node(end, j, k, cons(s1, cons(s2, nil())), outs, init, stop, states, states1)

    @clause
    def low_k(
        self,
        i: Term,
        j: Term,
        k: Term,
        end: Term,
        last: Term,
        n: Term,
        e: Term,
        s: Term,
        w: Term,
        b: Term,
        f: Term,
        init: Term,
        stop: Term,
        left: Term,
        right: Term,
        go: Term,
        states: Term,
        states1: Term,
    ) -> None:
        """Low K face: ask the point E - 1 planes in front for its state.

        pt(I,J,0,E,_,{Ni,No},{Ei,Eo},{Si,So},{Wi,Wo},{Bi,Bo},{Fi,Fo},IS,Stop,L,R,Go) :-
            1 =< I, I =< E, 1 =< J, J =< E |
            K1 := E - 2, Fo = [step(K1,S1,A1)|Fo1], acknowledged(A1,L,R),
            route(Go,Ni,Ei,Si,Wi,Bi,Fi,No,Eo,So,Wo,Bo,Fo1,Os), node(I,J,0,[S1],Os,IS,Stop).
        """
        guard(k == 0)
        guard(i >= 1)
        guard(i <= end)
        guard(j >= 1)
        guard(j <= end)
        (ni, no), (ei, eo), (si, so), (wi, wo), (bi, bo), (fi, fo) = links(n, e, s, w, b, f)
        s1 = fresh()
        a1 = fresh()
        fo1 = fresh()
        outs = fresh()
        tell(fo, cons(struct('step', end - 2, s1, a1), fo1))
        self.acknowledged(a1, left, right)
        self.route(go, ni, ei, si, wi, bi, fi, no, eo, so, wo, bo, fo1, outs)
        self.node(i, j, 0, cons(s1, nil()), outs, init, stop, states, states1)

    @clause
    def high_k(
        self,
        i: Term,
        j: Term,
        k: Term,
        end: Term,
        last: Term,
        n: Term,
        e: Term,
        s: Term,
        w: Term,
        b: Term,
        f: Term,
        init: Term,
        stop: Term,
        left: Term,
        right: Term,
        go: Term,
        states: Term,
        states1: Term,
    ) -> None:
        """High K face: ask the point E - 1 planes behind for its state.

        pt(I,J,M,E,M,{Ni,No},{Ei,Eo},{Si,So},{Wi,Wo},{Bi,Bo},{Fi,Fo},IS,Stop,L,R,Go) :-
            1 =< I, I =< E, 1 =< J, J =< E |
            K1 := E - 2, Bo = [step(K1,S1,A1)|Bo1], acknowledged(A1,L,R),
            route(Go,Ni,Ei,Si,Wi,Bi,Fi,No,Eo,So,Wo,Bo1,Fo,Os), node(I,J,M,[S1],Os,IS,Stop).
        """
        guard(k == last)
        guard(i >= 1)
        guard(i <= end)
        guard(j >= 1)
        guard(j <= end)
        (ni, no), (ei, eo), (si, so), (wi, wo), (bi, bo), (fi, fo) = links(n, e, s, w, b, f)
        s1 = fresh()
        a1 = fresh()
        bo1 = fresh()
        outs = fresh()
        tell(bo, cons(struct('step', end - 2, s1, a1), bo1))
        self.acknowledged(a1, left, right)
        self.route(go, ni, ei, si, wi, bi, fi, no, eo, so, wo, bo1, fo, outs)
        self.node(i, j, last, cons(s1, nil()), outs, init, stop, states, states1)

    @clause
    def low_j(
        self,
        i: Term,
        j: Term,
        k: Term,
        end: Term,
        last: Term,
        n: Term,
        e: Term,
        s: Term,
        w: Term,
        b: Term,
        f: Term,
        init: Term,
        stop: Term,
        left: Term,
        right: Term,
        go: Term,
        states: Term,
        states1: Term,
    ) -> None:
        """Low J face: ask the point E - 1 rows north for its state.

        pt(I,0,K,E,M,{Ni,No},{Ei,Eo},{Si,So},{Wi,Wo},{Bi,Bo},{Fi,Fo},IS,Stop,L,R,Go) :-
            1 =< I, I =< E, 0 =< K, K =< M |
            J1 := E - 2, No = [step(J1,S1,A1)|No1], acknowledged(A1,L,R),
            route(Go,Ni,Ei,Si,Wi,Bi,Fi,No1,Eo,So,Wo,Bo,Fo,Os), node(I,0,K,[S1],Os,IS,Stop).
        """
        guard(j == 0)
        guard(i >= 1)
        guard(i <= end)
        guard(k >= 0)
        guard(k <= last)
        (ni, no), (ei, eo), (si, so), (wi, wo), (bi, bo), (fi, fo) = links(n, e, s, w, b, f)
        s1 = fresh()
        a1 = fresh()
        no1 = fresh()
        outs = fresh()
        tell(no, cons(struct('step', end - 2, s1, a1), no1))
        self.acknowledged(a1, left, right)
        self.route(go, ni, ei, si, wi, bi, fi, no1, eo, so, wo, bo, fo, outs)
        self.node(i, 0, k, cons(s1, nil()), outs, init, stop, states, states1)

    @clause
    def high_j(
        self,
        i: Term,
        j: Term,
        k: Term,
        end: Term,
        last: Term,
        n: Term,
        e: Term,
        s: Term,
        w: Term,
        b: Term,
        f: Term,
        init: Term,
        stop: Term,
        left: Term,
        right: Term,
        go: Term,
        states: Term,
        states1: Term,
    ) -> None:
        """High J face: ask the point E - 1 rows south for its state.

        pt(I,M,K,E,M,{Ni,No},{Ei,Eo},{Si,So},{Wi,Wo},{Bi,Bo},{Fi,Fo},IS,Stop,L,R,Go) :-
            1 =< I, I =< E, 0 =< K, K =< M |
            J1 := E - 2, So = [step(J1,S1,A1)|So1], acknowledged(A1,L,R),
            route(Go,Ni,Ei,Si,Wi,Bi,Fi,No,Eo,So1,Wo,Bo,Fo,Os), node(I,M,K,[S1],Os,IS,Stop).
        """
        guard(j == last)
        guard(i >= 1)
        guard(i <= end)
        guard(k >= 0)
        guard(k <= last)
        (ni, no), (ei, eo), (si, so), (wi, wo), (bi, bo), (fi, fo) = links(n, e, s, w, b, f)
        s1 = fresh()
        a1 = fresh()
        so1 = fresh()
        outs = fresh()
        tell(so, cons(struct('step', end - 2, s1, a1), so1))
        self.acknowledged(a1, left, right)
        self.route(go, ni, ei, si, wi, bi, fi, no, eo, so1, wo, bo, fo, outs)
        self.node(i, last, k, cons(s1, nil()), outs, init, stop, states, states1)


class Col(Relation):
    """col(I, J, K, D, S, Ws, Es, Bs, Fs, Stop, L, R, Go, States, States1): the D points of one column."""

    pt = Pt()

    @clause
    def point(
        self,
        i: Term,
        j: Term,
        k: Term,
        d: Term,
        s: Term,
        ws: Term,
        es: Term,
        bs: Term,
        fs: Term,
        stop: Term,
        left: Term,
        right: Term,
        go: Term,
        states: Term,
        states1: Term,
    ) -> None:
        """Spawn point (I, J, K) and the rest of the column above it.

        col(I,J,K,D,S,[W|Ws],Es,[B|Bs],Fs,Stop,L,R,Go) :-
            J1 := J + 1, Max := D - 1, End := D - 2, Es = [{Eo,Ei}|Es1], Fs = [{Fo,Fi}|Fs1],
            pt(I,J,K,End,Max,{Ni,No},{Ei,Eo},S,W,B,{Fi,Fo},1,Stop,L,M,Go),
            col(I,J1,K,D,{No,Ni},Ws,Es1,Bs,Fs1,Stop,M,R,Go).
        """
        w, ws1 = uncons(ws)
        b, bs1 = uncons(bs)
        ni = fresh()
        no = fresh()
        ei = fresh()
        eo = fresh()
        fi = fresh()
        fo = fresh()
        es1 = fresh()
        fs1 = fresh()
        mid = fresh()
        states_mid = fresh()
        tell(es, cons(link(eo, ei), es1))
        tell(fs, cons(link(fo, fi), fs1))
        self.pt(
            i,
            j,
            k,
            d - 2,
            d - 1,
            link(ni, no),
            link(ei, eo),
            s,
            w,
            b,
            link(fi, fo),
            1,
            stop,
            left,
            mid,
            go,
            states,
            states_mid,
        )
        self(i, j + 1, k, d, link(no, ni), ws1, es1, bs1, fs1, stop, mid, right, go, states_mid, states1)

    @clause
    def done(
        self,
        i: Term,
        j: Term,
        k: Term,
        d: Term,
        s: Term,
        ws: Term,
        es: Term,
        bs: Term,
        fs: Term,
        stop: Term,
        left: Term,
        right: Term,
        go: Term,
        states: Term,
        states1: Term,
    ) -> None:
        """col(_,_,_,_,{_,So},[],Es,[],Fs,_,L,R,_) :- R = L, So = [], Es = [], Fs = []."""
        empty(ws)
        empty(bs)
        _, so = unstruct(s, 'io', 2)
        tell(right, left)
        tell(so, nil())
        tell(es, nil())
        tell(fs, nil())
        tell(states, states1)


class End1(Relation):
    """end1(Links): close the inward stream of every link on a high face."""

    @clause
    def one(self, ps: Term) -> None:
        """end1([{_,O}|Ss]) :- O=[], end1(Ss)."""
        p, ss = uncons(ps)
        _, out = unstruct(p, 'io', 2)
        tell(out, nil())
        self(ss)

    @clause
    def done(self, ps: Term) -> None:
        """end1([]) :- true."""
        empty(ps)


class End(Relation):
    """end(Lists): end1 on every list of links."""

    end1 = End1()

    @clause
    def one(self, ss: Term) -> None:
        """end([S|Ss]) :- end1(S), end(Ss)."""
        s, rest = uncons(ss)
        self.end1(s)
        self(rest)

    @clause
    def done(self, ss: Term) -> None:
        """end([]) :- true."""
        empty(ss)


class Gen1(Relation):
    """gen1(N, Ks): N closed links {[], _} -- the inputs of a low face."""

    @clause
    def more(self, n: Term, ks: Term) -> None:
        """gen1(N,Ks) :- N>0 | N1 := N-1, Ks = [{[],_}|Ks1], gen1(N1,Ks1)."""
        guard(n > 0)
        ks1 = fresh()
        tell(ks, cons(link(nil(), fresh()), ks1))
        self(n - 1, ks1)

    @clause
    def done(self, n: Term, ks: Term) -> None:
        """gen1(0,Ks) :- Ks=[]."""
        guard(n == 0)
        tell(ks, nil())


class Gen(Relation):
    """gen(N, D, Ks): N lists of D closed links -- the back face of the block."""

    gen1 = Gen1()

    @clause
    def more(self, n: Term, d: Term, ks: Term) -> None:
        """gen(N,D,Ks) :- N>0 | N1 := N-1, Ks=[Ks1|Kss], gen1(D,Ks1), gen(N1,D,Kss)."""
        guard(n > 0)
        ks1 = fresh()
        kss = fresh()
        tell(ks, cons(ks1, kss))
        self.gen1(d, ks1)
        self(n - 1, d, kss)

    @clause
    def done(self, n: Term, d: Term, ks: Term) -> None:
        """gen(0,_,Ks) :- Ks=[]."""
        guard(n == 0)
        tell(ks, nil())


class Plane(Relation):
    """plane(I, K, D, Js, Kss, NKs, Stop, L, R, Go, States, States1): the D - 2 columns of plane K."""

    col = Col()
    end1 = End1()

    @clause
    def column(
        self,
        i: Term,
        k: Term,
        d: Term,
        js: Term,
        kss: Term,
        nks: Term,
        stop: Term,
        left: Term,
        right: Term,
        go: Term,
        states: Term,
        states1: Term,
    ) -> None:
        """Spawn column I and the rest of the plane east of it.

        plane(I,K,D,Js,[Ks|Kss],NKs,Stop,L,R,Go) :- I1 := I + 1, NKs = [Ks1|Kss1],
            col(I,0,K,D,{[],_},Js,Js1,Ks,Ks1,Stop,L,M,Go), plane(I1,K,D,Js1,Kss,Kss1,Stop,M,R,Go).
        """
        ks, kss1 = uncons(kss)
        js1 = fresh()
        ks1 = fresh()
        nkss = fresh()
        mid = fresh()
        states_mid = fresh()
        tell(nks, cons(ks1, nkss))
        self.col(i, 0, k, d, link(nil(), fresh()), js, js1, ks, ks1, stop, left, mid, go, states, states_mid)
        self(i + 1, k, d, js1, kss1, nkss, stop, mid, right, go, states_mid, states1)

    @clause
    def done(
        self,
        i: Term,
        k: Term,
        d: Term,
        js: Term,
        kss: Term,
        nks: Term,
        stop: Term,
        left: Term,
        right: Term,
        go: Term,
        states: Term,
        states1: Term,
    ) -> None:
        """plane(_,_,_,Js,[],NKs,_,L,R,_) :- R = L, NKs = [], end1(Js)."""
        empty(kss)
        tell(right, left)
        tell(nks, nil())
        self.end1(js)
        tell(states, states1)


class Planes(Relation):
    """planes(K, D, Ks, Stop, L, R, Go, States, States1): the D planes of the block."""

    gen1 = Gen1()
    plane = Plane()
    end = End()

    @clause
    def plane_k(
        self, k: Term, d: Term, ks: Term, stop: Term, left: Term, right: Term, go: Term, states: Term, states1: Term
    ) -> None:
        """Spawn plane K and the rest of the block in front of it.

        planes(K,D,Ks,Stop,L,R,Go) :- K < D | K1 := K + 1, gen1(D,Js),
            plane(1,K,D,Js,Ks,NKs,Stop,L,M,Go), planes(K1,D,NKs,Stop,M,R,Go).
        """
        guard(k < d)
        js = fresh()
        nks = fresh()
        mid = fresh()
        states_mid = fresh()
        self.gen1(d, js)
        self.plane(1, k, d, js, ks, nks, stop, left, mid, go, states, states_mid)
        self(k + 1, d, nks, stop, mid, right, go, states_mid, states1)

    @clause
    def done(
        self, k: Term, d: Term, ks: Term, stop: Term, left: Term, right: Term, go: Term, states: Term, states1: Term
    ) -> None:
        """planes(K,K,Ks,_,L,R,_) :- R = L, end(Ks)."""
        guard(k == d)
        tell(right, left)
        self.end(ks)
        tell(states, states1)


class Start(Relation):
    """start(Done, Go): release the filters once the barrier token has come through."""

    @clause
    def begin(self, done: Term, go: Term) -> None:
        """start(done,Go) :- Go=go."""
        guard(done == 'done')
        tell(go, 'go')


class Go(Relation):
    """go(D, Stop, S, States): build the D x (D-2) x D block, run Stop rounds, report every final state."""

    planes = Planes()
    gen = Gen()
    start = Start()

    @clause
    def build(self, d: Term, stop: Term, s: Term, states: Term) -> None:
        """Valid parameters: spawn the block, close its back face, and start it.

        go(D,Stop,S) :- D > 5, Stop > 0 | IDim := D - 2, S=yes,
            planes(0,D,Ks,Stop,done,Done,Go), gen(IDim,D,Ks), start(Done,Go).
        """
        guard(d > 5)
        guard(stop > 0)
        ks = fresh()
        done = fresh()
        go = fresh()
        tell(s, 'yes')
        self.planes(0, d, ks, stop, 'done', done, go, states, nil())
        self.gen(d - 2, d, ks)
        self.start(done, go)

    @clause
    def refuse(self, d: Term, stop: Term, s: Term, states: Term) -> None:
        """go(_,_,S) :- S=no.  -- under otherwise: D and Stop are bound, so the first clause failed, not suspended."""
        tell(s, 'no')
        tell(states, nil())


go = Go()


def final_states(d: int, stop: int) -> list[Value]:
    """Run ``go(d, stop)`` and return the final state of every node (empty when ``go`` says ``no``)."""
    with session() as engine:
        answer = Var()
        states = Var()
        go(d, stop, answer, states)
        engine.run()
    return to_list(states)


def main() -> None:
    """Run ``go(6, 2)`` as wave.kl1's ``main`` does and report what its 144 nodes computed."""
    states = final_states(6, 2)
    print(f'go(6, 2): {len(states)} nodes stopped, final states {set(states)}')


if __name__ == '__main__':
    main()
