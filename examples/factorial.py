"""KL1 factorial, ported to python-kl1 with the clause DSL.

Mirrors ``examples/fact.kl1``. The clauses (methods) and the query function
(``solve`` / calling the instance) live on one object -- the ``Factorial`` relation.
Run it with ``uv run python examples/factorial.py``.
"""

from python_kl1.dsl import Relation, Term, clause, fresh, guard, tell


class Factorial(Relation):
    """fact(N, R): bind R to N!."""

    @clause
    def base(self, n: Term, r: Term) -> None:
        """fact(1, R) :- R = 1."""
        guard(n == 1)
        tell(r, 1)

    @clause
    def step(self, n: Term, r: Term) -> None:
        """fact(N, R) :- N > 1 | fact(N-1, R1), R := R1 * N."""
        guard(n > 1)
        r1 = fresh()
        self(n - 1, r1)
        tell(r, r1 * n)


factorial = Factorial()


def main() -> None:
    """Print 1!, 5!, and 11! (11! matches fact.kl1)."""
    for n in (1, 5, 11):
        print(f'{n}! =', factorial(n))


if __name__ == '__main__':
    main()
