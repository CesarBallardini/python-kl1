r"""KL1 Mastermind (naive generate and test), ported to python-kl1.

Faithful port of ``examples/mastermind.kl1`` (E. Tick, 1989). A *solution* is a sequence of at
most ``NG`` guesses over ``NC`` colours, each consistent with the feedback of all earlier
ones, that ends in the secret code; ``go(3, 3)`` counts 860 of them for the code ``[2,1,3,2]``::

    go(NG,NC,N) :- solve(NG,NC,A), count(A,N).
    code(C) :- C=[2,1,3,2].

    solve(NG,NC,Out) :- code(C), length(C,0,CL), gen(NC,Clist),
        genGuess(Guesses,Clist,CL), spawn(Guesses,Guesses,CL,[],0,NG,Out,[]).

    spawn(    [],    _, _,_,_, _,S0,S1) :- S0=S1.
    spawn([G|Gs],Plist,CL,A,N,NG,S0,S2) :-
        test(A,G,Plist,CL,A,N,NG,S0,S1), spawn(Gs,Plist,CL,A,N,NG,S1,S2).

    test([p(OldBulls,OldCows,Tried)|Gs],Guess,Plist,CL,A,N,NG,S0,S1) :-
        eval(Guess,Tried,Bulls,Cows),
        check(OldCows,Cows,OldBulls,Bulls,Gs,Guess,CL,Plist,A,N,NG,S0,S1).
    test([],Guess,Plist,CL,A,N,NG,S0,S1) :-
        code(Code), eval(Guess,Code,Bulls,Cows),
        loop(Bulls,Cows,Guess,CL,Plist,A,N,NG,S0,S1).

    loop(   CL,   _,    _,CL,    _,A,_, _,S0,S1) :- S0 = [A|S1].
    otherwise.
    loop(Bulls,Cows,Guess,CL,Plist,A,N,NG,S0,S1) :- Bulls < CL, add(N, 1, N1), N1 < NG |
        spawn(Plist,Plist,CL,[p(Bulls,Cows,Guess)|A],N1,NG,S0,S1).
    otherwise.
    loop(_,_,_,_,_,_,_,_,S0,S1) :- S0=S1.

    check(Sum,Sum,Bulls,Bulls,Gs,Guess,CL,Plist,A,N,NG,S0,S1) :-
        test(Gs,Guess,Plist,CL,A,N,NG,S0,S1).
    otherwise.
    check(_,_,_,_,_,_,_,_,_,_,_,S0,S1) :- S0=S1.

    eval(X,Y,Bulls,Cows) :- exact(X,Y,Bulls,0,X1,Y1), inexact(X1,Y1,Cows,0).

``exact`` / ``inexact`` / ``delete`` score a guess (bulls: right colour, right place; cows:
right colour, wrong place); ``genGuess`` / ``addmyself`` / ``combo`` enumerate the ``NC^CL``
guesses; ``length`` / ``gen`` / ``count`` are utilities. Solutions travel in the difference
list ``S0 \ S1`` threaded through every search path.

Substitutions: ``p(Bulls,Cows,Guess)`` is ``struct('p', ...)`` / ``unstruct(p, 'p', 3)``; the
guard arithmetic (``add/3``, ``:=``) is Python operators on terms, and the body goal
``N := CL-1`` a ``tell`` that waits for ``CL``; ``count/2`` is ``count/3`` started at 0.

**``otherwise`` waits for the score.** ``Bulls`` and ``Cows`` are produced by a concurrent
``eval``, so when ``loop`` and ``check`` first run those inputs are still unbound. Each
``otherwise.`` is an ``@otherwise`` clause, tried only once every clause above it has
*failed*: while ``solved`` or ``consistent`` is still waiting for the score, the default waits
too. A trailing guard-free ``@clause`` would commit at once, before the score exists. Run it
with ``uv run python examples/mastermind.py``.
"""

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
    struct,
    tell,
    uncons,
    unstruct,
)


class Code(Relation):
    """code(C): the secret code."""

    @clause
    def secret(self, c: Term) -> None:
        """code(C) :- C=[2,1,3,2]."""
        tell(c, cons(2, cons(1, cons(3, cons(2, nil())))))


