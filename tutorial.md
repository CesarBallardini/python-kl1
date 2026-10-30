# python-kl1 tutorial: concurrent logic programming inside everyday Python

`python-kl1` lets you write **KL1-style concurrent logic** — the Guarded Horn Clauses
(GHC) model from Japan's Fifth Generation project — as ordinary Python classes, and then
call them from ordinary Python code. There are no threads, no locks, and no `async`/`await`.
Concurrent "processes" talk to each other only by **binding shared single-assignment
variables**, and they **suspend automatically** until the data they need shows up.

This tutorial is about the *seam*: how KL1 relations plug into normal Python functions,
loops, lists, and iterators — and when reaching for this style actually pays off.

- [1. The mental model in five ideas](#1-the-mental-model-in-five-ideas)
- [2. Setup](#2-setup)
- [3. Your first relation](#3-your-first-relation)
- [4. The two ways to call a relation: eager vs. session](#4-the-two-ways-to-call-a-relation-eager-vs-session)
- [5. Talking in streams (the Python ↔ KL1 data bridge)](#5-talking-in-streams-the-python--kl1-data-bridge)
- [6. Stateful processes and back-communication](#6-stateful-processes-and-back-communication)
- [7. The clause vocabulary, at a glance](#7-the-clause-vocabulary-at-a-glance)
- [8. When is this a good option?](#8-when-is-this-a-good-option)
- [9. Gotchas and mental-model tips](#9-gotchas-and-mental-model-tips)
- [10. Where to go next](#10-where-to-go-next)

---

## 1. The mental model in five ideas

Everything in the library is built from five concepts. Internalize these and the rest is syntax.

1. **Single-assignment logic variable (`Var`).** A variable that can be *bound* exactly
   once. Binding it is the *only* way processes communicate, and the *only* wake-up signal.
   No variable is ever re-assigned — there is no mutable state to race over.

2. **Data-flow suspension.** A goal that needs a value which isn't bound yet doesn't
   busy-wait or error — it **suspends**, and is automatically re-run when the value arrives.
   Synchronization is implicit in the data.

3. **Committed choice.** A relation has several clauses (like `if`/`elif` branches). The
   engine tries them in order; the **first** whose guards pass **commits** — its body runs
   and the others are discarded. There is **no backtracking** (unlike Prolog).

4. **Streams.** An incrementally-built linked list (`[head | tail]` cons cells) over logic
   variables. This is the KL1 communication channel — a producer binds the tail as it goes,
   a consumer reads it as it appears. Streams can be lazy and unbounded.

5. **Functors (compound terms, `Struct`).** Tagged records like `deposit(100)` or
   `move(a, c)` — how you send structured messages and pattern-match on them.

The runtime underneath is a **cooperative, single-threaded, deterministic scheduler**: it
interleaves ready goals until everything is either done or blocked (quiescence). "Concurrent"
here means *logically concurrent and deterministic* — not multi-core parallel.

---

## 2. Setup

Requires **Python 3.14+**. The library itself has **no runtime dependencies**.

**Working inside this repo** (the usual way while learning):

```bash
make install          # provisions the uv environment
uv run python examples/factorial.py
```

**Using it from your own project** — add it as a dependency with [uv](https://docs.astral.sh/uv/):

```bash
uv add "python-kl1 @ git+https://github.com/CesarBallardini/python-kl1"
```

Then in your code, you'll import from two places:

```python
# The DSL — how you write and run relations:
from python_kl1.dsl import (
    Relation, Term, clause,          # define a relation
    guard, tell, fresh,              # clause body basics
    uncons, empty, cons, nil,        # list patterns [H|T] / []
    struct, unstruct,                # functor patterns  name(args)
    merge,                           # many-to-one: fan several streams into one
    session,                         # the lazy/dataflow entry point
)

# The core runtime — logic variables and stream helpers:
from python_kl1.core import Var, deref, to_list, drain, stream_from
```

---

## 3. Your first relation

A relation is a subclass of `Relation`. Its **clauses are methods** decorated with
`@clause`, and they read almost exactly like their logic-programming source. Here is
factorial (`fact(N, R)` means "`R` is `N!`"):

```python
from python_kl1.dsl import Relation, Term, clause, fresh, guard, tell


class Factorial(Relation):
    @clause                                   # fact(1, R) :- R = 1.
    def base(self, n: Term, r: Term) -> None:
        guard(n == 1)                         # this clause only applies when N == 1
        tell(r, 1)                            # bind the result R to 1

    @clause                                   # fact(N, R) :- N > 1 | fact(N-1, R1), R := R1*N.
    def step(self, n: Term, r: Term) -> None:
        guard(n > 1)
        r1 = fresh()                          # a new logic variable for the sub-result
        self(n - 1, r1)                       # spawn the recursive sub-goal
        tell(r, r1 * n)                        # R = R1 * N (waits for R1 to be bound)


factorial = Factorial()
print(factorial(5))                            # 120
```

Things worth noticing, because they're the whole trick:

- **Clause arguments are `Term`s, not plain numbers.** `n` and `r` arrive wrapped so that
  Python operators build *logic expressions*: `n - 1` and `r1 * n` are deferred terms,
  `n == 1` and `n > 1` are *guards*, not booleans.
- **`guard(cond)`** decides the clause: it *fails* the clause if `cond` is false, and
  *suspends* the whole goal if `cond` can't be decided yet (an input is still unbound).
- **`tell(target, expr)`** is binding (`=`): it sets `target`, first waiting for any unbound
  variables inside `expr`.
- **`fresh()`** makes a new unbound logic variable.
- **Calling `self(...)`** inside a body **spawns a concurrent sub-goal** — it does not
  return a value; the answer flows back through the variable you passed in (`r1`).

The clauses are tried top-to-bottom; the first whose guards pass commits. Order matters:
put specific/guarded clauses before general fallbacks.

---

## 4. The two ways to call a relation: eager vs. session

A `Relation` instance is a **callable**, and it behaves in one of two ways depending on
where you call it. This is the main bridge between KL1 and everyday Python.

### Eager call — for a single answer

Call a relation at top level (from ordinary Python) with just its **inputs**. The library
appends a fresh output variable, runs the engine to completion, and hands you back the
plain Python value:

```python
factorial(5)          # 120        -- a normal int, ready to use
not_gate(0)           # 1
```

This is the "it's just a function" mode. Use it whenever you want one scalar result and
don't care about streaming or overlap. It's the simplest way to drop a relation into
existing code.

### Session call — for streams, dataflow, and overlap

Inside a `with session() as engine:` block, calling a relation **spawns** it with *exactly*
the arguments you pass (you create and pass the output variables yourself) and returns
`None`. Nothing computes until you drive the engine. Results are **futures** — logic
variables you read with `deref` afterward:

```python
from python_kl1.core import Var, deref
from python_kl1.dsl import session

with session() as engine:
    r = Var()
    factorial(5, r)        # spawn -- r is a future, nothing has run yet
    engine.run()           # drive the computation to quiescence
    print(deref(r))        # 120
```

Why bother, when the eager form is shorter? Because a session lets you:

- spawn **several** goals and let them **interleave** and feed each other,
- thread an **unresolved** variable from one goal into another (compose pipelines),
- consume **lazy / unbounded** streams on demand (see the next section),
- treat everything uniformly as a `Var` you `deref` when ready.

Rule of thumb: **eager for one value, session for streams and coordination.**

### Wrapping relations in ordinary Python

You freely mix the two worlds. Here Python's own `for`-loop drives a per-row KL1 relation
to build Pascal's triangle — each row is one small session:

```python
def rows(n: int) -> list[list]:
    result, row = [], [1]
    for _ in range(n):
        result.append(row)
        with session() as engine:
            out = Var()
            next_row(0, stream_from(engine, row), out)   # feed a Python list in
            engine.run()
            row = to_list(out)                            # get a Python list back
    return result
```

Python owns the loop and the accumulator; KL1 owns the per-step relational computation.
That layering — **normal Python on the outside, relations on the inside** — is the typical
shape of real code using this library.

---

## 5. Talking in streams (the Python ↔ KL1 data bridge)

Streams are how KL1 processes exchange sequences. Three helpers move data across the
boundary:

| Direction | Helper | What it does |
|-----------|--------|--------------|
| Python → KL1 | `stream_from(engine, iterable)` | turns a Python iterable into a stream (a `Var` bound to cons cells) |
| KL1 → Python (all at once) | `to_list(var)` | materializes a *finished* stream into a Python `list` |
| KL1 → Python (lazily) | `drain(engine, var)` | yields items **as they are produced**, driving the engine on demand |

### Eager consumption with `to_list`

Run to completion, then collect. The Sieve of Eratosthenes as communicating filters:

```python
from python_kl1.core import Var, to_list
from python_kl1.dsl import session

with session() as engine:
    result = Var()
    primes(30, result)                # spawn the whole pipeline
    engine.run()                      # run it to quiescence
    print(to_list(result))            # [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]
```

### Lazy consumption with `drain`

`drain` returns a normal Python iterator. Each time you pull an item, it drives the engine
just far enough to produce the next one — **demand-driven**, so it works for large or
in-principle-unbounded streams and integrates with Python's `for`, `list()`, `itertools`,
`next()`, generator expressions, etc.:

```python
from python_kl1.core import Var, drain
from python_kl1.dsl import session

with session() as engine:
    result = Var()
    primes(30, result)
    for p in drain(engine, result):   # consumed one at a time, on demand
        print(p)
```

`drain` is the point where KL1's lazy dataflow becomes an ordinary Python iterator — the
most natural way to hand streaming results back to everyday code.

---

## 6. Stateful processes and back-communication

A long-lived KL1 "object" is a relation that **serves a stream of messages** while carrying
its state as an argument. Because variables are single-assignment, a client that wants a
value back sends a **fresh reply variable inside the message** — a stamped, self-addressed
envelope — and the server binds it. This is the `struct` / `unstruct` (functor) feature.

A bank account that handles `deposit`, `debit`, and `balance`:

```python
from python_kl1.dsl import Relation, Term, clause, empty, guard, tell, uncons, unstruct


class Account(Relation):
    @clause                                             # accumulator([], _).
    def closed(self, msgs: Term, total: Term) -> None:
        empty(msgs)

    @clause                                             # deposit(A): total += A
    def deposit(self, msgs: Term, total: Term) -> None:
        msg, more = uncons(msgs)
        (amount,) = unstruct(msg, 'deposit', 1)
        self(more, total + amount)

    @clause                                             # debit(A): if it stays >= 0
    def debit(self, msgs: Term, total: Term) -> None:
        msg, more = uncons(msgs)
        (amount,) = unstruct(msg, 'debit', 1)
        guard(total - amount >= 0)
        self(more, total - amount)

    @clause                                             # balance(Reply): bind the client's var
    def balance(self, msgs: Term, total: Term) -> None:
        msg, more = uncons(msgs)
        (reply,) = unstruct(msg, 'balance', 1)
        tell(reply, total)                              # back-communication
        self(more, total)
```

Driving it from Python — build the message stream with `Struct`, drop a `Var` inside the
`balance` message, run, then read that same variable:

```python
from python_kl1.core import Struct, Var, deref, stream_from
from python_kl1.dsl import session

account = Account()

with session() as engine:
    reply = Var()
    messages = [
        Struct('deposit', (100,)),
        Struct('deposit', (50,)),
        Struct('debit', (30,)),
        Struct('balance', (reply,)),     # the reply variable rides inside the message
    ]
    account(stream_from(engine, messages), 0)
    engine.run()
    print(deref(reply))                  # 120
```

This request/reply-over-a-stream pattern is the KL1 equivalent of an actor with a mailbox,
or a channel-based service — but expressed with nothing but variables and binding.

### Many clients, one server: `merge`

A server reads *one* stream, so several clients need their streams **merged** into it. That is
KL1's `merge` — here `merge(*streams)`, a fair many-to-one fan-in: each element is forwarded
as soon as it appears on any input, and the merged stream closes once every input has closed.
Two depositors and a teller sharing the account:

```python
from python_kl1.core import Struct, Var, deref, stream_from
from python_kl1.dsl import merge, session

with session() as engine:
    reply = Var()
    alice = stream_from(engine, [Struct('deposit', (100,))])
    bob = stream_from(engine, [Struct('deposit', (50,))])
    teller = stream_from(engine, [Struct('balance', (reply,))])
    account(merge(alice, bob, teller), 0)   # one input stream, three clients
    engine.run()
    print(deref(reply))                      # 150 -- but read on
```

`merge` promises **fairness, not an order**. Nothing says the teller's `balance` arrives after
both deposits; on this deterministic engine the ready inputs interleave round-robin, so you
will see 150 every time, but a query racing a deposit is a genuine race — exactly as in KL1,
where an indeterminate merge is a race by construction. If one client's messages must precede
another's, put them on the *same* stream (sequence them); merge only what may interleave.

Inside a clause body `merge` is an expression: pass `merge(xs, ys)` straight to a consumer, or
bind an output argument with `tell(out, merge(xs, ys))`. To let a running client admit a new
one, split its own input by nesting — `tell(ins, merge(mine, theirs))` — the upstream merge
then sees `ins` close only when both halves have closed. (`examples/merge.py` ports KLIC's
`merge` demo this way, fanning K streams in through nested mergers.)

---

## 7. The clause vocabulary, at a glance

Everything you write inside a clause body comes from this small set:

| Construct | Meaning | Behavior on unbound input |
|-----------|---------|---------------------------|
| `guard(cond)` | Test a guard (`==`, `!=`, `<`, `<=`, `>`, `>=`) | **suspends** if undecidable; **fails** the clause if false |
| `tell(target, expr)` | Bind `target` to `expr` (KL1 `=` / `:=`) | waits for `expr`'s unbound vars, then binds |
| `fresh()` | Make a new logic variable (as a `Term`) | — |
| `self(...)` / `other_rel(...)` | Spawn a concurrent sub-goal | returns `None`; answers flow through passed vars |
| `uncons(term)` → `(head, tail)` | List pattern `[H\|T]` | **suspends** if unbound; **fails** if not a cons cell |
| `empty(term)` | List pattern `[]` | **suspends** if unbound; **fails** if not `[]` |
| `cons(h, t)` / `nil()` | Build `[h\|t]` / `[]` (for `tell`) | — |
| `struct(name, *args)` | Build a functor `name(args)` (for `tell`) | — |
| `unstruct(term, name, arity)` → tuple | Destructure functor `name(...)` | **suspends** if unbound; **fails** on wrong name/arity/type |
| `merge(*streams)` → merged stream | Fair many-to-one merge (KL1 `merge`) | forwards each element as its input binds; closes once **all** inputs have closed |
| `@otherwise` (instead of `@clause`) | Default clause (KL1 `otherwise.`): tried only once every clause above it has **failed** | **waits** while any clause above is suspended; mark only the first clause after each `otherwise.` |

Arithmetic on terms — `+ - * // %` — builds deferred expressions; comparisons build guards.
Both are evaluated lazily, only once their variable leaves are bound.

The suspend-vs-fail distinction is the heart of it: **fail** rejects *this clause* (try the
next one); **suspend** parks the *whole goal* until more data arrives, then retries from the
top. You rarely trigger these explicitly — they fall out of `guard`, `uncons`, `empty`, and
`unstruct` doing the right thing on unbound data.

> **Escape hatch.** For lower-level stream work outside the DSL, `python_kl1.core` also
> exposes `open_stream`, `put`, `close`, `each`, `collect`, `map_stream`, `filter_stream`,
> `merge_streams` (the engine-level form of `merge`) and a `Producer` — plus the raw goal
> layer (`call`, `commit`, `suspend`, `fail`). You
> won't need these to start; the DSL is the intended front door.

---

## 8. When is this a good option?

This is a specialized tool. It shines for a particular shape of problem and is the wrong
choice for many others. Be honest about which you have.

### Good fits ✅

- **Pipelines of communicating stages** — producer → filter → transform → consumer, where
  each stage is a process reading and writing streams (the sieve is the canonical example).
- **Dataflow coordination** — you have a tangle of "compute X once Y and Z are ready"
  dependencies and want the *suspension/wake-up wiring done for you* instead of hand-rolling
  futures, callbacks, or locks.
- **Lazy / unbounded sequences with backpressure** — demand-driven generation where the
  consumer's pace controls the producer (via `drain`).
- **Declarative relational search** — puzzles and combinatorial problems (N-queens,
  constraint-style generate-and-test) that read naturally as clauses.
- **Deterministic, reproducible concurrency** — because scheduling is single-threaded and
  deterministic, runs are repeatable; great for *testing and reasoning about* concurrent
  logic without heisenbugs.
- **Learning / teaching** concurrent logic programming, GHC, KL1, or dataflow — and
  experimenting with the object/message-stream/reply-variable idiom.

### Poor fits ❌ — reach for the standard library instead

- **CPU-bound speedup across cores.** The engine is cooperative and single-threaded; it
  gives you *no* parallel speedup. Use `multiprocessing` or a native extension.
- **High-throughput real I/O concurrency** (network servers, many sockets). Use `asyncio`
  or threads — this library models *logical* concurrency, not I/O multiplexing.
- **Plain sequential logic.** If a normal function, comprehension, or generator expresses
  it clearly, just write that. The DSL adds indirection that only pays off when you actually
  need dataflow suspension or committed-choice search.
- **Mutable, in-place state.** Single-assignment means no rebinding, no in-place updates,
  no shared mutable objects. State is threaded as arguments (as in the bank account).
- **Performance-critical hot paths.** It's an interpreter running atop CPython; expect
  meaningful per-goal overhead. Prototype and model with it; don't put it in a tight loop.

A useful test: *"Is the hard part of my problem the coordination — who waits for what — more
than the raw computation?"* If yes, this style can make that coordination disappear into the
data. If the coordination is trivial, you don't need it.

---

## 9. Gotchas and mental-model tips

- **A variable binds once.** Trying to bind an already-bound variable to a conflicting
  value raises a `UnificationError`. "Communication is binding" — design around it, don't
  fight it.
- **Clause order is behavior.** Committed choice takes the *first* clause whose guards pass.
  Put the specific, guarded clauses first and any guard-free fallback last. There is no
  backtracking to undo a commit.
- **A guard-free fallback is *not* an otherwise — use `@otherwise`.** A trailing `@clause`
  with no guards commits as soon as it is tried, even while the clauses above it are merely
  *suspended* on input that has not arrived yet. KL1's `otherwise.` waits for them to *fail*,
  and so does `@otherwise` (`examples/mastermind.py`: its defaults wait for the `Bulls`/`Cows`
  a concurrent `eval` is still computing). Mark only the first clause after each
  `otherwise.`; the clauses after it in the same group stay `@clause`.
- **Nothing runs until you drive the engine.** In a session, spawning only queues work.
  Call `engine.run()` (run to quiescence), or consume via `drain` (run on demand). Forgetting
  to drive the engine looks like "my variable is still unbound."
- **`self(...)` returns `None`.** It spawns a sub-goal; the result comes back through the
  variable you passed, read later with `deref` — it is *not* a Python return value.
- **Deadlock = quiescence with unbound outputs.** If everything suspends waiting on data
  nothing will ever produce (e.g. a clause that never gets a base case), the engine simply
  goes quiet and your future stays unbound. Check that some clause actually *binds* the
  outputs and terminates.
- **`to_list` needs a finished, proper stream;** `deref` gives you whatever a variable holds
  right now (possibly still a `Var`). Use `to_list`/`deref` *after* driving the engine.

---

## 10. Where to go next

- **`examples/`** — runnable ports of the classic KL1 programs, from simplest to most
  involved: `not_gate.py`, `factorial.py`, `sieve.py`, `bank_account.py`, `qsort.py`,
  `hanoi.py`, `deriv.py`, `pascal.py`, `kkqueen.py`, `qlay.py`, `merge.py`, `pp.py`,
  `mastermind.py`, `puzzle.py`, `wave.py`, `life.py`, `turtles.py`. Read them in that order.
- **`python-kl1-general.md`** — the design notes and KL1 concepts distilled from the KLIC
  reference implementation and the Huntbach & Ringwood book, plus the layered architecture
  (§5) and a backlog of further programs (Appendix C).
- **`README.md`** — quickstart and module layout; **`tooling.md`** — the dev tooling.

The shortest path to fluency: copy `factorial.py`, change it into a relation of your own,
run it eagerly, then convert it to a `session()` and consume its output with `drain`. Once
those two calling styles feel natural, the rest of the library is just more clause
vocabulary.
