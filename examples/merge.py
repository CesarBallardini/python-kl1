"""KLIC's ``merge`` demo, ported to python-kl1 with the clause DSL.

Mirrors ``kl1c/examples/merge.kl1``::

    main :- go(0, 100).

    go(K, N) :- K > N | true.
    go(K, N) :- K =< N | m(K), K1 := K+1, go(K1, N).

    m(K) :- generic:new(merge, In, Out),
            generic:new(vector, In0, K),
            send_and_close(0, K, In0, In),
            count(Out, 0, K).

    send_and_close(N, N, V0, V) :- V = V0.
    send_and_close(K, N, V0, V) :- K < N |
            generic:set_element(V0, K, _, [1], V1), K1 := K+1, send_and_close(K1, N, V1, V).

    count([], N, N).
    count([C|S], K, N) :- K1 := K+C, count(S, K1, N).

For every K from 0 to 100, ``m`` merges K one-element streams ``[1]`` into one stream and
checks that exactly K elements come out and that the merged stream then closes. KLIC fans the
K inputs in through a *vector* ``{[1], [1], ...}`` bound to the merger's input; python-kl1 has
no vectors, so ``SendAndClose`` builds the same fan-in by **nesting mergers** -- each slot is
``V = merge([1], V1)`` and the last is ``V = []``. (That nesting is also how a running merge
input is split to admit a new client: ``tell(ins, merge(in1, in2))``, KLIC's
``In = {In1, In2}``.) ``Count`` returns its total through an output variable and ``Go`` checks
it against K the way the original does -- by unification, so a mismatch raises
``UnificationError``. Run it with ``uv run python examples/merge.py``.
"""

from python_kl1.dsl import Relation, Term, clause, cons, empty, fresh, guard, merge, nil, session, tell, uncons


class Count(Relation):
    """count(S, K, N): N is K plus the sum of the elements of the stream S."""

    @clause
    def at_end(self, s: Term, k: Term, n: Term) -> None:
        """count([], N, N)."""
        empty(s)
        tell(n, k)

    @clause
    def more(self, s: Term, k: Term, n: Term) -> None:
        """count([C|S], K, N) :- K1 := K+C, count(S, K1, N)."""
        c, s1 = uncons(s)
        self(s1, k + c, n)


class SendAndClose(Relation):
    """send_and_close(K, N, V): V fans in N-K one-element streams [1] -- nested mergers for KLIC's vector."""

    @clause
    def done(self, k: Term, n: Term, v: Term) -> None:
        """send_and_close(N, N, V0, V) :- V = V0.  -- no slots left: the fan-in ends here."""
        guard(k == n)
        tell(v, nil())

    @clause
    def more(self, k: Term, n: Term, v: Term) -> None:
        """send_and_close(K, N, V0, V) :- K < N | slot K := [1], send_and_close(K+1, N, V1, V)."""
        guard(k < n)
        v1 = fresh()
        tell(v, merge(cons(1, nil()), v1))
        self(k + 1, n, v1)


class MergeCount(Relation):
    """m(K, Total): merge K one-element streams into one and count what comes out."""

    count = Count()
    send_and_close = SendAndClose()

    @clause
    def go(self, k: Term, total: Term) -> None:
        """m(K) :- generic:new(merge, In, Out), send_and_close(0, K, In0, In), count(Out, 0, K)."""
        ins = fresh()
        out = merge(ins)
        self.send_and_close(0, k, ins)
        self.count(out, 0, total)


class Go(Relation):
    """go(K, N): run m for every K in K..N, checking that each total is its K."""

    m = MergeCount()

    @clause
    def done(self, k: Term, n: Term) -> None:
        """go(K, N) :- K > N | true."""
        guard(k > n)

    @clause
    def more(self, k: Term, n: Term) -> None:
        """go(K, N) :- K =< N | m(K), K1 := K+1, go(K1, N)."""
        guard(k <= n)
        total = fresh()
        self.m(k, total)
        tell(total, k)  # the original hands K to count/3's result slot: a mismatch is a unification failure
        self(k + 1, n)


merge_count = MergeCount()
go = Go()


def main() -> None:
    """Run ``go(0, 100)`` as merge.kl1 does: every merged count must match its K."""
    with session() as engine:
        go(0, 100)
        engine.run()
    print('merged K one-element streams for every K in 0..100: each count matched')


if __name__ == '__main__':
    main()