class Length(Relation):
    """length(Xs, Acc, N): N = Acc + length(Xs)."""

    @clause
    def done(self, xs: Term, acc: Term, n: Term) -> None:
        """length([],X,Y) :- X=Y."""
        empty(xs)
        tell(n, acc)

    @clause
    def step(self, xs: Term, acc: Term, n: Term) -> None:
        """length([_|T],X,Y) :- X1:=X+1, length(T,X1,Y)."""
        _head, rest = uncons(xs)
        self(rest, acc + 1, n)


class Gen(Relation):
    """gen(N, Xs): the colours [N, N-1, ..., 1]."""

    @clause
    def positive(self, n: Term, xs: Term) -> None:
        """gen(N, X) :- N>0, M:=N-1 | X = [N|Xs], gen(M,Xs)."""
        guard(n > 0)
        rest = fresh()
        tell(xs, cons(n, rest))
        self(n - 1, rest)

    @clause
    def zero(self, n: Term, xs: Term) -> None:
        """gen(N, X) :- N=:=0 | X = []."""
        guard(n == 0)
        tell(xs, nil())


class Count(Relation):
    """count(Xs, M, N): N = M + length(Xs)."""

    @clause
    def done(self, xs: Term, m: Term, n: Term) -> None:
        """count([],M,N) :- M = N."""
        empty(xs)
        tell(n, m)

    @clause
    def step(self, xs: Term, m: Term, n: Term) -> None:
        """count([_|Xs],M,N) :- M1:=M+1 | count(Xs,M1,N)."""
        _head, rest = uncons(xs)
        self(rest, m + 1, n)


class Combo(Relation):
    r"""combo(Cs, L, O1, O2): O1 \ O2 is [C|L] for each colour C in Cs."""

    @clause
    def done(self, cs: Term, prefix: Term, o1: Term, o2: Term) -> None:
        """combo([], _, O1,O2) :- O1=O2."""
        empty(cs)
        tell(o1, o2)

    @clause
    def step(self, cs: Term, prefix: Term, o1: Term, o3: Term) -> None:
        """combo([C|Cs], L, O1,O3) :- O1 = [[C|L]|O2], combo(Cs, L, O2,O3)."""
        c, rest = uncons(cs)
        o2 = fresh()
        tell(o1, cons(cons(c, prefix), o2))
        self(rest, prefix, o2, o3)


class AddMyself(Relation):
    r"""addmyself(Is, Myself, O1, O2): O1 \ O2 is every partial guess in Is extended by each colour of Myself."""

    @clause
    def done(self, items: Term, myself: Term, o1: Term, o2: Term) -> None:
        """addmyself([], _, O1,O2) :- O1=O2."""
        empty(items)
        tell(o1, o2)

    @clause
    def step(self, items: Term, myself: Term, o1: Term, o3: Term) -> None:
        """addmyself([I|Is], Myself, O1,O3) :- combo(Myself, I, O1,O2), addmyself(Is, Myself, O2,O3)."""
        i, rest = uncons(items)
        o2 = fresh()
        _combo(myself, i, o1, o2)
        self(rest, myself, o2, o3)


class GenGuess(Relation):
    """genGuess(N, In, L, Out): extend every partial guess in In by one colour, N more times."""

    @clause
    def done(self, n: Term, ins: Term, colours: Term, out: Term) -> None:
        """genGuess(0,In,_,Out) :- Out=In."""
        guard(n == 0)
        tell(out, ins)

    @otherwise
    def more(self, n: Term, ins: Term, colours: Term, out: Term) -> None:
        """Extend every partial guess by one more colour.

        otherwise. genGuess(N,In,L,Out) :- N1:=N-1 | addmyself(In,L,Temp,[]), genGuess(N1,Temp,L,Out).
        """
        temp = fresh()
        _addmyself(ins, colours, temp, nil())
        self(n - 1, temp, colours, out)


class GenGuesses(Relation):
    """genGuess(Out, L, CL): Out is every guess of CL colours drawn from L (NC^CL of them)."""

    @clause
    def go(self, out: Term, colours: Term, cl: Term) -> None:
        """genGuess(Out,L,CL) :- N:=CL-1, addmyself([[]],L,In,[]), genGuess(N,In,L,Out)."""
        n, ins = fresh(), fresh()
        tell(n, cl - 1)  # a body `:=`: waits for CL, which length/3 is still computing
        _addmyself(cons(nil(), nil()), colours, ins, nil())
        _gen_guess(n, ins, colours, out)


