# python-kl1 — General findings

**Date:** 2026-07-19
**Goal:** design a Python library, `python-kl1`, that lets us write multi-threaded
programs in the *KL1 style* — the concurrent-logic / Guarded-Horn-Clauses (GHC)
programming model.

This document records what we learned from reading the KLIC reference
implementation in the [kl1c repo](https://github.com/CesarBallardini/kl1c) (its
`examples/`, `agent-oriented-programming/` book transcriptions, and the primitive
`tests/`). It is a living document: we will refine it step by step.

---

## 1. What KL1 is

KL1 (Kernel Language 1) is the concurrent logic programming language from Japan's
ICOT Fifth Generation project. KLIC is its portable C implementation (compiles a
`.kl1` to C, then to a native binary). The underlying formalism is **Guarded Horn
Clauses (GHC)** — Prolog-like syntax, but with *committed-choice concurrency*
instead of backtracking.

The mental model that matters for us: a KL1 program is a **pool of concurrent
processes (goals)** that communicate **only** through shared **logic variables**.
There is no shared mutable state, no locks, no explicit thread handles. Synchronization
is *data-driven*: a process blocks until the data it needs to inspect becomes bound.

This is exactly the property we want to reproduce in Python.

---

## 2. The computational model (what we must reproduce)

### 2.1 Clauses, guards, and commitment

A clause has the shape:

```
Head :- Guard | Body.
```

- `|` is the **commit operator**.
- Everything **left** of `|` (the *guard*) is a set of **passive tests** — they may
  read variables but must **not bind** any variable belonging to the caller.
- Everything **right** of `|` (the *body*) runs **only after** the clause commits.
- A clause with no `|` is all body (guard = `true`).
- `:- module main.` declares a module; execution starts at `main`.

Example (`examples/fact.kl1`):

```prolog
fact(1, R) :- R = 1.
fact(N, R) :- N > 1, N1 := N-1 |          % guard: test N>1, compute N1
    fact(N1, R1),                          % body: spawn sub-goal
    R := R1 * N.
```

### 2.2 Committed choice (no backtracking)

Several clauses may match a goal. Their guards are evaluated **concurrently**; the
**first** clause whose guard succeeds is **committed to**, and all other candidates
are discarded. Unlike Prolog, there is **no backtracking** — once committed, the
choice is final. This is what makes the model tractable for real parallelism.

`otherwise.` (seen in `examples/turtles.kl1`) marks a *default* clause: it commits
only if every clause **above** it failed. It is the ordered-fallback escape hatch.

### 2.3 Suspension (data-flow synchronization)

If a goal's guards cannot yet decide (because a variable they need to test is still
unbound), the goal **suspends** and is re-tried when some other process binds that
variable. This is the *only* synchronization mechanism. There are no semaphores; a
consumer of a stream simply suspends on the stream's tail until a producer extends it.

### 2.4 Single-assignment logic variables

- `=` is **unification / binding** (write-once): a variable is bound at most once.
- `:=` is **arithmetic assignment** (evaluates an expression to a number).
- `=<`, `>`, `>=`, `=:=`, `=\=` are **arithmetic guards** (passive comparisons).
- Binding a variable is the act of *communication*: whoever binds it, wakes whoever
  was suspended on it.

A variable is a one-shot channel. Reuse across "messages" is achieved with lists
whose tail is an unbound variable — the **stream** (next section).

---

## 3. Concurrency patterns found in the corpus

These are the recurring idioms; the Python library must make each of them natural.

### 3.1 Streams = incremental lists (Kahn–McQueen)

A **stream** is a list `[X0, X1, ... | Tail]` whose tail is an unbound variable.
Producer binds the tail to `[Xn | NewTail]`; consumer suspends on the tail until it
appears. This gives lazy, unbounded, single-producer/single-consumer channels *for
free* from unification.

Sieve of Eratosthenes (`primes_sieve.kl1`) — a classic pipeline of concurrent
filter processes:

```prolog
sieve([P|Ns], Ps)  :- true | Ps = [P|P1s], filter(P, Ns, Fs), sieve(Fs, P1s).
filter(P, [N|Ns], Fs)  :- 0 =\= N mod P | Fs = [N|F1s], filter(P, Ns, F1s).
filter(P, [N|Ns], Fs)  :- 0 =:= N mod P | filter(P, Ns, Fs).
```

`natNums`, `sieve`, and every `filter` run **concurrently**; each stage consumes its
input stream and produces its output stream, suspending whenever it gets ahead of its
producer.

### 3.2 The object / client–server pattern (stream of messages)

An "object" is a **long-lived process that serves a stream of request messages** and
carries its state as an argument (accumulator style). The client sends a message
containing an unbound variable — a "stamped, self-addressed envelope" — and the
server binds it with the reply.

Bank account (`bank_account.kl1`):

```prolog
accumulator([deposit(A)|More], Total) :- New := Total + A | accumulator(More, New).
accumulator([debit(A)|More], Total)   :- New := Total - A, New >= 0 | accumulator(More, New).
accumulator([balance(Amt)|More], Total) :- Amt = total(Total), accumulator(More, Total).
accumulator([], _) :- true | true.
```

Note the reply (`Amt = total(Total)`) is bound in the **body**, never in the guard —
a guard may not instantiate the caller's variables (§2.1).

### 3.3 Merge — many-to-one channels

A single server serves one stream, so *many* clients need their streams **merged**
into one. KLIC provides a `merge` builtin object:

```prolog
generic:new(merge, In, Out)           % examples/merge.kl1: In is the merged-in side, Out the fair-merged output
generic:new(merge, {S1, S2}, Merged)  % tests/merge/merge_new.kl1: vector of input streams -> one Merged output
```

Merge fairly interleaves multiple producer streams into one consumer stream. It is the
standard way to build a shared server with multiple clients.

In python-kl1 it is a stream helper rather than a special object: `merge_streams(engine, *streams)`
in `core/stream.py`, surfaced in the DSL as `merge(*streams)` (a clause body writes
`tell(out, merge(xs, ys))`, or passes `merge(xs, ys)` straight to a consumer). There are no
vectors, so the `{S1, S2}` split that admits a new client into a running merge is written by
nesting — `tell(ins, merge(in1, in2))` — which keeps the "closes when every input has closed"
rule exact with no central registry. See `examples/merge.py`.

### 3.4 Difference lists (O(1) concatenation)

A pair `(List, Tail)` where `Tail` is the still-open end, letting a process append in
O(1) by binding `Tail`. Quicksort uses this to avoid any append (`qsort_dl.kl1`):

```prolog
qsort([Pivot|List], Sorted, Tail) :-
    part(List, Pivot, Lesser, Greater),
    qsort(Lesser,  Sorted,  [Pivot|GSorted]),   % threads the "hole"
    qsort(Greater, GSorted, Tail).
```

### 3.5 Priority annotations (`@`)

Goals can be annotated with scheduling priority:

