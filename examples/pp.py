"""KLIC's ``pp`` benchmark, ported to python-kl1 with the clause DSL.

Mirrors ``kl1c/examples/pp.kl1``::

    main :- pp(12).

    pp(N) :- true | p([N|L],M), r(M,L).

    p([],M) :- true | M=[].
    p([N|L],M) :- true | M=[N|M1], p(L,M2), p(M2,M1).

    r([0|_],M) :- true | M=[].
    r([N|L1],M) :- N > 0, N1:=N-1 | M=[N1|M1], r(L1,M1).

``pp`` wires two stream processes into a feedback loop: ``p`` copies ``[N|L]`` onto ``M`` and
``r`` turns ``M`` back into ``L``, each element one less than the one it read, closing ``L`` at
the first 0. So ``M`` is ``N, N-1, ..., 0`` -- but by an exponential route: ``p(Xs) = [X0 |
p(p(Xs'))]`` is the identity on finite lists, yet every tail passes through *two* further
copies, so element k crosses 2^k copy processes and the 13 elements of ``pp(12)`` cost about
2^13 reductions. That is the point of the benchmark: five clauses that spawn thousands of
fine-grained, data-suspended goals. The original prints nothing; ``main()`` prints the stream
it builds. Run it with ``uv run python examples/pp.py``.
"""

from python_kl1.core import to_list
from python_kl1.dsl import Relation, Term, clause, cons, empty, fresh, guard, nil, tell, uncons


class P(Relation):
    """p(In, M): copy In onto M, routing the tail through two more copies -- the identity, exponentially."""

    @clause
    def at_end(self, ins: Term, m: Term) -> None:
        """p([], M) :- M = []."""
        empty(ins)
        tell(m, nil())

    @clause
    def more(self, ins: Term, m: Term) -> None:
        """p([N|L], M) :- M = [N|M1], p(L, M2), p(M2, M1)."""
        n, rest = uncons(ins)
        m1 = fresh()
        m2 = fresh()
        tell(m, cons(n, m1))
        self(rest, m2)
        self(m2, m1)


class R(Relation):
    """r(In, M): M is each element of In minus one, until a 0 arrives and closes M."""

    @clause
    def at_zero(self, ins: Term, m: Term) -> None:
        """r([0|_], M) :- M = []."""
        n, _ = uncons(ins)
        guard(n == 0)
        tell(m, nil())

    @clause
    def more(self, ins: Term, m: Term) -> None:
        """r([N|L1], M) :- N > 0, N1 := N-1 | M = [N1|M1], r(L1, M1)."""
        n, l1 = uncons(ins)
        guard(n > 0)
        m1 = fresh()
        tell(m, cons(n - 1, m1))
        self(l1, m1)


class Pp(Relation):
    """pp(N, M): M is the stream N, N-1, ..., 0, built by the p/r feedback loop."""

    p = P()
    r = R()

    @clause
    def go(self, n: Term, m: Term) -> None:
        """pp(N) :- p([N|L], M), r(M, L)."""
        ls = fresh()
        self.p(cons(n, ls), m)
        self.r(m, ls)


pp = Pp()


def main() -> None:
    """Run ``pp(12)`` as pp.kl1 does and print the stream it builds."""
    print(to_list(pp(12)))


if __name__ == '__main__':
    main()