class Exact(Relation):
    """exact(X, Y, Bulls, I, X1, Y1): Bulls = I + matching positions; X1 / Y1 are the leftovers."""

    @clause
    def done(self, xs: Term, ys: Term, n: Term, i: Term, x1: Term, y1: Term) -> None:
        """exact([],T2,N,I,S1,S2) :- N=I, S2=T2, S1=[]."""
        empty(xs)
        tell(n, i)
        tell(y1, ys)
        tell(x1, nil())

    @clause
    def bull(self, xs: Term, ys: Term, n: Term, i: Term, x1: Term, y1: Term) -> None:
        """exact([H|T],[H|T2],N,I,S1,S2) :- add(I, 1, I1) | exact(T,T2,N,I1,S1,S2)."""
        h, t = uncons(xs)
        h2, t2 = uncons(ys)
        guard(h == h2)
        self(t, t2, n, i + 1, x1, y1)

    @otherwise
    def miss(self, xs: Term, ys: Term, n: Term, i: Term, x1: Term, y1: Term) -> None:
        """No bull here: keep both colours for the cows count.

        otherwise. exact([X|T1],[Y|T2],N,I,X1,Y1) :- X1 = [X|S1], Y1 = [Y|S2], exact(T1,T2,N,I,S1,S2).
        """
        x, t1 = uncons(xs)
        y, t2 = uncons(ys)
        s1, s2 = fresh(), fresh()
        tell(x1, cons(x, s1))
        tell(y1, cons(y, s2))
        self(t1, t2, n, i, s1, s2)


class Inexact(Relation):
    """inexact(Xs, Choice, Cows, I): Cows = I + leftovers of Xs that occur somewhere in Choice."""

    @clause
    def no_choice(self, xs: Term, choice: Term, n: Term, i: Term) -> None:
        """inexact( _,[],N,I) :- I=N."""
        empty(choice)
        tell(n, i)

    @otherwise
    def done(self, xs: Term, choice: Term, n: Term, i: Term) -> None:
        """No leftovers: the count is complete.

        otherwise. inexact([], _,N,I) :- I=N.
        """
        empty(xs)
        tell(n, i)

    @clause
    def step(self, xs: Term, choice: Term, n: Term, i: Term) -> None:
        """inexact([Ht|Tt],Choice,N,I) :- delete(Choice,Ht,F,F,Choice,Tt,N,I)."""
        ht, tt = uncons(xs)
        f = fresh()
        _delete(choice, ht, f, f, choice, tt, n, i)


class Delete(Relation):
    """delete(List, X, F, NewChoice, Choice, Tt, N, I): remove the first X from List, then continue inexact."""

    @clause
    def absent(self, lst: Term, x: Term, f: Term, new_choice: Term, choice: Term, tt: Term, n: Term, i: Term) -> None:
        """delete([],_,_,_,Choice,Tt,N,I) :- inexact(Tt,Choice,N,I)."""
        empty(lst)
        _inexact(tt, choice, n, i)

    @clause
    def found(self, lst: Term, x: Term, f: Term, new_choice: Term, choice: Term, tt: Term, n: Term, i: Term) -> None:
        """delete([X|Y],X,F,NewChoice,_,Tt,N,I) :- I1:=I+1 | F = Y, inexact(Tt,NewChoice,N,I1)."""
        x1, y = uncons(lst)
        guard(x1 == x)
        tell(f, y)
        _inexact(tt, new_choice, n, i + 1)

    @otherwise
    def skip(self, lst: Term, x: Term, f: Term, new_choice: Term, choice: Term, tt: Term, n: Term, i: Term) -> None:
        """Not this colour: keep it and look further down the list.

        otherwise. delete([X1|Y],X,F,NewChoice,Choice,Tt,N,I) :- F = [X1|Z],
            delete(Y,X,Z,NewChoice,Choice,Tt,N,I).
        """
        x1, y = uncons(lst)
        z = fresh()
        tell(f, cons(x1, z))
        self(y, x, z, new_choice, choice, tt, n, i)