- `Goal@priority(N)` — absolute priority (`examples/prio.kl1`).
- `Goal@lower_priority` — relative demotion (`examples/primesp.kl1`).

This is a *hint to the scheduler*, not a correctness feature. The Python library can
map this to a priority queue for runnable goals; a plain FIFO is a valid first cut.

### 3.6 Explicit `wait`

`wait(X)` (in `tests/sync/wait.kl1`) is a guard that suspends until `X` is bound
(instantiated to any non-variable), then succeeds. It is the explicit form of the
implicit suspension in §2.3 — occasionally useful to force a barrier.

### 3.7 I/O as a stream

Even I/O is a stream of messages. `klicio:klicio([stdout(Res)])` yields `normal(S)`;
the program binds `S = [putt(N), nl | S1]` to emit. Sockets/files use the same
message-difference-list model (`server.kl1`, `client.kl1`, `tests/streams/`).

---

## 4. Primitive inventory (from `tests/`, grouped)

The `tests/` tree (75 cases, 17 categories) is effectively an executable spec of the
KLIC primitive surface. Only a subset is *concurrency-relevant*; the rest are the
data/value layer we get from Python for free.

**Concurrency / process layer (the part `python-kl1` must actually implement):**

| KL1 primitive                      | Meaning                                          |
| ---------------------------------- | ------------------------------------------------ |
| `Head :- Guard \| Body`            | guarded clause, committed choice                 |
| `=`                                | unification / bind a logic variable (write-once) |
| `wait(X)`                          | suspend until `X` bound                          |
| streams (`[H\|T]` w/ open tail)    | data-flow channels                               |
| `generic:new(merge, In, Out)`      | many-to-one fair merge                           |
| `otherwise`                        | ordered default clause                           |
| `@priority(N)` / `@lower_priority` | scheduling hints                                 |
| `unbound/2`                        | test whether a variable is still unbound         |

**Value / data layer (map directly onto Python types — low priority to reimplement):**

- `arithmetic/` — `:=`, `+ - * / mod`, bitwise, integer compares.
- `comparison/` — `@< @=< @> @>=`, `compare/3`, `hash/2`, `\=`.
- `types/` — `atom integer float list atomic`.
- `float/` — full transcendental set.
- `aggregates/` — vectors `{..}` and strings (mutable-ish objects via `generic:*`).
- `atoms/`, `functors/` (`functor/3`, `arg/3`, `setarg/4`, `=..`), `functors`.
- `io/`, `streams/`, `unix/`, `timer/`, `merge/`, `random/`, `status/`, `meta/`.

For a first Python cut we lean on native Python for the value layer and focus the
library on the **process/variable/stream** machinery.

---

## 5. The implementation (current state)

> This section reflects what is actually built; it replaces the original design sketch.
> The library lives in `src/python_kl1/`; see the README architecture appendix for the
> layered dependency graph, and `examples/` for runnable ports.

### 5.1 Layers

Bottom-up, each layer building only on the ones below it — a DAG at runtime, enforced by
import-linter:

```
        dsl.py                          Layer 3 — KL1-style surface
   (Relation, @clause, guard/tell,
    session, struct/unstruct, solve)
          |  builds on engine + goal + logicvar + terms
          v
 engine.py · stream.py · goal.py        Layer 2 — runtime substrate (siblings)
  scheduler · dataflow   · committed
             channels      choice
          |  each builds on logicvar (+ terms)
          v
       logicvar.py                      Layer 1 — the one synchronization primitive
   (Var, unify, deref, wake-lists)
          |  builds on terms
          v
        terms.py                        Layer 0 — the value model (no runtime deps)
   (Value, Cons, Struct, Nil, Atom)
```

- **`core/terms.py`** — the value model. `type Value = Var | Cons | Struct | Nil | Atom`
  (`Atom = int | float | str | bool | None`). `Cons` is the list/stream cell; `Struct` is a
  general **functor** (`name` + `args`) for tagged terms; `NIL` is the empty list.
- **`core/logicvar.py`** — the single synchronization primitive. `Var` is write-once with a
  per-variable **wake-list**; `unify` is union-find + structural (recurses into `Cons` and
  `Struct`, name/arity checked); plus `deref`, `bind`, `is_bound`. Binding a variable fires
  its wake-list — the sole act of communication.
- **`core/engine.py`** — a cooperative, deterministic **interleaving scheduler** (a FIFO of
  runnable thunks; §3.11 of the book): `spawn`, `step`, `run`, `when_bound`, and a context
  manager that runs to quiescence on exit.
- **`core/stream.py`** — streams as incremental `Cons` lists over a `Var`: `stream_from`,
  `put`/`close`, `Producer` (context-manager write-end), `each`/`collect`/`drain`
  (`drain` is a lazy Python iterator), `map_stream`/`filter_stream`, `merge_streams` (KL1's
  fair many-to-one **merge**: one waiter per input feeding a shared `Producer`, closing once
  every input has closed), and `to_list`.
- **`core/goal.py`** — the raw **committed-choice** engine. A `Predicate` holds clauses that
  return `commit(body)` / `suspend(*vars)` / `fail()`; the reducer picks the first that
  commits, else suspends on the union of awaited vars and retries when any binds. `bind_from`
  models `:=` (arithmetic that waits for its operands).
- **`dsl.py`** — the KL1-style surface (next).

### 5.2 The DSL (`dsl.py`)

Relations are **classes**, clauses are **methods**:

```python
class Factorial(Relation):
    @clause                       # fact(1, R) :- R = 1.
    def base(self, n, r):
        guard(n == 1)
        tell(r, 1)

    @clause                       # fact(N,R) :- N>1 | fact(N-1,R1), R := R1*N.
    def step(self, n, r):
        guard(n > 1)
        r1 = fresh()
        self(n - 1, r1)           # spawn a sub-goal
        tell(r, r1 * n)
```

- Clause args arrive as **`Term`** objects; their operators build logic expressions
  (`n - 1`, `r1 * n`) and guards (`n == 1`, `n > 1`). Guards suspend on unbound inputs and
  fail the clause when false; `tell` binds (waiting for any unbound vars in the expression).
- **List patterns** `uncons` / `empty` (`[H|T]` / `[]`) with constructors `cons` / `nil`;
  **functor patterns** `unstruct(term, name, arity)` with constructor `struct(name, *args)`.
- **Merge** `merge(*streams)` — KL1's fair many-to-one channel as an expression: pass it to a
  consumer or bind an output with `tell(out, merge(xs, ys))`; dynamic fan-in is nesting,
  `tell(ins, merge(in1, in2))`.
- **Running a relation:** outside a session, `rel(*inputs)` is the **eager** query (append a
  fresh result, run to quiescence, return the value — an atom or a `Cons`-stream; `to_list`
  materialises a stream). Inside a **`session()`** (or a clause body), `rel(*args)` instead
  spawns lazily on the session engine and you read the variables you passed — the future /
  dataflow model. There is no separate `solve` method: calling the relation *is* the query.

