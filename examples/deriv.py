"""KL1 symbolic differentiation, ported to python-kl1 with the clause DSL.

In the spirit of ``examples/deriv.kl1``: differentiate an expression with respect to
``x``. Expressions are compound terms (**functors**): the atom ``x``, ``const(N)``,
``plus(A, B)``, ``times(A, B)``. This is the example the compound-term / functor feature
(``struct`` / ``unstruct``) unlocks.

Adaptation: constants are wrapped as ``const(N)`` rather than left as bare numbers, because
the DSL has no numeric type guard / ``otherwise`` to tell a bare number from the variable
``x``. Run it with ``uv run python examples/deriv.py``.
"""

from python_kl1.core import Struct, Value, Var, deref
from python_kl1.dsl import Relation, Term, clause, fresh, guard, session, struct, tell, unstruct


class Deriv(Relation):
    """deriv(Expr, D): D is d(Expr)/dx."""

    @clause
    def variable(self, expr: Term, d: Term) -> None:
        """deriv(x, D) :- D = const(1)."""
        guard(expr == 'x')
        tell(d, struct('const', 1))

    @clause
    def constant(self, expr: Term, d: Term) -> None:
        """deriv(const(_), D) :- D = const(0)."""
        unstruct(expr, 'const', 1)
        tell(d, struct('const', 0))

    @clause
    def sum(self, expr: Term, d: Term) -> None:
        """deriv(plus(A, B), D) :- deriv(A, DA), deriv(B, DB), D = plus(DA, DB)."""
        a, b = unstruct(expr, 'plus', 2)
        da = fresh()
        db = fresh()
        self(a, da)
        self(b, db)
        tell(d, struct('plus', da, db))

    @clause
    def product(self, expr: Term, d: Term) -> None:
        """deriv(times(A, B), D) :- D = plus(times(A, DB), times(B, DA))."""
        a, b = unstruct(expr, 'times', 2)
        da = fresh()
        db = fresh()
        self(a, da)
        self(b, db)
        tell(d, struct('plus', struct('times', a, db), struct('times', b, da)))


deriv = Deriv()


def show(expr: Value) -> str:
    """Render an expression term as readable infix text."""
    expr = deref(expr)
    if isinstance(expr, Struct):
        if expr.name == 'const':
            return str(deref(expr.args[0]))
        if expr.name == 'plus':
            return f'({show(expr.args[0])} + {show(expr.args[1])})'
        if expr.name == 'times':
            return f'({show(expr.args[0])} * {show(expr.args[1])})'
    return str(expr)  # the atom 'x'


def main() -> None:
    """Differentiate x*x + x with respect to x."""
    expr = Struct('plus', (Struct('times', ('x', 'x')), 'x'))
    with session() as engine:
        d = Var()
        deriv(expr, d)
        engine.run()
        print(f'd/dx {show(expr)} = {show(d)}')


if __name__ == '__main__':
    main()
