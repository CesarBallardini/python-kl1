# python-kl1

[![check](https://github.com/CesarBallardini/python-kl1/actions/workflows/check.yml/badge.svg)](https://github.com/CesarBallardini/python-kl1/actions/workflows/check.yml)
[![pytest](https://github.com/CesarBallardini/python-kl1/actions/workflows/pytest.yml/badge.svg)](https://github.com/CesarBallardini/python-kl1/actions/workflows/pytest.yml)
[![security](https://github.com/CesarBallardini/python-kl1/actions/workflows/security.yml/badge.svg)](https://github.com/CesarBallardini/python-kl1/actions/workflows/security.yml)

A Python library for **KL1-style concurrent programming** — the concurrent-logic /
Guarded Horn Clauses (GHC) model from Japan's ICOT Fifth Generation project. Concurrent
processes communicate only through shared **single-assignment logic variables** and
synchronize by **data-flow**: a goal suspends until the data it needs is bound. No locks,
no shared mutable state, no backtracking.

> **New here?** Start with the **[tutorial](tutorial.md)** — the concepts, setup, the
> eager-vs-`session` calling styles, streaming to/from ordinary Python, and when this style
> is a good fit for your code.

See [`python-kl1-general.md`](python-kl1-general.md) for the
findings and design notes distilled from the KLIC reference implementation.

> For the development tooling (uv, ruff, type checkers, tests, security, the `Makefile`),
> see **[tooling.md](tooling.md)**.

## Concepts

- **`LogicVar`** — a write-once logic variable with a per-variable wake-list. Binding it is
  both the sole act of communication and the sole wake-up signal.
- **`Stream`** — an incremental list over logic variables; the KL1 dataflow channel.
- **`Engine`** — a cooperative, deterministic scheduler that interleaves goals until
  quiescence. Also a context manager (`with Engine() as engine: ...` runs on exit).
- **Clause DSL** — write predicates as `Relation` subclasses whose clauses are methods:
  committed choice, guards that suspend on unbound data, and `[H|T]` / `[]` list patterns.

## Quickstart

Set up the environment (see [tooling.md](tooling.md) for details):

```bash
make install
```

Run an example:

```bash
uv run python examples/factorial.py   # 1! = 1 ... 11! = 39916800
uv run python examples/not_gate.py    # not(0) = 1 ; not(1) = 0
uv run python examples/sieve.py       # [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
```

Write a relation — clauses are methods, and calling it runs the query:

```python
from python_kl1.dsl import Relation, clause, fresh, guard, tell


class Factorial(Relation):
    @clause                       # fact(1, R) :- R = 1.
    def base(self, n, r):
        guard(n == 1)
        tell(r, 1)

    @clause                       # fact(N, R) :- N > 1 | fact(N-1, R1), R := R1 * N.
    def step(self, n, r):
        guard(n > 1)
        r1 = fresh()
        self(n - 1, r1)           # recurse: spawn a sub-goal
        tell(r, r1 * n)


factorial = Factorial()
factorial(5)                      # 120  (eager). For streams / dataflow, use session().
```

## Layout

```
src/python_kl1/
  core/
    terms.py      # the value model: Value, Cons cells, Struct (functors), NIL
    logicvar.py   # single-assignment logic variables + unification
    engine.py     # cooperative interleaving scheduler (context manager)
    stream.py     # streams over logic variables (Producer, drain, map/filter)
    goal.py       # committed-choice goal reduction (the raw layer)
  dsl.py          # KL1-style clause DSL: Relation subclasses, @clause, guard/tell,
                  #   list + functor patterns; calling a relation (eager) or session (lazy)
examples/         # not_gate, factorial, sieve, bank_account (ports of the KL1 originals)
tests/            # unit tests per module
tutorial.md       # hands-on guide: concepts, setup, calling styles, when to use it
python-kl1-general.md   # KL1 findings + library design notes
tooling.md        # development tooling (uv, ruff, type checkers, tests, security)
```

The modules stack in layers (data → logic variables → runtime substrate → DSL); see
**[`python-kl1-general.md`](python-kl1-general.md) §5** for the diagram, the dependency
rules, and how the layers are enforced (import-linter).

## License

MIT — see [LICENSE](LICENSE).