### 5.3 What was decided

- **Substrate:** a single-threaded **cooperative interleaving** engine (deterministic,
  testable), not OS threads / asyncio — resolving the original open question. The `Engine`
  is swappable in principle (goals/streams reference it only as a type).
- **Guard safety:** enforced by construction — guards are `ask` (read/suspend only), bodies
  are `tell`; `guard` and `tell` are separate primitives.
- **Unification:** yes — write-once, union-find, structural over `Cons` and `Struct`.
- **Value layer:** an explicit `Value` union (not `object`), including functors (`Struct`).
- **Eager vs. lazy:** calling a relation is eager for a single-atom query; `session()` is the
  lazy, uniform, composable form for streams, the object pattern, and dataflow composition.
- **Merge:** an ordinary pattern over the substrate, not a first-class runtime object —
  `merge_streams` is one `when_bound` waiter per input writing to a shared `Producer`, so
  elements flow as they arrive, ready inputs interleave round-robin on the FIFO engine, and the
  output closes with the last input; the DSL's `merge(*streams)` is sugar over it. KLIC's
  vector split (`In = {In1, In2}`) becomes nesting, which needs no vectors.

### 5.4 The layering, and how it is enforced

The **`TYPE_CHECKING` blocks *are* the layering.** A few dependencies would be cycles at
runtime, so they live in `if TYPE_CHECKING:` — real only for the type checkers:

- `terms → logicvar`: `terms.py` needs `Var` for the `Value = Var | Cons | …` union, but
  `logicvar` imports `terms` at runtime.
- `stream` / `goal` → `engine`: both take an `engine: Engine` parameter, but `engine` sits
  below them.

So the runtime imports are the clean bottom-up layering (a DAG); the `TYPE_CHECKING` imports
mark exactly where it folds back for typing. That is why `pyright` / `pyrefly` see a fully
connected type graph while the import graph stays acyclic — and the flake8-type-checking
(`TCH`) lint rule, which sorts each dependency into runtime vs. typing-only, is what keeps
the two apart.

The runtime layering is checked in CI by **import-linter** (`make layers` /
`uv run lint-imports`); its layers contract is in `[tool.importlinter]` in `pyproject.toml`,
with `exclude_type_checking_imports = true` so only the runtime graph is constrained. A
lower-→-higher import fails the build.

---

## 6. Ported examples

In `examples/` (each also an executable test asserting the KL1 result):

- **`not_gate.py`** — `not.kl1`: committed choice over guards (`In=0|Out=1`, `In=1|Out=0`).
- **`factorial.py`** — `fact.kl1`: guarded recursion + `:=` (an eager query).
- **`sieve.py`** — `primes_sieve.kl1`: a concurrent stream pipeline, fully relational
  (`NaturalNumbers` → `Sieve` → `Filter`), composed via sub-relation attributes and run in a
  lazy `session()`.
- **`bank_account.py`** — `bank_account.kl1`: the client-server object with **functors** and
  a **reply variable** (back-communication) — deposit/debit/balance over a message stream.
- **`qsort.py`** — `qsort.kl1`: quicksort with a **difference-list** accumulator.
- **`hanoi.py`** — Towers of Hanoi: recursion + a difference list of `move(_,_)` functors.
- **`deriv.py`** — symbolic differentiation: **functor** pattern-matching (`struct` / `unstruct`).
- **`pascal.py`** — Pascal's triangle: a list-to-list transform (shift-and-add).
- **`kkqueen.py`** — `kkqueen.kl1`: N-Queens counting via a **difference-list of solutions**
  (no `merge`); the guard disjunction becomes committed-choice ordering.
- **`qlay.py`** — `qlay.kl1`: N-Queens via the **layered-streams** technique (Okimura); the
  two `otherwise.` defaults become a guard-free `keep` clause after the skip clauses.
- **`merge.py`** — `merge.kl1`: the **merge** primitive — K one-element streams fanned into one,
  counted, and checked to close; nested mergers stand in for KLIC's input vector.

**N-Queens two ways (`kkqueen` vs `qlay`).** The two ports solve the same problem with
different KL1 idioms:

- **`kkqueen` — candidate search.** Explicit backtracking: `queen` tries each column, `check`
  tests the diagonals against the placed board, and every full solution is appended to a
  **difference list** threaded through the search. Plain committed-choice recursion, one
  logical goal per placement attempt; the solution *boards* are built individually.
- **`qlay` — layered streams.** The *set* of partial solutions is represented compactly as a
  nested ("layered") stream whose common prefixes are shared; `filter` prunes the whole set
  against a newly placed queen in a single pass, and `lastFilter` flattens the final layer
  into full solutions. More intricate, but it avoids re-exploring shared prefixes.

Both give the same counts (N=8 → 92) and, in the cooperative engine, comparable time at these
sizes; the layered-streams sharing is what pays off at larger N. Notably, **neither needed
`merge` or `otherwise`** — the guard disjunctions and ordered defaults both reduce to
committed-choice ordering with a guard-free fallback clause (the same trick in both files).

The full backlog of unported programs — and which are blocked by a missing feature — is in
Appendix C.

---

## 7. Resolved questions & what's next

The first implementation settled the big choices (see §5.3): scheduler substrate
(cooperative interleaving); guard safety (the ask/tell split); unification (structural over
`Cons` and `Struct`); the value layer (an explicit `Value` union with functors); surface
syntax (the class-based DSL); eager vs. lazy (calling vs. `session`); and where **merge**
lives (an ordinary pattern over the stream layer — `merge_streams` / `merge` — not a
first-class runtime object). Several of those decisions are worth revisiting, and other gaps
remain.

Still open:

- **Threads vs. asyncio vs. greenlets** for the scheduler — which best models cheap,
  data-suspended goals? (KL1 goals are *very* fine-grained; native threads may be too
  heavy for `primes_sieve` at scale.)
- How faithfully do we enforce the *guard cannot bind caller vars* rule — statically,
  at runtime, or by convention?
- Do we need full **unification** (two unbound vars, compound terms) or is
  **assignment + pattern-match on Python data** enough for the target programs?
- Scope of the **value layer**: reuse Python ints/lists/dicts, or model KL1
  atoms/functors/vectors explicitly for fidelity?
- API ergonomics: how close to the `Head :- Guard | Body` notation can we get in
  idiomatic Python without a parser?
- **Priority / `@priority`, `otherwise`, `after(N)`** — scheduling/control annotations are
  not exposed (the FIFO engine ignores priority).
- **Relation inheritance** — clause collection uses a subclass's own methods only, so a
  `Relation` subclass does not inherit a parent's clauses.
- **`unify` uses Python `==`**, so `1 == 1.0` unifies — a divergence from KL1's distinct
  integer and float types.

---

## 8. Book study — Huntbach & Ringwood, *Agent-Oriented Programming: From Prolog to Guarded Definite Clauses* (1999)

