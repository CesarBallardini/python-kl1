# Plan: advance python-kl1 — phased, step by step

**Written:** 2026-10-29, from the reading of `python-kl1-general.md` (§7 "Still open", the §8
"ship these idioms first" checklist, Appendix C.4), reviewed against the code.

**Decisions taken on 2026-10-29** (they shape Phases 1–3 and are not reopened below):

1. Order: GC → `@otherwise` → deadlock reporting → fidelity → `@priority` → book-fragment ports.
2. `@otherwise` is a decorator that *replaces* `@clause` on a default clause.
3. All four hand-rendered examples (`qlay`, `puzzle`, `wave`, `mastermind`) are converted to it.
4. Deadlock reporting: an eager call raises; sessions opt in with `engine.run(check=True)`;
   `engine.blocked` lists the goals; plain `run()` stays quiet.
5. Phases 7–11 make process management pluggable. The cooperative `Engine` becomes the first
   plugin and stays the default and the reference. asyncio, threads, greenlets and
   multiprocessing are added after the ports as further plugins, all registered and selected
   the same way.

**Starting state.** `feat/merge-primitive` is pushed with two commits — `1d3d9aa feat: add
merge…` and `04db774 feat: port life, mastermind, puzzle, wave and pp…` (the latter also carries
the `uv.lock` bump). Untracked: the project guide and this plan. Sixteen examples; every KLIC
example the current primitives allow is ported.

Every phase below has the same shape — *Preconditions → Steps (do / check) → Verification →
Acceptance → Docs → Handover* — and starts from `main` on its own branch, with its own plan-mode
spec before the first edit. "Gate chain" means `make qa` (ruff, pyright, pyrefly,
import-linter, pytest with the 90 % coverage floor, every example, stopping at the first
failure) and the attribution grep from the global guide (its pattern is not repeated here, so
this file passes it once tracked).

---

## Phase 0 — land what exists, tidy the design notes

**Branch:** `docs/design-notes-tidy` · **commit:** `docs: tidy the design notes after the KLIC ports`

