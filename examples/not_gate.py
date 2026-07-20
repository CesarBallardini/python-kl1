"""KL1 logical NOT gate, ported to python-kl1 with the clause DSL.

Mirrors ``ch03-metamorphosis/not.kl1``. The clauses (methods) and the query
function live on one object -- the ``NotGate`` relation, which suspends until its
input is bound. Run it with ``uv run python examples/not_gate.py``.
"""

from python_kl1.dsl import Relation, Term, clause, guard, tell


class NotGate(Relation):
    """not(In, Out): logical negation over 0/1."""

    @clause
    def zero(self, input_bit: Term, output_bit: Term) -> None:
        """not(In, Out) :- In = 0 | Out = 1."""
        guard(input_bit == 0)
        tell(output_bit, 1)

    @clause
    def one(self, input_bit: Term, output_bit: Term) -> None:
        """not(In, Out) :- In = 1 | Out = 0."""
        guard(input_bit == 1)
        tell(output_bit, 0)


not_gate = NotGate()


def main() -> None:
    """Print not(0) and not(1)."""
    print('not(0) =', not_gate(0))
    print('not(1) =', not_gate(1))


if __name__ == '__main__':
    main()