> Summary of the full book, read from
> <https://github.com/CesarBallardini/kl1c/blob/main/biblio/Agent-Oriented-Programming-From-Prolog-to-Guarded-Definite-Clauses-Matthew_M._Huntbach.md>
> (Springer LNAI 1630). This is the canonical text behind the
> `agent-oriented-programming/` KL1 transcriptions in the
> [kl1c repo](https://github.com/CesarBallardini/kl1c). The concurrency
> core is Chapters 3–5; Chapters 6–10 are applications. Focus below is on what bears
> on the `python-kl1` design.

### Framing

The book is a genealogy and a manifesto. It traces a single line of descent — Prolog →
IC-Prolog → the Relational Language → Concurrent Prolog → Parlog → GHC → **KL1 / GDC** —
and argues that **committed-choice concurrent logic programming (GDC = Guarded Definite
Clauses) is the natural substrate for concurrent, distributed, object-, actor-, and
agent-oriented programming**. The central move is to abandon Prolog's *don't-know*
nondeterminism (search + backtracking) in favour of *don't-care* **indeterminacy**
(guards + commit), replacing control-flow sequencing with **event-driven condition
synchronization** carried by the single-assignment logic variable. What is lost is
completeness/invertibility; what is gained is a small, scalable process calculus in which
"a network of concurrent agents communicating over channels" and "a conjunction of goals
sharing logic variables" are the *same thing* (Table 4.8.1). GDC is deliberately generic —
"not quite the Japanese KL1 but generic" — so its lessons port directly to a KL1-style
Python runtime.

### Per-chapter summary

**1. The Art in Artificial Intelligence.** History of AI told as art-movements, structured
around two recurring themes: *search* (generate-and-test, breadth vs. depth-first,
combinatorial explosion, heuristics, constraint satisfaction, **least commitment**) and
*knowledge representation*. Load-bearing threads for us: the Horn/definite-clause + SLD-
resolution + unification substrate; least commitment as "defer decisions as long as
possible" ≈ dataflow suspension; Kowalski's **"algorithm = logic + control"**; and
Hewitt's actors / blackboard / open-systems metaphor of "control as a pattern of
message-passing among agents."

**2. Fifth Generation Architecture.** Rationale and post-mortem of the Japanese FGCS/ICOT
project (1982–92) that picked Prolog as a machine language and bet on logic + parallelism.
Relevant: the ICOT charter to *extend Prolog for writing operating systems* is exactly the
KL1/GHC lineage; the **cut** as the sequential ancestor of committed choice;
**metaprogramming / meta-interpretation / partial evaluation (Futamura)** flagged as
Prolog's key strengths (chapters 8–9); the von Neumann bottleneck and **Amdahl's law**
(speed-up capped by communication cost `C`) as cautions for any and-parallel model.

**3. Metamorphosis (Prolog → GDC).** *The conceptual core.* Derives GDC step-by-step from
the failure of naive parallel Prolog. Key mechanisms:
- **Premature binding problem.** In parallel Prolog, `conc` with an unbound first argument
  can commit to a wrong clause and instantiate a *shared* variable before another goal is
  ready — a mutual-exclusion / lost-update problem. Even `p(X,Y):-q(X),r(Y)` is unsafe when
  called `p(Z,Z)`.
- **Or-parallelism** ("clause-search parallelism") needs one binding frame per branch → a
  *tree* of binding contexts, not a stack; rejected as too expensive.
- **Condition synchronization** is the fix: split a clause into `head :- guard | body`. The
  guard uses an **instance/ask** primitive (`«`, "left is an instance of right") that may
  bind only clause-*local* variables and **suspends** the call if it is insufficiently
  instantiated to satisfy any clause's guard. This is *safe* (guards never bind caller
  variables). Sugar: move `«` constraints into head patterns (pattern-match, not unify)
  with `true` guards.