class Eval(Relation):
    """eval(X, Y, Bulls, Cows): score guess X against Y."""

    @clause
    def go(self, x: Term, y: Term, bulls: Term, cows: Term) -> None:
        """eval(X,Y,Bulls,Cows) :- exact(X,Y,Bulls,0,X1,Y1), inexact(X1,Y1,Cows,0)."""
        x1, y1 = fresh(), fresh()
        _exact(x, y, bulls, 0, x1, y1)
        _inexact(x1, y1, cows, 0)


class Loop(Relation):
    """loop(Bulls, Cows, Guess, CL, Plist, A, N, NG, S0, S1): act on a guess's score against the code."""

    @clause
    def solved(
        self,
        bulls: Term,
        cows: Term,
        guess: Term,
        cl: Term,
        plist: Term,
        a: Term,
        n: Term,
        ng: Term,
        s0: Term,
        s1: Term,
    ) -> None:
        """loop(CL, _, _, CL, _, A, _, _, S0, S1) :- S0 = [A|S1]."""
        guard(bulls == cl)
        tell(s0, cons(a, s1))

    @otherwise
    def deeper(
        self,
        bulls: Term,
        cows: Term,
        guess: Term,
        cl: Term,
        plist: Term,
        a: Term,
        n: Term,
        ng: Term,
        s0: Term,
        s1: Term,
    ) -> None:
        """Not solved yet, and guesses left: try another round.

        otherwise. loop(Bulls,Cows,Guess,CL,Plist,A,N,NG,S0,S1) :- Bulls < CL, add(N, 1, N1), N1 < NG |
            spawn(Plist,Plist,CL,[p(Bulls,Cows,Guess)|A],N1,NG,S0,S1).
        """
        guard(bulls < cl)
        guard(n + 1 < ng)
        _spawn(plist, plist, cl, cons(struct('p', bulls, cows, guess), a), n + 1, ng, s0, s1)

    @otherwise
    def exhausted(
        self,
        bulls: Term,
        cows: Term,
        guess: Term,
        cl: Term,
        plist: Term,
        a: Term,
        n: Term,
        ng: Term,
        s0: Term,
        s1: Term,
    ) -> None:
        """Out of guesses: this search path yields no solution.

        otherwise. loop(_,_,_,_,_,_,_,_,S0,S1) :- S0=S1.
        """
        tell(s0, s1)


class Check(Relation):
    """check(OldCows, Cows, OldBulls, Bulls, Gs, Guess, ...): is the guess consistent with one earlier feedback?"""

    @clause
    def consistent(
        self,
        old_cows: Term,
        cows: Term,
        old_bulls: Term,
        bulls: Term,
        gs: Term,
        guess: Term,
        cl: Term,
        plist: Term,
        a: Term,
        n: Term,
        ng: Term,
        s0: Term,
        s1: Term,
    ) -> None:
        """check(Sum,Sum,Bulls,Bulls,Gs,Guess,CL,Plist,A,N,NG,S0,S1) :- test(Gs,Guess,Plist,CL,A,N,NG,S0,S1)."""
        guard(old_cows == cows)
        guard(old_bulls == bulls)
        _test(gs, guess, plist, cl, a, n, ng, s0, s1)

    @otherwise
    def inconsistent(
        self,
        old_cows: Term,
        cows: Term,
        old_bulls: Term,
        bulls: Term,
        gs: Term,
        guess: Term,
        cl: Term,
        plist: Term,
        a: Term,
        n: Term,
        ng: Term,
        s0: Term,
        s1: Term,
    ) -> None:
        """The guess contradicts an earlier score: this search path yields no solution.

        otherwise. check(_,_,_,_,_,_,_,_,_,_,_,S0,S1) :- S0=S1.
        """
        tell(s0, s1)


