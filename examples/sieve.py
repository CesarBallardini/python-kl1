"""KL1 Sieve of Eratosthenes, ported to python-kl1 with the clause DSL.

Mirrors ``ch04-.../primes_sieve.kl1``, fully as relations::

    primes(Limit, Ps)      :- naturalNumbers(2, Limit, Ns), sieve(Ns, Ps).
    naturalNumbers(Low, High, Ns) :- Low > High | Ns = [].
    naturalNumbers(Low, High, Ns) :- Low =< High | Ns = [Low|N1s], naturalNumbers(Low+1, High, N1s).
    sieve([], Ps)          :- Ps = [].
    sieve([P|Ns], Ps)      :- Ps = [P|P1s], filter(P, Ns, Fs), sieve(Fs, P1s).
    filter(P, In, Out)     :- ...

``Primes`` is a **compound** relation: its body wires ``NaturalNumbers`` into ``Sieve``, and
``Sieve`` in turn uses ``Filter``. Sub-relations are held as class attributes and
called through ``self``. Run it with ``uv run python examples/sieve.py``.
"""

from python_kl1.core import Var, drain
from python_kl1.dsl import Relation, Term, clause, cons, empty, fresh, guard, nil, session, tell, uncons


class NaturalNumbers(Relation):
    """naturalNumbers(Low, High, Ns): Ns is the stream Low, Low+1, ..., High."""

    @clause
    def done(self, low: Term, high: Term, ns: Term) -> None:
        """naturalNumbers(Low, High, Ns) :- Low > High | Ns = []."""
        guard(low > high)
        tell(ns, nil())

    @clause
    def more(self, low: Term, high: Term, ns: Term) -> None:
        """naturalNumbers(Low, High, Ns) :- Low =< High | Ns = [Low|N1s], naturalNumbers(Low+1, High, N1s)."""
        guard(low <= high)
        n1s = fresh()
        tell(ns, cons(low, n1s))
        self(low + 1, high, n1s)


class Filter(Relation):
    """filter(P, In, Out): drop multiples of P from the stream In."""

    @clause
    def at_end(self, p: Term, ins: Term, fs: Term) -> None:
        """filter(_, [], Fs) :- Fs = []."""
        empty(ins)
        tell(fs, nil())

    @clause
    def keep(self, p: Term, ins: Term, fs: Term) -> None:
        """filter(P, [N|Ns], Fs): keep N when N mod P is nonzero."""
        n, ns = uncons(ins)
        guard(n % p != 0)
        f1s = fresh()
        tell(fs, cons(n, f1s))
        self(p, ns, f1s)

    @clause
    def drop(self, p: Term, ins: Term, fs: Term) -> None:
        """filter(P, [N|Ns], Fs): drop N when N mod P is zero."""
        n, ns = uncons(ins)
        guard(n % p == 0)
        self(p, ns, fs)


class Sieve(Relation):
    """sieve(In, Ps): Sieve of Eratosthenes -- a compound of Sieve and Filter."""

    sift = Filter()  # sub-relation held as a class attribute

    @clause
    def at_end(self, ins: Term, ps: Term) -> None:
        """sieve([], Ps) :- Ps = []."""
        empty(ins)
        tell(ps, nil())

    @clause
    def prime(self, ins: Term, ps: Term) -> None:
        """sieve([P|Ns], Ps) :- Ps = [P|P1s], filter(P, Ns, Fs), sieve(Fs, P1s)."""
        p, ns = uncons(ins)
        p1s = fresh()
        tell(ps, cons(p, p1s))
        fs = fresh()
        self.sift(p, ns, fs)
        self(fs, p1s)


class Primes(Relation):
    """primes(Limit, Ps): Ps is the primes up to Limit -- a compound of NaturalNumbers and Sieve."""

    naturals = NaturalNumbers()
    sieve = Sieve()

    @clause
    def go(self, limit: Term, ps: Term) -> None:
        """primes(Limit, Ps) :- naturalNumbers(2, Limit, Ns), sieve(Ns, Ps)."""
        ns = fresh()
        self.naturals(2, limit, ns)
        self.sieve(ns, ps)


primes = Primes()


def main() -> None:
    """Print the primes up to 30 (matching primes_sieve.kl1)."""
    with session() as engine:
        result = Var()
        primes(30, result)  # spawn -- `result` is a future output stream
        print(list(drain(engine, result)))  # consumed lazily


if __name__ == '__main__':
    main()