- **Commit / indeterminacy.** Only one clause whose guard succeeds is chosen ("committed
  choice"); no search beyond the guard. Loses completeness, keeps soundness; makes
  semantics functional/directed. `otherwise` and priority handle "when more than one guard
  holds."
- **Guard safety & deep guards.** User-defined goals in guards can leak recursive bindings
  → premature binding again. Fixes: copy endangered variables locally and unify only *after*
  commit; or hoist recursion into the body with an **arbiter** process so a tree of
  processes percolates the answer up. **Flat** GDC (FGHC/KL1) restricts guards to decidable
  primitives → guaranteed safe & decidable; search must then be *programmed*, not inherited.
- **Decision-tree compilation** of mutually exclusive guards (with `+` alternatives and
  `otherwise`) — the compilation target for a Python clause-indexer.
- §3.15 gives the full family tree (read-only vars vs. mode declarations vs.
  pattern-matching as the three synchronization schemes) ending at KL1 / KLIC.

**4. Event Driven Condition Synchronization.** *The concurrency cookbook.* Combining the
logic variable with condition synchronization *is* stream processing; "it is not the list
structure that gives rise to stream programming but the nondestructive assignment of
variables." Covers: streams-for-free (Sieve of Eratosthenes as a dynamically growing filter
pipeline); generators/transducers/filters/integrators; dataflow & Petri-net modelling;
**eager vs. lazy (demand-driven) producers** and how to program synchronous / bounded /
one-slot / N-slot (**difference-list**) buffers; **message passing** and the
**binding-conflict problem** (two producers of the same variable — a race that "can only
occur once" with single assignment); the **client-server paradigm** with the **reply-paid-
envelope / incomplete-message** pattern (`balance(Amount)`); **objects as perpetual
tail-recursive stream servers** carrying state in unshared arguments (`accumulator`);
user-defined **fair merge** (swap arguments each step to avoid starvation; biased merge =
priority) and **self-balancing (splay-tree) merge** with logarithmic delay;
**synchronization** via **continuations** (`eq(A,B,Cont)`) to sequence tell-operations and
implement RPC/atomic compound transactions without a separate mutex; **readers/writers**
with distributed **short-circuit** termination (Takeuchi); **dining philosophers**
(chopstick = combined mutex+merge; deadlock broken by asymmetry); the **Brock-Ackerman
anomaly** (indeterminate dataflow is *not* compositional — two processes with identical I/O
relations differ inside a feedback loop); **conditional/abductive semantics** with the
`<R,B,I>` (Reducible/Blocked/Irreducible) machine state, **open-world assumption** (no
failure — irreducible goals are conditional answers), and control primitives `otherwise`
and `after(N)` (time-out); implementation via `{f,X1..Xn}` tuples with `functor/arg/array`
primitives and the `testCommitAndSet` atomic primitive for the multiple-writer race.

**5. Actors and Agents.** Maps GDC onto Hewitt/Agha **Actors**: an actor's `case`/behavior
= guarded clauses; `send`/`become`/`create`/`forward` — GDC needs only *create* (bodies),
actor death is implicit (ephemeral goals), `forward` = shorting two streams (as in merge).
"Actors names local variables and message queues; GDC names only channels" (channels are
single-use, so a message *queue* is a nesting/list of channels + explicit merge). Worked
macro-protocols as concurrent-object programs: **haggling** (Winograd-Flores),
**Byzantine/consensus**, **Contract Net** with timeout-collected tenders, **auction/poker**.
**Neural networks in GDC**: a `tree` process self-replicates into a net of
`protoNeuron`/`pLN` actors; learning uses **back-communication** (reply variables carrying
`confirmed`/`incorrect` back down the same message) → natural back-propagation. **Conway's
Life**: each cell is an actor connected to neighbours by shared logic variables;
asynchronous yet "a cell cannot advance more than one generation ahead of a neighbour" —
self-synchronizing by data dependency; mutable arrays modelled as tail-recursive
`lookup`/`update` servers reusing the process descriptor. **Agent micro/meta
architectures**: Shoham-style `agent0(Stream,Beliefs,Commitments)`; time as a monotonic
`clock` counter (not a real-time clock); resource-bounded meta-interpreters
(`demo(KB,InGoals,Out,Resource)`) that program search as an explicit stream of disjuncts
because there is no backtracking. **Actor reconstruction of GDC** and the **inheritance
anomaly** (synchronization code — the guard — cannot be cleanly inherited).

**6. Concurrent Search.** The central cliché: **convert OR-parallelism to AND-parallelism**
— each search branch becomes its own actor with its *own* output channel, and a pluggable
combiner (`choose` = first, `append` = all-ordered, `merge` = all-temporal, `lowestcost`)
makes the indeterminate choice. Covers **speculative-parallelism control** (dummy `none`
sentinels; `found` + cheap `unknown` guard; atomic `test_and_set` on a shared solution
channel; short-circuit difference-list accumulators), the **priority pragma**
`actor@priority(P)` (priority attaches to *this* actor only — pass it down for inheritance;
priority-less/mandatory actors like `choose` must preempt `search` or you get livelock),
**process-per-node** search trees, **parallel branch-and-bound** (a `manager` actor holds
the best-cost bound), **parallel α-β**, and **layered streams**. Methodology: write the
maximally parallel declarative program first, then add priority/cutoff annotations, then
partial-evaluate.

**7. Distributed Constraint Solving.** DAI with no central coordinator: "what seem the
weaknesses of concurrent logic programming — no omniscience or omnipotence — are in fact its
strength." One idiom across three graph problems: **actor-per-vertex, stream-per-arc**,
long-lived actors via tail recursion, long-lived channels via incomplete messages.
All-pairs shortest path (asynchronous, converges at quiescence); graph colouring
(synchronous *by message protocol alone*, **back-communication** `mess(Col,Accepted,Return)`,
symmetry broken by integer **"social laws"**); minimal spanning tree (**dynamic** topology —
actors merge/terminate by passing **first-class channels inside messages** so mail to a
defunct actor is forwarded to its successor). "Improving the program improved the algorithm."

**8. Meta-interpretation.** The classic Prolog "vanilla" 3-liner and its **GDC form**
(`reduce(X=Y):-X=Y.` / `reduce(A):-otherwise|behavior(A,Body),reducelist(Body).`), object
programs reified as `behavior(Head,BodyList)` facts. Key insight: a monolingual interpreter
inherits control *implicitly* — "nothing in the interpreter indicates it is depth-first
left-to-right with backtracking." Enhancements by threading extra arguments: reduction
counters/tracers, **short-circuit termination detection**, forced sequentialization,
explicit `match(X,Y,Flag)`→true/false/suspend (making commitment inspectable),
**priority scheduling** (actors emit `req(P,Go)` to an explicit scheduler), explicit
**suspension wake-lists**, and a **bilingual** interpreter with its own `unify`+environment
to model backtracking (monolingual single-assignment *cannot*). Also GDC-hosted **Linda
tuple-space**, Occam, and lazy/eager λ-calculus (unbound result channels behave as
**futures**). Thesis: the meta-interpreter is "the third element that combines logic and
control" — but costs ~10× per layer, motivating chapter 9.

**9. Partial Evaluation.** Program specialization: run the *static* parts once, emit a
residual program. **Futamura projections** (specialize interpreter w.r.t. program =
compiler; self-apply = compiler-generator) justify "meta-interpreter + partial evaluator =
compiler," flattening chapter 8's layered overhead. Gives a concrete **GDC PE algorithm**
(unfold by normal GDC evaluation but leave output assignments suspended — Furukawa's rule),
a **stop criterion** via **generalization / anti-unification** (Plotkin lgg) with a
well-founded term-size ordering, and **actor fusion / deforestation** (fuse dependent
producer+consumer to eliminate the intermediary channel — e.g. `append & length →
append_length`). Notes that "an actor reacting to a partial message then suspending is
*almost identical to partial evaluation*."

**10. Agents and Robots.** The "agent" as the shift from closed world-modeller to active
participant. Contrasts Brooks's **reactive/subsumption** robots with **deliberative/
planning** agents and Etzioni's **softbots**. A worked GDC robot (`robot0..robot9` FSM over
sensor/effector streams) shows **actor = recursive state-continuation + streams**, and
honestly shows it can livelock. Develops **agents as concurrent OOP**: the `xyobj`
stream-object with `set`/`val`/`new`, **access classes** (capability streams),
**express/priority messages** (second stream taken only when the normal one is `unknown`, or
KL1 `alternatively`), **prototyping/delegation** via `otherwise`, and **biased merge /
append** as fairness knobs. Flags GDC's *missing* pieces: only a crude relative **priority**
(no resource *ownership*), **no real-time**, and **no failure handling** (no matching
behaviour ⇒ whole system fails). Concludes GDC is best seen not as parallel Prolog but as an
**abstract concurrent language coinciding with Actors / concurrent-OO**, with first-class
channels as **futures**, making it a superior coordination ("glue") language to Linda; I/O
is done the KLIC way — send `fwrite(x)` down a stream bound to stdout; **mobile agents**
migrate by packaging themselves as messages.

### GDC concurrency primitives & idioms (distilled)

Syntax: a clause is `head :- guard | body.` — `:-…|` is the **commit** operator; guard =
**ask** (test only), body = **tell** (`=` bind + spawn).

- **Guard / commit (committed choice).** Test-only guard; first satisfied clause commits; no
  search beyond it. `part([I|L],P,Le,Gr) :- P=<I | Gr=[I|Gr1], part(L,P,Le,Gr1).`
- **Ask primitives that suspend on unbound input.** `«` (instance), `==`/`=/=`, `=<`/`<`,
  `:=` (eval when RHS ground), `=:=`. Any call **suspends** until instantiated enough to
  satisfy *some* clause's guard — the only synchronization.
- **Tell / output.** Binding is done *only* in the body by the equality process `X=t`;
  guards must not bind caller variables (**guard safety**).
- **Streams.** Incrementally instantiated list `[Item|Tail]` = infinite async buffer.
  `nats(M,Ns):-M1:=M+1 | Ns=[M|R], nats(M1,R).`
- **Perpetual process / object.** Tail-recursive stream server; state in unshared args.
  `accumulator([deposit(A)|More],T):-NT:=T+A | accumulator(More,NT).`
- **Eager vs. demand-driven producer.** Reverse producer/consumer roles, or give both a head
  pattern, for lazy / synchronous behaviour; consumer sends a list of *unbound* slots to fill.
- **Bounded buffer (difference list).** `Channel=[_,_,_,_|End]`; consumer replaces one slot
  per message → N-slot buffer; `Chan\End` notation.
- **Reply-paid envelope / incomplete message.** Client sends `balance(Amount)` with `Amount`
  unbound; server binds it; consumer of `Amount` blocks until filled → back-channel reply.
- **Back-communication.** A message carries unbound reply variables the receiver fills later
  (`mess(Col,Accepted,Return)`); two-way handshake, no extra channel.
- **Continuations for sequencing.** `eq(A,B,Cont)` binds then runs `Cont`; nest to order
  tells; basis for RPC and atomic compound transactions without a mutex.
- **Fair merge / biased merge.** Many-to-one; swap args each recursion for fairness, fix them
  for priority. **Self-balancing (splay) merge** for log-depth fan-in.
- **Short-circuit termination.** Thread a variable through a chain of workers; the circuit
  "shorts" (`done`) only when all complete — distributed quiescence detection.
- **OR→AND search cliché.** Each branch = actor with its own channel; combiner
  (`choose`/`append`/`merge`/`lowestcost`) picks; sentinel `none` / `unknown`-guard / atomic
  `test_and_set` for cutoff.
- **`otherwise` / priority / `after(N)`.** `otherwise` fires only if all other guards fail
  (exhaustive, sound); `@priority(P)` schedules; `after(N)` is a timeout guard.
- **Mutable array / state.** A recursive `lookup`/`update` message server (tail call reuses
  the descriptor), or one actor per element.
- **`{f,X1..Xn}` tuples + `functor`/`arg`/`array` + `testCommitAndSet`.** Indexed access and
  the atomic guard-test-commit-and-bind to arbitrate the multiple-writer race safely.

### Implications for `python-kl1`

- **Model the single-assignment variable as the one synchronization primitive.** A logic var
  with states unbound → bound-once, plus a **suspension wake-list** of blocked processes per
  variable. Everything (streams, merge, client-server, futures, back-communication) falls out
  of it. Do *not* add locks/semaphores; condition synchronization is the whole model.
- **Guard = ask (no side effects); body = tell.** Enforce **guard safety**: guard primitives
  may inspect and suspend but must never bind a caller variable. Start with **flat guards**
  (decidable primitives only) as KL1/FGHC did — guaranteed safe and decidable. Defer
  deep/recursive guards.
- **Suspend, don't busy-wait.** A process not satisfying any clause guard registers on the
  wake-lists of the exact unbound variables it examined, re-scheduled only when one is bound.
- **Perpetual tail-recursive processes are your objects.** Servers consume a message stream
  and carry state in arguments; reuse the frame on tail call. This gives concurrent OOP,
  mutable state, and I/O for free.
- **Ship these idioms first (in order):** (1) stream producer/consumer + suspension;
  (2) `merge` (fair + biased); (3) perpetual stream-server object with reply-paid-envelope;
  (4) difference-list bounded buffer; (5) `otherwise` + priority scheduling; (6) short-circuit
  termination; (7) OR→AND concurrent search skeleton. These cover chapters 4–7.
- **Pitfalls the book explicitly warns about:**
  - **Premature binding** — never expose bindings to shared variables before commit; copy
    endangered vars locally and unify after commit, or hoist recursion into an arbiter body.
  - **Binding conflict / multiple writers** — with single assignment the race "can only happen
    once," but prefer single-producer channels; provide an atomic `testCommitAndSet` for real
    multi-writer arbitration; prefer textual clause priority for reproducibility.
  - **Brock-Ackerman anomaly** — indeterminate merge is *not compositional*; two processes with
    identical I/O relations can differ inside a feedback loop. Test cyclic/feedback topologies
    specifically. Reappears as the **inheritance anomaly** for synchronization code.
  - **Deadlock & starvation (dining philosophers)** — cyclic demand-driven chains deadlock under
    perfect symmetry; break symmetry; use `after(N)` timeouts and priorities to escape Blocked.
  - **Livelock in search** — any actor propagating "solution found" must have **higher priority
    than expanding actors**, or the search never stops.
  - **Speculative-parallelism blow-up** — control eager bodies with priorities / demand-driven
    producers / cutoffs.
- **Indeterminacy vs. determinism, not nondeterminism.** Commit to *don't-care* semantics: no
  backtracking, no goal failure, **open-world** (irreducible goals are conditional answers, not
  `false`). Search, negation, all-solutions must be **programmed** as explicit streams.
- **Runtime state = `<R,B,I>`.** Structure the scheduler around multisets of **R**educible /
  **B**locked / **I**rreducible goals; done when R is empty (may be non-terminating);
  B-nonempty-with-R-empty = deadlock to detect and report.
- **Priority is the only built-in control lever — and it is weak.** Provide `@priority`, FIFO
  within a band, and inheritance-by-parameter — but note the book's warning that agents also
  need resource ownership, real-time facilities, and failure handling; leave hooks.
- **I/O and side effects as messages on channels** (the KLIC way): no imperative `write`; bind
  a stream to stdout/stdin and send `fwrite(x)` terms. Channels double as **futures**.
- **Keep meta-interpretation and partial evaluation in view.** The `reduce`/`behavior(Head,
  Body)` reification is the natural shape for a Python interpreter and for programmable
  schedulers/tracers; the ~10× per-layer cost is real, so plan a source-to-source specializer /
  actor-fusion pass if hosting interpreters.

### Memorable quotes & section map

- "It is not the list structure that gives rise to stream programming but the nondestructive
  assignment of variables." (§4.5)
- "There is nothing in the interpreter that indicates that it is Prolog's depth-first
  left-to-right with backtracking control." (Ch. 8)
- "This technique of converting conceptually OR-parallelism to AND-parallelism is a cliché in
  concurrent logic programming." (Ch. 6)
- "Any mechanism that passes on the information that a solution has been found [must] have
  priority over further computations. Otherwise … livelock." (Ch. 6)
- "What at first seem to be the weaknesses of concurrent logic programming — its failure to
  offer any form of omniscience or omnipotence — is in fact its strength." (Ch. 7)
- "Almost accidentally, the guarded definite clause languages were found to correspond closely
  to the concurrent object-oriented paradigm." (Ch. 10)
- Section map: guards/commit/safety §3.10–3.13; decision-tree compilation §3.14; GDC family
  history §3.15; streams/eager-lazy §4.1–4.7; client-server & continuations §4.8–4.10;
  readers/writers §4.11; dining philosophers §4.12; Brock-Ackerman §4.13; `<R,B,I>` semantics
  & `otherwise`/`after` §4.14–4.16; Actor↔GDC & inheritance anomaly §5.1, §5.18–5.19;
  concurrent-search clichés Ch. 6; actor-per-vertex + back-communication Ch. 7; vanilla
  meta-interpreter Ch. 8; Futamura + actor fusion Ch. 9; channels-as-futures / coordination
  language Ch. 10.

---

## Appendix A: source material read

- [`kl1c/README.md`](https://github.com/CesarBallardini/kl1c/blob/main/README.md),
  [`kl1c/CLAUDE.md`](https://github.com/CesarBallardini/kl1c/blob/main/CLAUDE.md) — project
  rationale, KL1 language notes.
- [`kl1c/examples/`](https://github.com/CesarBallardini/kl1c/tree/main/examples) —
  `fact, qsort, merge, primesp, prio, pp, server, client, turtles`.
- [`kl1c/agent-oriented-programming/ch04-.../`](https://github.com/CesarBallardini/kl1c/tree/main/agent-oriented-programming/ch04-event-driven-condition-synchronization)
  — `primes_sieve, bank_account, qsort_dl` (transcribed from Huntbach & Ringwood,
  *Agent-Oriented Programming*).
- [`kl1c/tests/`](https://github.com/CesarBallardini/kl1c/tree/main/tests) —
  `merge/merge_new`, `sync/wait`, and the category `README.md` (75-case primitive spec).
- [`kl1c/biblio/`](https://github.com/CesarBallardini/kl1c/tree/main/biblio) — Huntbach &
  Ringwood, *Agent-Oriented Programming* (full book, summarized in §8); Chikayama 1996 KLIC
  paper and `KLIC.info.txt` reference manual (Predicate Index) — not yet mined in depth.

---

## Appendix B: KL1 in a nutshell — concepts, idioms, primitives

> A distilled, one-page reference for the whole document. §8 has the full book study; §2–3
> the model and patterns; this appendix compresses them into what to keep in your head while
> designing `python-kl1`. It is the "cheat sheet" — every line is load-bearing.

### The one big idea

A KL1 program is a **soup of concurrent processes (goals)** that share nothing but
**single-assignment logic variables** and synchronize **only by data-flow**: a process runs
when its input is instantiated enough to decide, otherwise it **suspends** until some other
process binds the variable it is waiting on. No threads-and-locks, no shared mutable state,
no backtracking. *Binding a variable is the sole act of communication and the sole
wake-up signal.* Reproducing exactly this in Python is the whole project.

### Central concepts

| Concept                 | One-line meaning                                                                                |
| ----------------------- | ----------------------------------------------------------------------------------------------- |
| **Guarded Horn Clause** | `Head :- Guard \| Body.` — the unit of program; the `\|` is **commit**.                         |
| **Guard (ask)**         | Passive tests, left of `\|`. May *read* and *suspend*, must **not bind** caller vars.           |
| **Body (tell)**         | Runs only after commit, right of `\|`. Binds variables (`=`) and spawns goals.                  |
| **Committed choice**    | Guards of matching clauses race; **first to succeed wins**, rest discarded. No backtracking.    |
| **Suspension**          | A goal that can't yet decide sleeps on the unbound var(s) it inspected; rebinding wakes it.     |
| **Single assignment**   | A logic variable is bound **at most once** (write-once). Second conflicting bind = error.       |
| **Indeterminacy**       | *don't-care* nondeterminism — commit to any viable clause; unlike Prolog's *don't-know* search. |
| **Open world**          | No goal "failure": an unmatched/irreducible goal is a *conditional answer*, not `false`.        |
| **`<R,B,I>` state**     | Runtime = multisets of **R**educible / **B**locked / **I**rreducible goals; done when R empty.  |

### Core operators (the value/guard layer)

- `=` — **unify / bind** a logic variable (write-once). The *tell* primitive.
- `:=` — **arithmetic assignment**: evaluate an expression to a number (suspends until ground).
- `=<  <  >  >=  =:=  =\=` — **arithmetic guards** (passive comparisons; suspend if unbound).
- `wait(X)` — explicit guard: suspend until `X` is bound to any non-variable.
- `otherwise` — a **default clause** that fires only when every clause above it failed.
- `@priority(N)` / `@lower_priority` — **scheduling hints** on a spawned goal (not correctness).
- `after(N)` — a **timeout** guard (escape from a permanently Blocked state).

### The idioms that matter (in porting order)

1. **Stream** — an incremental list `[X0,X1,…|Tail]` with an unbound tail; the universal
   async channel. Producer binds the tail, consumer suspends on it.
   `nats(M,Ns) :- M1:=M+1 | Ns=[M|R], nats(M1,R).`
2. **Perpetual process = object** — a tail-recursive goal serving a message stream, carrying
   state in an argument. This *is* the KL1 object / actor.
   `acc([deposit(A)|More],T) :- NT:=T+A | acc(More,NT).`
3. **Reply-paid envelope (incomplete message)** — client sends a message holding an *unbound*
   variable; server binds it with the reply; client's consumer blocks until filled.
   `acc([balance(Amt)|More],T) :- Amt=total(T), acc(More,T).`
4. **Merge** — many-to-one fair channel (`generic:new(merge, Ins, Out)`); *fair* by swapping
   arguments each step, *biased* (priority) by keeping them fixed; splay-merge for log fan-in.
5. **Difference list** — a `(List, Tail)` pair for O(1) append and as an N-slot bounded buffer
   (`[_,_,_,_|End]`); used by `qsort_dl` to sort with no `append`.
6. **Short-circuit termination** — thread one variable through a chain of workers; it "shorts"
   to `done` only when all finish → distributed quiescence / barrier detection.
7. **Back-communication** — a message carries reply variables the receiver fills later; a
   two-way handshake with no extra channel (basis for back-propagation, negotiation).
8. **OR→AND search** — turn each search branch into its own goal with its own output channel;
   a combiner (`choose`/`append`/`merge`/`lowestcost`) makes the indeterminate pick.
9. **Continuations for sequencing** — `eq(A,B,Cont)` binds then runs `Cont`; nest to order
   *tell*s and build atomic compound transactions without a mutex.
10. **I/O as a stream** — no imperative `write`; bind a stream to stdout and send terms
    (`S=[putt(N),nl|S1]`, or `fwrite(X,_)`); channels double as **futures**.

### Pitfalls the model forces you to respect

- **Premature binding** — never let a guard/commit expose a binding on a *shared* variable
  before commit. Guard safety (guards can't bind caller vars) exists precisely to prevent this.
- **Binding conflict** — two writers to one variable; single-assignment makes it a
  once-only race — prefer single-producer channels, arbitrate the rest atomically.
- **Brock–Ackerman anomaly** — indeterminate merge is **not compositional**: identical
  input→output behaviour can differ inside a feedback loop. Test cyclic topologies explicitly.
- **Deadlock / starvation** — symmetric demand-driven cycles (dining philosophers) deadlock;
  break symmetry, add `after(N)` timeouts and priorities.
- **Search livelock** — a goal announcing "solution found" must outrank goals that expand the
  search, or it never stops.

### The 30-second takeaway for `python-kl1`

Build **one** primitive well — a write-once `LogicVar` with a per-variable **wake-list** —
and make **`Stream`, merge, objects, futures, and back-communication all fall out of it**.
Keep **guards side-effect-free** (start with *flat*, decidable guards), **suspend instead of
busy-wait**, model **objects as tail-recursive stream servers**, and treat **committed choice
+ open-world indeterminacy** (no backtracking, no failure) as non-negotiable semantics.
Everything else in KL1 is a pattern layered on top of that.

---

## Appendix C: KL1 programs not yet ported (the backlog)

Eleven programs are now ported to `examples/` (see §6): `not`, `factorial`, `sieve` (from
`primes_sieve`), `bank_account`, `qsort`, `hanoi`, `deriv`, `pascal`, `kkqueen`, `qlay`, and
`merge`.
This appendix analyses the rest — **✓ ported**, **○ feasible** with the current primitives (not yet
written), or **✗ blocked** by a missing feature (summarised in §C.4).

### C.1 KLIC distribution examples (`kl1c/examples/`)

Standalone `.kl1` programs shipped with KLIC (`fact` → `examples/factorial.py`):

| Program | What it computes | Status |
| --- | --- | --- |
| `qsort` | quicksort of a fixed list | ✓ `examples/qsort.py` |
| `hanoi` | Towers of Hanoi | ✓ `examples/hanoi.py` |
| `deriv` | symbolic differentiation | ✓ `examples/deriv.py` (functors) |
| `pascal` | Pascal's triangle | ✓ `examples/pascal.py` |
| `primes` | basic Sieve of Eratosthenes | ○ same as `sieve.py` |
| `primesp` | the sieve with priorities | ○ = `sieve.py`; the `@lower_priority` hint is unsupported |
| `pp` | nested-list generator (benchmark) | ○ feasible (list processing) |
| `kkqueen` | N-Queens (counts solutions) | ✓ `examples/kkqueen.py` (difference-list solutions — no `merge`) |
| `qlay` | N-Queens via layered streams | ✓ `examples/qlay.py` |
| `puzzle` | a combinatorial puzzle | ○ feasible (search) |
| `mastermind` | Mastermind solver | ○ feasible (rewritable without `otherwise`) |
| `wave` | a cellular "wave" simulation | ○ feasible (grid of relations) |
| `life` | Conway's Game of Life | ○ feasible (grid of cell-relations; substantial) |
| `prio` | priority demo | ✗ needs `@priority` scheduling |
| `turtles` | a tiling puzzle | ✗ needs `otherwise` (ordered default clause) |
| `merge` | the `merge` builtin demo | ✓ `examples/merge.py` (nested mergers stand in for the input vector) |
| `atomfunc` | atom & functor builtins | ✗ needs atom builtins (`make_atom`, `intern`, …) |
| `vecstr` | vector & string builtins | ✗ needs aggregate types (vectors `{..}`, strings) |
| `cmac` | a macro-declaration demo | ✗ needs `with` / macro directives (compile-time substitution) |
| `iotest` | reads its own source file | ✗ needs the I/O layer (file streams) |
| `parsetest` | a parser test | ○ feasible for a token list; char parsing would want string builtins |
| `client` / `server` | socket echo | ✗ needs the I/O layer (sockets) |

### C.2 Book transcriptions (`kl1c/agent-oriented-programming/`)

`not`, `primes_sieve`, `bank_account` — and the difference-list quicksort — are covered:

- **ch03 `qsort`** / **ch04 `qsort_dl`** — ✓ `examples/qsort.py`. Both book versions are the
  same difference-list accumulator technique (O(1) concatenation by threading the open
  "hole", no `append`).

### C.3 Program fragments in the book (Huntbach & Ringwood)

GDC snippets in the text (see §8), never shipped as `.kl1` files — the richest backlog. By
chapter:

- **Ch. 4 (streams / synchronization):** eager vs. lazy producers; bounded / N-slot buffer
  (difference list); user-defined **fair merge** and **self-balancing (splay) merge**;
  **readers/writers** with short-circuit termination; the **dining philosophers**; the
  Brock–Ackerman feedback example.
- **Ch. 5 (actors & agents):** **haggling** (Winograd–Flores); **Contract Net**;
  Byzantine / consensus; auction / poker; **neural networks** with back-communication
  (back-prop); **Conway's Life** in GDC; Shoham-style `agent0`; the resource-bounded `demo`
  meta-interpreter.
- **Ch. 6 (concurrent search):** the OR→AND search skeleton with combiners
  (`choose` / `append` / `merge` / `lowestcost`); parallel **branch-and-bound**; parallel
  **α-β**; speculative-parallelism control.
- **Ch. 7 (distributed constraint solving):** actor-per-vertex all-pairs **shortest path**;
  **graph colouring** (back-communication + integer "social laws"); **minimal spanning tree**
  (dynamic topology, first-class channels passed in messages).
- **Ch. 8 (meta-interpretation):** the "vanilla" `reduce` / `behavior` meta-interpreter (plus
  tracer, priority scheduler, explicit wake-lists); a GDC-hosted **Linda tuple-space**;
  lazy / eager **λ-calculus** (channels as futures).
- **Ch. 9 (partial evaluation):** the GDC partial evaluator (Futamura projections);
  **actor fusion / deforestation** (e.g. `append_length`).
- **Ch. 10 (agents & robots):** the subsumption **robot** FSM (`robot0..robot9`);
  agents-as-objects (`xyobj`, access classes, express / priority messages); **mobile agents**
  (migrate by packaging themselves as a message).

### C.4 Missing features (the blockers)

The `✗` rows above, and much of §C.3, reduce to a handful of gaps (cf. §7):

- **`@priority` / `otherwise` / `after(N)`** — scheduling and control annotations (`prio`,
  `turtles`, and the biased-merge / dining-philosophers fragments).
- **An I/O layer** — KL1 file / socket streams (`unix:` / `klicio`); the examples currently
  drive I/O from Python instead (`iotest`, `client`, `server`).
- **Aggregate & atom builtins** — vectors `{..}`, strings-as-objects, `make_atom` / `intern`
  (`vecstr`, `atomfunc`).
- **`with` / macro directives** — compile-time constant substitution (`cmac`).

Functors (needed by `deriv`, the object pattern, and much of §C.3) are already available
(`struct` / `unstruct`), and so now is **merge** (`merge` / `merge_streams`), which unblocks the
shared-server and all-solutions fragments and the Ch. 6 search combiners; difference lists and
streams need no new features. So the plan from here — the largest *unblocked* next steps — is
**`puzzle`** (concurrent search), the **`wave`** / **`life`** cellular grids, and the §C.3
fragments that merge unblocks (the shared-server agents of Ch. 5, the Ch. 6 search skeleton).