class Test(Relation):
    """test(History, Guess, Plist, CL, A, N, NG, S0, S1): check Guess against the history, then against the code."""

    @clause
    def against_history(
        self, history: Term, guess: Term, plist: Term, cl: Term, a: Term, n: Term, ng: Term, s0: Term, s1: Term
    ) -> None:
        """Score Guess against one earlier guess, then check that the feedback agrees.

        test([p(OldBulls,OldCows,Tried)|Gs],Guess,Plist,CL,A,N,NG,S0,S1) :-
            eval(Guess,Tried,Bulls,Cows), check(OldCows,Cows,OldBulls,Bulls,Gs,Guess,CL,Plist,A,N,NG,S0,S1).
        """
        p, gs = uncons(history)
        old_bulls, old_cows, tried = unstruct(p, 'p', 3)
        bulls, cows = fresh(), fresh()
        _eval(guess, tried, bulls, cows)
        _check(old_cows, cows, old_bulls, bulls, gs, guess, cl, plist, a, n, ng, s0, s1)

    @clause
    def against_code(
        self, history: Term, guess: Term, plist: Term, cl: Term, a: Term, n: Term, ng: Term, s0: Term, s1: Term
    ) -> None:
        """Score Guess against the secret code, then act on the result.

        test([],Guess,Plist,CL,A,N,NG,S0,S1) :-
            code(Code), eval(Guess,Code,Bulls,Cows), loop(Bulls,Cows,Guess,CL,Plist,A,N,NG,S0,S1).
        """
        empty(history)
        code = fresh()
        _code(code)
        bulls, cows = fresh(), fresh()
        _eval(guess, code, bulls, cows)
        _loop(bulls, cows, guess, cl, plist, a, n, ng, s0, s1)


class Spawn(Relation):
    r"""spawn(Guesses, Plist, CL, A, N, NG, S0, S1): try every guess after history A; solutions go into S0 \ S1."""

    @clause
    def done(self, guesses: Term, plist: Term, cl: Term, a: Term, n: Term, ng: Term, s0: Term, s1: Term) -> None:
        """spawn([], _, _,_,_, _,S0,S1) :- S0=S1."""
        empty(guesses)
        tell(s0, s1)

    @clause
    def step(self, guesses: Term, plist: Term, cl: Term, a: Term, n: Term, ng: Term, s0: Term, s2: Term) -> None:
        """spawn([G|Gs],Plist,CL,A,N,NG,S0,S2) :- test(A,G,Plist,CL,A,N,NG,S0,S1), spawn(Gs,Plist,CL,A,N,NG,S1,S2)."""
        g, gs = uncons(guesses)
        s1 = fresh()
        _test(a, g, plist, cl, a, n, ng, s0, s1)
        self(gs, plist, cl, a, n, ng, s1, s2)


class Solve(Relation):
    """solve(NG, NC, Out): Out is the list of all solutions (each a history of p/3 feedback)."""

    @clause
    def go(self, ng: Term, nc: Term, out: Term) -> None:
        """Enumerate the NC^CL guesses and start the search from an empty history.

        solve(NG,NC,Out) :- code(C), length(C,0,CL), gen(NC,Clist),
            genGuess(Guesses,Clist,CL), spawn(Guesses,Guesses,CL,[],0,NG,Out,[]).
        """
        c, cl, clist, guesses = fresh(), fresh(), fresh(), fresh()
        _code(c)
        _length(c, 0, cl)
        _gen(nc, clist)
        _gen_guesses(guesses, clist, cl)
        _spawn(guesses, guesses, cl, nil(), 0, ng, out, nil())


class Go(Relation):
    """go(NG, NC, N): N is the number of solutions with at most NG guesses over NC colours."""

    @clause
    def solve_and_count(self, ng: Term, nc: Term, n: Term) -> None:
        """go(NG,NC,N) :- solve(NG,NC,A), count(A,N)."""
        a = fresh()
        _solve(ng, nc, a)
        _count(a, 0, n)


_code = Code()
_length = Length()
_gen = Gen()
_count = Count()
_combo = Combo()
_addmyself = AddMyself()
_gen_guess = GenGuess()
_gen_guesses = GenGuesses()
_exact = Exact()
_inexact = Inexact()
_delete = Delete()
_eval = Eval()
_loop = Loop()
_check = Check()
_test = Test()
_spawn = Spawn()
_solve = Solve()
go = Go()


def main() -> None:
    """Print the solution count for go(3, 3), as mastermind.kl1 does (860)."""
    print(f'mastermind go(3, 3): {go(3, 3)} solutions for the code [2, 1, 3, 2]')


if __name__ == '__main__':
    main()