| # | Do | Check |
| --- | --- | --- |
| 0.1 | Open the PR for `feat/merge-primitive`. Title (two `feat` commits, so GitHub's default would be wrong): `feat: add the merge primitive and port the remaining KLIC examples`. Body: the two commit bodies. | CI green on all three workflows; squash-merge; delete the branch. |
| 0.2 | Keep the project guide untracked: append its file name to `.git/info/exclude` (clone-local, never committed). Decide whether this plan is tracked (recommended: yes, in this PR). | `git status` shows only what you intend. |
| 0.3 | `python-kl1-general.md` §5.1: replace "see the README architecture appendix" with a pointer to §5.4 and the README's *Layout* section. Header goal (l. 4): "write multi-threaded programs in the *KL1 style*" → "write concurrent programs in the *KL1 style*", since the library runs many lightweight processes on one cooperative engine (§5.3), not OS threads. | Link targets exist; no remaining line presents threads as the substrate. |
| 0.4 | §7: split "Still open" into *Decided in §5.3, worth revisiting* (scheduler, guard safety, unification, value layer) and *Open*. | No bullet lost. |
| 0.5 | §6 `wave.py` bullet and §8 checklist (l. 703): short-circuit termination is demonstrated by `wave`'s `done` token; tick (1)–(3) and (6). | — |
| 0.6 | Header: `Date: 2026-07-19` → "Started 2026-07-19 · last revised 2026-10-29". | — |

**Verification:** attribution grep. **Acceptance:** no factual claim changes. **Handover:** branch,
commit, push, PR titled as the commit.

---

## Phase 1 — keep the cyclic GC off the engine's live frontier

**Branch:** `perf/engine-gc` · **commit:** `perf: keep the cyclic GC off the engine's live frontier`
**Where:** `src/python_kl1/core/engine.py` — `Engine.run()` (l. 71) loops `step()`; `drain()` in
`core/stream.py` (l. 178) pumps `step()` itself, so anything that must also cover lazy consumption
has to be usable from there. Object model: `core/terms.py` (`Cons`, `Struct`), `core/logicvar.py`
(`Var`), the waiter closures in `Engine.when_bound` and `goal.retry_when_any_bound`.
**Known:** `mastermind go(3, 3)` 98 s → 17 s and `go(2, 3)` 4.0 s → 1.6 s with
`gc.freeze()` + `gc.disable()` applied from a script.

| # | Do | Check |
| --- | --- | --- |
| 1.1 | Baseline script in the scratchpad: wall time, `tracemalloc` peak and the number of collections (`gc.callbacks`) for `mastermind go(2, 3)` / `go(3, 3)`, `life(30, 20, 20)` / `(120, 38, 38)`, `puzzle go()`, `pp(12)`. | Table recorded in *Review*. |
| 1.2 | Profile the tracked population at `mastermind go(2, 3)`'s peak: `len(gc.get_objects())` and a `Counter` of type names. | Tells whether the structural variant (1.6) can pay. |
| 1.3 | Variant A — raise `gc.set_threshold` inside a private `_gc_relief()` context manager used by `run()`; save and restore. Python 3.14's incremental collector changes what the thresholds mean: measure, do not assume. | Timing + peak vs baseline. |
| 1.4 | Variant B — `gc.freeze()` on entering `run()`, `gc.unfreeze()` on leaving. | Same. |
| 1.5 | Variant C — `gc.disable()` for the duration of `run()`, `gc.enable()` + `gc.collect()` in `finally`, a depth counter for nested runs, `gc.isenabled()` honoured so a caller's own setting is restored. **Never around `drain`**: its consumer loop may be the user's long-running program. | Same, with peak memory watched. |
| 1.6 | Variant D — `slots=True` on the `Cons`/`Struct` dataclasses, `__slots__` on `Var`; re-run 1.2. | Object count and time. |
| 1.7 | Choose: the simplest variant giving ≥ 3× on `go(3, 3)` with peak memory ≤ 2× baseline and no semantic change; combine with D if D is cheap. Implement in `run()`; extend to `drain` only if the chosen variant is memory-bounded (A, B, D). No public knob unless a test needs one. | — |
| 1.8 | Tests in `tests/unit/test_engine.py`: GC flags and thresholds identical before and after `run()`, also when a goal raises; a result-equality test on a cyclic structure. | Green. |
| 1.9 | Gate chain; examples loop re-timed. | `examples/mastermind.py` < 30 s here. |

**Docs:** §7 GC bullet → a §5.3 note ("Scheduler and the cyclic GC", with the numbers);
`tooling.md` examples-loop sentence re-timed. **Acceptance:** 1.9 plus unchanged results (860,
711, 65). **Risk:** 3.14's incremental GC; mitigated by measuring every variant.

---

## Phase 2 — `@otherwise`, the ordered default clause; port `turtles`; convert four examples

**Branch:** `feat/otherwise-clause` · **commit:** `feat: add @otherwise, the ordered default clause, and port turtles`
**Where:** `src/python_kl1/dsl.py` — `_ClauseMethod` (l. 423, `__slots__ = ('fn',)`), `clause`
(l. 433), `Relation.__init_subclass__` (l. 466: unwraps the marker, collects
`cls._clause_methods`) and `__init__` (l. 476: `partial(method, self)`), `call().reduce()`
(l. 511–527: accumulates `waiting`, `retry_when_any_bound` at the end); `src/python_kl1/core/goal.py`
— `Predicate.clause` (l. 97) and the reducer in `call()` (l. 110–122) for raw-layer parity.

**Semantics (fixed):** the reducer tries clauses in order, accumulating `waiting`. On reaching an
`@otherwise` clause with `waiting` non-empty it stops and suspends the goal on `waiting`; with
`waiting` empty — every clause above *failed* — it tries the clause like any other. Consecutive
defaults each wait for everything above them (differs from KL1's `otherwise. c1. c2.` only when
`c1` suspends; documented). `NoMatchingClauseError` unchanged.

| # | Do | Check |
| --- | --- | --- |
| 2.1 | `dsl.py`: `_ClauseMethod.__slots__ = ('fn', 'otherwise')`; `clause()` builds it with `False`; new `otherwise(method)` decorator builds it with `True`; docstrings; add to `__all__` and the module docstring's vocabulary bullet. | `pyright` clean. |
| 2.2 | `Relation.__init_subclass__`: collect a slotted `_ClauseSpec(fn, otherwise)` per clause into `_clause_methods`; `__init__`: `_clauses` carries the flag beside the bound callable. | Existing tests green. |
| 2.3 | `call().reduce()`: before trying a clause, `if spec.otherwise and waiting: break`; the existing tail then suspends on `waiting`. | — |
| 2.4 | `core/goal.py`: `Predicate.clause(fn, *, otherwise=False)` keeps the flag beside the clause; the same rule in its reducer; `__repr__` unchanged. | `tests/unit/test_goal.py` case. |
| 2.5 | Tests in `tests/unit/test_dsl.py`: (a) a default does not commit while an earlier clause is suspended on an unbound input, and the right clause commits once it binds; (b) with every earlier clause failing on bound input the default commits at once; (c) two consecutive defaults; (d) `NoMatchingClauseError` when nothing matches and nothing waits; (e) the trap as a regression: a guard-free fallback commits early, `@otherwise` does not. | Green; each test < 0.1 s. |
| 2.6 | Port `turtles.kl1` → `examples/turtles.py` (fork, role-first brief). Facts from the original: `go(4, A)` — **N = 4** solutions, `A` their list; three `otherwise.` sites — `filter` (after the same-card skip clause), `send`, `flip`; `send`'s default reads `T`, the output of a concurrently running `filter`, so a guard-free fallback *would* commit early — this is the case `@otherwise` exists for; **`N-T` in `rearrange1` is the functor `-(N, T)`, build it with `struct('-', n, t)`, never `n - t`**; the atom `begin` seeds the layered stream (`guard(x == 'begin')`); guard unifications `card(J,_,_,_,_) = C` are `unstruct(c, 'card', 5)` + `guard(j2 == j)`; the solutions are 9-element lists of `-(N, T)` structs, cross-check with a brute-force Python packer; test budget ≲ 5 s, else a reduced constraint set with its own reference. | `go()` count 4; solution shape asserted. |
| 2.7 | Convert, each faithful to its `.kl1`, running `pytest -k <name>` after each file: `qlay.py` (`Filter.keep` l. 59, `LastFilter.keep` l. 110 → `@otherwise`); `puzzle.py` (`Match.no_fit`, `DirectPiece.no_fit`, `Play.skip`); `wave.py` (`Go.refuse`); `mastermind.py` (`Loop.deeper` keeps its own guards and becomes `@otherwise`, `Loop.exhausted` drops its guards; `Check` → one `@otherwise` fallback; `Exact.miss`, `Delete.skip`, `GenGuess.more` drop the negated guards; `Inexact` regains its directive — `done` and `step` become defaults). Module docstrings: the "rendered by hand" paragraphs go. | 92, 65, 144 × 3, 860 unchanged. |
| 2.8 | Re-time `mastermind` and `puzzle` (fewer guard evaluations expected). | Not slower. |
| 2.9 | Docs: §2.2, §4 table (`otherwise` ✓), §5.2 bullet, §6 bullets (qlay/puzzle/mastermind/wave rewritten, `turtles` added), §7 (rule-of-thumb bullet → resolved), Appendix C intro "Seventeen", C.1 `turtles` ✓, C.4 blockers (drop `otherwise`); `tutorial.md` §9 (replace the trap bullet with "a guard-free fallback is *not* an otherwise — use `@otherwise`") and §7 table; `README.md` concepts line; the project guide's semantics bullet and public-API list. | Attribution grep. |
| 2.10 | Gate chain; examples loop. | — |

**Acceptance:** 2.6, 2.7, 2.8 and the five new tests. **Handover:** branch, commit, PR titled as
the commit; body = the semantics paragraph plus the conversion list.

---

## Phase 3 — report blocked goals at quiescence

**Branch:** `feat/deadlock-report` · **commit:** `feat: report blocked goals at quiescence`
**Where:** `core/engine.py` (`Engine.__slots__ = ('_queue',)`, `run`, `when_bound`),
`core/goal.py` `retry_when_any_bound` (l. 145 — the single place every suspension goes through),
`dsl.py` `call()` (supplies the description) and `Relation.__call__` (l. 481, the eager path).

**Design (fixed by decision 4):** `Engine` keeps a registry of blocked goals — a slotted
`Blocked(describe, variables)`; `retry_when_any_bound` registers on suspend and its `wake()`
unregisters. `Engine.blocked` → tuple of descriptions (relation name + `deref`'d args, capped).
`Engine.run(*, check: bool = False)` raises `DeadlockError(blocked)` after quiescence when `check`
is set and goals remain blocked. The eager call raises `DeadlockError` when its answer is unbound
at quiescence **and** goals are blocked; unbound with nothing blocked (the program simply never
bound its output) keeps returning the `Var`, documented. `session()` and `__exit__` unchanged.

| # | Do | Check |
| --- | --- | --- |
| 3.1 | `engine.py`: `Blocked`, `DeadlockError`, `_blocked` registry (identity-keyed), `block()` / `unblock()`, the `blocked` property with lazy, capped descriptions. | Unit tests. |
| 3.2 | `goal.py`: `retry_when_any_bound(engine, variables, retry, describe)`; raw `call()` passes `predicate.name` + args; `bind_from` passes a `:=` description. | `test_goal.py`. |
| 3.3 | `dsl.py` `call()`: `describe` = relation name + `deref`'d, capped args. | Description names the relation. |
| 3.4 | `run(check=True)`; eager-path raise in `Relation.__call__`. | `test_dsl.py`. |
| 3.5 | Performance budget: `mastermind go(2, 3)` before/after; accept ≤ 5 % slower, else cheaper records. | Numbers in *Review*. |
| 3.6 | Tests: `test_engine.py` (registry fills on suspend, empties on wake, `check=True` raises, plain `run()` quiet); `test_dsl.py` (eager raise with a goal that waits forever; the sieve and merge tests still quiet; message text); `examples/life.py` — delete `life_count`'s `TypeError` guard, now redundant. | Green. |
| 3.7 | Docs: `tutorial.md` §9 deadlock bullet rewritten around `engine.blocked` / `check=True`, §4 eager-call note; §5.1 engine bullet; §8's `<R,B,I>` implication marked done; `README.md` concepts; the project guide's API list (`DeadlockError`). | — |

**Acceptance:** 3.5 and 3.6. **Handover** as usual.

---

## Phase 4 — fidelity, two small branches

**4a** · `fix/unify-int-float` · `fix: keep ints and floats distinct in unify`
`core/logicvar.py:103` `if a == b:` → `if type(a) is type(b) and a == b:` (atoms only reach that
line; `bool` becomes its own type, so `True` no longer unifies with `1`, nor `1` with `1.0`).
Arithmetic guards (`Term.__eq__` → `_compare`) keep Python numeric semantics — KL1's `=:=`.
Tests in `test_logicvar.py` for both sides; grep the examples for float literals (none expected);
§7 bullet retired, §5.3 note.

**4b** · `feat/type-guards` · `feat: add wait and the type guards to the DSL`
In `dsl.py`, after `unstruct`, on the `empty`/`unstruct` template (`_resolve`; `Var` →
`_ClauseSuspend([value])`; mismatch → `_ClauseFail`): `wait(term)` (suspend until bound, then
pass), `is_integer`, `is_float`, `is_atom` (a `str`), `is_list` (`Cons` or `NIL`) — the `is_`
prefix keeps `float`/`list` unshadowed. `__all__`, module docstring. Then `wave.py`:
`Show.step` `empty(sync)` → `wait(sync)`, `CheckList.one` `guard(v >= 0)` → `is_integer(v)`.
Tests in `test_dsl.py`; docs: §4 table (`wait` ✓), §5.2 bullet, §6 `wave` bullet, `tutorial.md`
§7 guard table, the project guide's API list.

---

## Phase 5 — goal priorities

**Branch:** `feat/priority` · **commit:** `feat: add goal priorities to the engine and the DSL`

| # | Do | Check |
| --- | --- | --- |
| 5.1 | Pre-study (Appendix A says it is unmined): `kl1c/biblio/KLIC.info.txt` on `@priority(N)`, `@lower_priority`, the default priority and range, inheritance by spawned goals, `alternatively`; the Chikayama 1996 PDF on scheduling. Write the findings into §3.5 first — they fix the semantics below and `prio`'s expected output. | §3.5 updated before any code. |
| 5.2 | Engine: `spawn(goal, priority=0)`; a heap keyed `(-priority, sequence)`, FIFO within a band; `step()` pops the highest; `when_bound` continuations keep the *suspended* goal's priority; keep the `deque` fast path until the first non-default priority is seen. | `mastermind go(2, 3)` ≤ 10 % slower. |
| 5.3 | DSL: `with priority(n):` and `with lower_priority():` context managers around spawns in a body — a priority stack consulted by `call()`; spawned goals inherit (the book's inheritance by parameter); `self(...)` unchanged. | `test_dsl.py` scoping tests. |
| 5.4 | Tests: `test_engine.py` (ordering across bands, FIFO within), the Ch. 6 livelock scenario (a "found" announcer at higher priority stops expansion). | Green. |
| 5.5 | Ports: `examples/prio.py` — `p([N|T]) :- print(N)@priority(N)` over 0..9 filled in order; expected order per 5.1. `examples/primesp.py` — `sieve.py` with `lower_priority()` around the generator; **168 primes ≤ 1000**, and the generator's lead (produced-but-unconsumed) measured by a probe is bounded where the plain FIFO lets it run ahead. | Both asserted in `test_examples.py`. |
| 5.6 | Docs: §3.5, §5.1–5.3, §7, C.1 rows (`prio`, `primesp` ✓), C.4 blockers; `tutorial.md` new subsection; the project guide. | — |

---

## Phase 6 — the book fragments (one plan and one role-first fork per port)

Each port: read its chapter in `kl1c/biblio/…Huntbach.md`; a brute-force Python reference where
the book gives no number; test ≲ 5 s; tick its C.3 line and the §8 checklist; `tutorial.md` §10
list and `README.md` layout line.

| # | Port | Needs | Files |
| --- | --- | --- | --- |
| 6a | Ch. 6 OR→AND search skeleton — one problem, combiners `append`, `merge`, `choose`, `lowestcost` | `choose` needs Phase 5 (cut-off without livelock); do `append`/`merge`/`lowestcost` first if 5 is not in | `examples/search.py` |
| 6b | Ch. 4 — N-slot bounded buffer (difference list), readers/writers with short-circuit termination, dining philosophers (the book's symmetry break), the user-defined fair/biased merge; add `merge_streams(..., biased=True)` / `merge(..., biased=True)` here with tests and a §3.3 paragraph | — | `buffer.py`, `readers_writers.py`, `philosophers.py` |
| 6c | Ch. 5 — Contract Net (and haggling) over `merge` | — | `contract_net.py` |
| 6d | Ch. 7 — actor-per-vertex all-pairs shortest path; graph colouring with back-communication and "social laws" | — | `shortest_path.py`, `colouring.py` |

Commit subjects: `feat: port <fragment> from Huntbach & Ringwood`.

---

## Phases 7–11 — engine plugins: cooperative, asyncio, threads, greenlets, multiprocessing

§5.3 chose a single-threaded cooperative engine and §7 still lists "threads vs. asyncio vs.
greenlets" as open. These phases answer it by making process management a **plugin**: every
substrate, the existing cooperative one included, implements one `Scheduler` protocol, is
registered under a name with its declared capabilities, and is selected per session. Each one
is then measured against the reference engine rather than argued about.

| Plugin | Module | Phase | Dependency | Brings |
| --- | --- | --- | --- | --- |
| `cooperative` | `python_kl1.core.engine:Engine` (unchanged) | 7 | none | the reference: deterministic FIFO |
| `asyncio` | `python_kl1.engines.aio` | 8 | none (stdlib) | goals inside an asyncio program, real I/O |
| `threads` | `python_kl1.engines.threads` | 9 | none (stdlib) | multi-core on the free-threaded build |
| `greenlet` | `python_kl1.engines.greenlets` | 10 | `greenlet`, an optional extra | mid-clause suspension |
| `multiprocessing` | `python_kl1.engines.processes` | 11 | none (stdlib) | multi-core on the default build, KLIC's `@node` placement |

**What every substrate must preserve.** Single assignment is what makes this tractable: a bound
`Var` never changes, so a guard that read a value is never invalidated, and a guard that saw an
unbound input suspends and retries. Two invariants need care on a real multi-worker engine:
(a) **no lost wake-up** — `when_bound` checks then parks (`core/engine.py:45`), and `_resolve`
sets `ref` then swaps the waiter list (`core/logicvar.py:108`), so a waiter parked between the
two is never fired; (b) **no silent overwrite** — two goals binding the same `Var` to different
values must produce exactly one `UnificationError`. Which goal raises may vary between runs;
that is accepted and documented. Results of determinate programs must equal the reference
engine's; programs whose output order depends on scheduling (fair merge) are compared as
multisets.

**Order:** 7 (the plugin seam) → 8 (asyncio: stdlib, deterministic, lowest risk) → 9 (threads:
multi-core on `3.14t`) → 10 (greenlets: a third-party dependency, landed only if it earns it)
→ 11 (multiprocessing: the largest, a distributed variable store). Phase 7 waits for Phases 1,
3 and 5, because the GC policy, the blocked-goal registry and priorities are engine features
every plugin must provide or declare it lacks.

### Phase 7 — engine plugins: the protocol, the registry, the conformance suite

**Branch:** `refactor/engine-plugins` · **commit:** `refactor: make the engine a plugin and add a conformance suite`
**Where:** `core/engine.py`; a new package `src/python_kl1/engines/` (the registry; later
phases add plugin modules to it); `dsl.py` `_ENGINE_STACK` (l. 308, a module-global list —
shared across threads and asyncio tasks), `session()` (l. 533, which hard-codes `Engine()`) and
the eager path in `Relation.__call__` (l. 481); `core/stream.py` and `core/goal.py` (callers of
`spawn` / `when_bound` / `step`); `pyproject.toml` `[tool.importlinter]`; `tests/unit/conftest.py`.

**Plugin contract (fixed here, used by Phases 8–11):**

- A plugin is an `EnginePlugin(name, factory, capabilities, missing)` record: `factory` returns
  a `Scheduler`; `missing` is `None` or the install hint when an optional dependency is absent.
- `Capabilities` declares `fifo_order: bool` (reproduces the reference order), `priorities`
  (`'exact'`, `'best_effort'` or `'none'`), `parallel: bool` and `placement: bool` (accepts
  `node(k)`, Phase 11). Tests and docs read these instead of checking plugin names.
- Built-in plugins are listed in a static table in `engines/__init__.py` as lazy import paths,
  so they work without reinstalling. Third-party plugins register through the entry-point group
  `python_kl1.engines`; a name that collides with a built-in is an error.
- The cooperative engine stays where it is (`python_kl1.core.engine:Engine`) and registers as
  `cooperative`, so `from python_kl1.core import Engine` keeps working.
- Selection, in order: an instance passed to `session(engine=…)`, a name passed there, the
  `PYTHON_KL1_ENGINE` environment variable, then `cooperative`. Options go through an
  instance, for example `session(engine=ThreadEngine(workers=4))`.

| # | Do | Check |
| --- | --- | --- |
| 7.1 | `core/engine.py`: a `Scheduler` `Protocol` with exactly what callers use — `spawn`, `when_bound`, `step`, `run(check=…)`, `blocked`, the context manager; `Engine` implements it. `goal`, `stream` and `dsl` annotate against `Scheduler`. | `pyright`, `pyrefly` clean; no behaviour change. |
| 7.2 | `engines/__init__.py`: `EnginePlugin`, `Capabilities`, `available()`, `load(name)`, `default()`; the built-in table with `cooperative`; entry-point discovery with `importlib.metadata.entry_points(group='python_kl1.engines')`. Listing never imports a plugin; an unavailable plugin is listed with its hint, and `load` raises with it. | `tests/unit/test_engines.py`: list, load, unknown name, unavailable hint, env-var default, a third-party plugin via a patched `entry_points`. |
| 7.3 | `dsl.py`: `_ENGINE_STACK` → a `ContextVar[tuple[Scheduler, ...]]`, so each thread and each asyncio task sees its own current engine. `session(engine: str | Scheduler | None = None)`; the eager path takes its engine from `default()`. | Existing tests green; reducer timing on `mastermind go(2, 3)` within noise. |
| 7.4 | Order audit: classify every test whose expected output depends on FIFO order; mark them `@pytest.mark.needs('fifo_order')` and give each a multiset twin that runs everywhere. | List recorded in *Review*. |
| 7.5 | `conftest.py`: `--engine=<name>` (default `cooperative`) sets the default plugin for the run; tests that create `Engine()` directly go through a fixture; `needs(...)` markers skip a test when the plugin lacks the capability. CI: a matrix over the built-in plugins in `pytest.yml`, one row now, one more per phase. | `pytest --engine=cooperative` == today's run. |
| 7.6 | import-linter: a new layer `python_kl1.engines` between `dsl` and `core.goal | core.stream | core.engine`; plugins may import `core.*`, `core` never imports `engines`. | `lint-imports` clean. |
| 7.7 | `tutorial.md` section "Writing an engine plugin": the protocol, the capabilities, the entry-point snippet for `pyproject.toml`, running the suite with `--engine=<yours>`. | Snippet tested by 7.2's third-party case. |

**Docs:** §5.1 engine bullet (plugins), §5.3 substrate note ("the default, not the only one"),
`tooling.md` (`--engine`, `PYTHON_KL1_ENGINE`, the CI matrix), `README.md` concepts, the project
guide's layer diagram and API list (`python_kl1.engines`). **Acceptance:** the suite is
unchanged on `cooperative`, and a dummy third-party plugin registered in a test runs through
the whole selection path.

### Phase 8 — the `asyncio` plugin

**Branch:** `feat/asyncio-engine` · **commit:** `feat: add the asyncio engine plugin`
**Purpose:** run KL1 goals inside an asyncio program and let them exchange data with real I/O.
The tutorial today says the library is not for I/O multiplexing (`tutorial.md:412–415`); this
phase changes that claim, not the semantics. Stdlib only, no new dependency.

| # | Do | Check |
| --- | --- | --- |
| 8.1 | `engines/aio.py`: `AsyncioEngine` keeps the reference engine's deque (same FIFO order, so the suite stays deterministic) and adds `async def arun()`, which runs goals in slices of K and `await asyncio.sleep(0)` between slices. Sync `step()` / `run()` still work outside a loop. Registered as `asyncio` with `fifo_order=True`, `priorities='exact'`. | Conformance suite with `--engine=asyncio`, order-dependent tests included; CI matrix row added. |
| 8.2 | Bridges: `await wait_bound(term)` (an `asyncio.Future` resolved by a parked waiter) and `async for x in adrain(engine, stream)`; both in `engines/aio.py`. | Unit tests. |
| 8.3 | Feeding a stream from a coroutine: `feed(engine, queue)` turns an `asyncio.Queue` into a KL1 stream, closing it on a sentinel. | A producer with `asyncio.sleep` delays, a summing relation as consumer; the result matches the synchronous sum. |
| 8.4 | Fairness to the loop: a ticker coroutine keeps ticking while `mastermind go(2, 3)` runs under `arun()`; choose K from the measured trade-off. | Max gap between ticks ≤ 50 ms; `go(2, 3)` ≤ 10 % slower than the reference. |
| 8.5 | Demonstration in `tutorial.md` (a new section), not in `examples/`, which stays reserved for ports of the originals. | — |

**Docs:** `tutorial.md` new section and the I/O bullet at l. 414; §5.3; §7 bullet (asyncio part
answered); `README.md` concepts; the project guide's API list. **Acceptance:** 8.1–8.4.

### Phase 9 — the `threads` plugin, for free-threaded Python

**Branch:** `feat/thread-engine` · **commit:** `feat: add the threaded engine plugin for free-threaded Python`
**Purpose:** use more than one core inside one process. It only pays on the free-threaded
build (`3.14t`); on the default build it must stay correct but will be slower. Phase 11 is the
multi-core answer for the default build.

| # | Do | Check |
| --- | --- | --- |
| 9.1 | Preconditions, checked before any code (as for the 3.15 attempt): `uv python install 3.14t` on Windows; pytest and pytest-xdist run on it; import-linter's `grimp` and other compiled dev tools may lack `cp314t` wheels, so `lint-imports` and the type checkers stay on the default build. | A one-line verdict in *Review*; stop and report if pytest cannot run on `3.14t`. |
| 9.2 | Race audit of `core/logicvar.py` and `core/engine.py`: `_resolve` (l. 108), the Var–Var link in `unify` (l. 81–86), `when_bound` (l. 45). Write a stress test for each invariant first — N threads binding one `Var`, N threads parking on it while one binds — and watch it fail. | Failing tests in hand. |
| 9.3 | Fix with the simplest lock that works: one binding lock held by `_resolve`, the Var–Var link and `when_bound`'s check-and-park; waiters fired outside the lock. Measure the uncontended cost on the reference engine; keep it unconditional if ≤ 5 % on `mastermind go(2, 3)`, else switch it on only when a threaded engine exists. Striped locks only if 9.6 shows contention. | 9.2 tests green 1 000× in a loop. |
| 9.4 | `engines/threads.py`: `ThreadEngine(workers=N)` — a shared run-queue, an outstanding-goal counter (queued + running) for quiescence, workers that set the engine `ContextVar` from Phase 7, the first worker exception re-raised by `run()` after the others stop; `step()` runs one goal on the calling thread, so `drain` keeps working. Registered as `threads` with `fifo_order=False`, `priorities='best_effort'`, `parallel=True`. | Conformance suite with `--engine=threads` on both builds; order-dependent tests skipped by capability; CI matrix row added. |
| 9.5 | Priorities (Phase 5) per worker as a best-effort order, documented as such; the blocked-goal registry (Phase 3) under the same lock; the GC policy (Phase 1) stays process-wide. | Unit tests for each. |
| 9.6 | Measure on `3.14t` with 1, 2, 4 and 8 workers: `puzzle go()`, `kkqueen` 8, `mastermind go(2, 3)`, `life(30, 20, 20)`, against the reference engine. Goals are microseconds long, so a single shared queue may dominate; if it does, try per-worker deques with work stealing. | Table in *Review*. |
| 9.7 | **Decision gate:** land as a supported engine only if some example reaches ≥ 1.5× at 4 workers. Otherwise stop and report the numbers; landing it as experimental or dropping the branch is your call. | — |
| 9.8 | CI: a `pytest-ft` job in `pytest.yml` on `3.14t`, unit tests only, with `--engine=threads`. | Green on push. |

**Docs:** §5.3 and §7 (threads answered, with the table); `tutorial.md` "CPU-bound speedup"
bullet (l. 412) rewritten from the numbers; `tooling.md` (the `3.14t` job); `README.md`; the
project guide. **Acceptance:** 9.4 on both builds, 9.6 recorded, 9.7 decided.

### Phase 10 — the `greenlet` plugin, optional

**Branch:** `feat/greenlet-engine` · **commit:** `feat: add the optional greenlet engine plugin`
**Purpose:** test the one thing greenlets offer that the others do not — a goal that suspends
*mid-clause* and resumes where it stopped, instead of retrying the whole clause from scratch.
**Conflict to resolve first:** `greenlet` is a compiled third-party package, and the library
promises no runtime dependencies. The plan keeps that promise: greenlet is an optional extra
(`python-kl1[greenlet]`), imported only by `engines/greenlets.py`. Without the extra, the
registry still lists `greenlet`, as unavailable, with the install hint.

| # | Do | Check |
| --- | --- | --- |
| 10.1 | Preconditions: a `greenlet` release with `cp314` `win_amd64` wheels, and whether it supports `3.14t`; `pip-audit` and `osv-scanner` clean on it. | Verdict in *Review*; stop if no wheel. |
| 10.2 | `[project.optional-dependencies] greenlet = [...]` in `pyproject.toml`; `uv lock`; the plugin's `missing` hint set when the import fails. | `uv lock --check`; `test_engines.py` case with greenlet absent. |
| 10.3 | `GreenletEngine`: one greenlet per goal; a guard that meets an unbound input switches back to the scheduler and parks the greenlet on the variable; binding resumes it at the same point. Committed choice is unchanged: a resumed guard re-reads its inputs, and commit still happens once. Registered as `greenlet` with `fifo_order=True`, `priorities='exact'`. | Conformance suite with `--engine=greenlet`, order-dependent tests included; CI matrix row installs the extra. |
| 10.4 | Measure against the reference: per-goal cost, memory per suspended goal at scale (`qlay` 8, `sieve` to 10 000 — the §7 worry about heavy goals applies here), and guard work saved on `mastermind go(2, 3)`, where goals suspend late in long clauses. | Table in *Review*. |
| 10.5 | **Decision gate:** keep it if it is faster on some example or makes a Phase 6 fragment simpler to write; otherwise record the numbers in §5.3 and drop the branch unmerged. | — |

**Docs (if kept):** §5.3, §7 (the open question closed), `tutorial.md`, `tooling.md` (the
extra), `README.md`, the project guide.

### Phase 11 — the `multiprocessing` plugin, with node placement

**Branch:** `feat/process-engine` · **commit:** `feat: add the multiprocessing engine plugin with node placement`
**Purpose:** multi-core on the default build, where the GIL rules out Phase 9's speedup. Stdlib
only. It is KLIC's own distributed model: its `@node(N)` pragma places a goal on a processor.

**Design constraint.** A goal costs microseconds and a pickle round-trip across processes costs
far more, so goals cannot be scattered one by one. Each node runs a local cooperative engine,
and the program places *coarse* goals with `with node(k):`, mirroring Phase 5's
`with priority(n):`. Unplaced goals stay on the node that spawned them, so a program with no
placement behaves exactly like `cooperative` on node 0. Two consequences shape the steps:

- **Goals cross as data, not closures.** A placed goal travels as the relation's importable
  qualified name plus its arguments. Relations must be module-level, which Windows' `spawn`
  start method requires anyway, together with the `if __name__ == '__main__':` guard every
  example already has.
- **Variables crossing a node boundary become references.** A `Var` is owned by the node that
  created it and travels as `RemoteRef(node, id)`. Binding asks the owner, which decides once,
  since single assignment makes the owner the single point of truth, then broadcasts the value
  to subscribed nodes or returns `UnificationError` to the requester.

| # | Do | Check |
| --- | --- | --- |
| 11.1 | Pre-study: the Chikayama 1996 PDF and `KLIC.info.txt` on distributed KLIC — `@node`, export and import tables, reference counting of exported variables, termination detection. Write the findings into §3 first; they may replace parts of the design below. | §3 updated before any code. |
| 11.2 | Wire format: picklable `Atom`, numbers, `Cons`, `Struct`, `NIL`; `Var` ↔ `RemoteRef`; relations resolved by qualified name on arrival. | Round-trip tests for every term kind. |
| 11.3 | `engines/processes.py`: `ProcessEngine(nodes=N)` — node 0 is the calling process, nodes 1…N−1 are worker processes, each with a cooperative engine and one duplex pipe; message kinds `spawn`, `bind`, `subscribe`, `value`, `error`, `idle`. | A placed goal runs on its node and its result reaches node 0. |
| 11.4 | Cross-node unification: binds go to the owner; a Var–Var link between nodes points at the lower `(node, id)` to avoid cycles; waiters on a remote variable are a subscription plus local waiters. | Stress test: conflicting binds from three nodes yield exactly one `UnificationError`. |
| 11.5 | Distributed quiescence: all nodes idle and no message in flight, detected by counting sent and received messages in the idle reports over two consistent rounds. The blocked-goal registry (Phase 3) is gathered from every node; worker exceptions are forwarded and re-raised by `run()`; worker processes always shut down, also on error. | Unit tests for each; no orphan process after a failing test. |
| 11.6 | DSL: `with node(k):` placement context, valid only on a plugin with `placement=True`, an error elsewhere. Registered as `multiprocessing` with `fifo_order=False`, `priorities='best_effort'` (per node), `parallel=True`, `placement=True`. | `test_dsl.py` scoping tests. |
| 11.7 | Conformance suite with `--engine=multiprocessing`: unplaced programs must pass everything that does not need `fifo_order`. | CI matrix row added. |
| 11.8 | Measure with 1, 2 and 4 nodes, start-up cost reported apart: `kkqueen` 8 with one placed subtree per first-column choice, `puzzle go()` per first piece, `mastermind go(3, 3)` per guess subtree. | Table in *Review*. |
| 11.9 | **Decision gate:** land as supported only if some example reaches ≥ 2× at 4 nodes, start-up included. Otherwise stop and report; experimental or dropped is your call. | — |

**Docs:** §3 (distributed KLIC findings), §5.3, §7, `tutorial.md` section on placement,
`README.md`, `tooling.md` (the Windows `spawn` notes), the project guide's API list (`node`).
**Acceptance:** 11.7, 11.8 recorded, 11.9 decided.

---

## Deferred on purpose

Relation inheritance (document as intended — the book's inheritance anomaly); `after(N)` (needs
a clock; revisit with priority); the I/O layer, aggregates/strings, `cmac` (outside the
library's purpose).
## Working agreements

- Plan mode per phase; the spec names files, steps, verification, acceptance before the first edit.
- Tooling through `uv run --frozen …`; the gate chain before "done".
- Forks: role first, one writable file, no shared-file edits, report instead of integrate.
- No repository-mutating git; exact commands handed over; branch per phase; PR title = commit
  subject; no attribution anywhere.
- Test budget ≲ 5 s per new test; `main()` keeps each original's full size.

## Review

(Per phase: what landed, deviations from this plan, the numbers, lessons.)

**Phase 0 (2026-10-29).** 0.1: PR #1 squash-merged under the proposed title. 0.2: the project
guide is excluded clone-locally; this plan is tracked from this PR on. Not in the plan: the
tooling was aligned with `localenv-python` in between (PR #2: `make qa`, coverage floor,
gitleaks, link check, commitizen, hardened CI); its link check found a dead `kl1c` link in
Appendix A, which is why 0.3–0.6 waited for it. 0.3–0.6 landed as written, plus the same dead
"README appendix" pointer in `tooling.md`. The §8 checklist marks (2) fair-merge only: nothing
implements a biased merge yet (it needs Phase 5).
