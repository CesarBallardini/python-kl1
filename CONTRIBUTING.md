# Contributing

Thanks for taking a look. The gates below are what keep a small concurrency
library honest: each one fails the build rather than printing a warning.

## Getting set up

```bash
git clone https://github.com/CesarBallardini/python-kl1
cd python-kl1
make install
```

`make install` syncs the environment from the committed `uv.lock` and installs
the git hooks — the `pre-commit`, `commit-msg` and `pre-push` ones. Run `make`
with no target to list everything available. [`tooling.md`](tooling.md)
describes each tool.

## The workflow

1. **Branch.** Commits to `main` are blocked by a hook on purpose; work lands
   through a pull request so the CI, coverage and security gates get a chance
   to run first. Name the branch `<type>/<slug>`, where `<type>` is the
   Conventional Commits type of the work — `feat/otherwise-clause`,
   `perf/engine-gc`. A `pre-push` hook enforces this.
2. **Commit.** Messages follow
   [Conventional Commits](https://www.conventionalcommits.org/) — `feat:`,
   `fix:`, `docs:`, `chore:`, `refactor:`, `perf:`, `test:`, `ci:`. The
   `commit-msg` hook checks this locally, and CI checks the pull request title,
   because a squash merge takes the title as the commit subject.
3. **Check locally** before pushing:

   ```bash
   make qa security
   ```

4. **Open the pull request.** Give it a Conventional Commits title — that is
   what determines the next version number.

   Set the title *deliberately*; do not accept the one GitHub proposes. When a
   branch has more than one commit, GitHub defaults the title to the humanised
   branch name (`feat/otherwise-clause` becomes `Feat/otherwise clause`),
   which drops the colon and fails `validate-pr-title`. The `pre-push` hook
   warns about this and suggests a starting point.

## What has to pass

| Gate | Command |
| --- | --- |
| Lint and format | `make lint` |
| Types (pyright + pyrefly) | `make types` |
| Architectural layers (import-linter) | `make layers` |
| Tests, with the 90% coverage floor | `make coverage` |
| Every example script | `make examples` |
| All of the above, in order | `make qa` |
| SAST, CVEs, secrets, licenses | `make security` |
| Every hook at once | `make precommit` |

CI runs the *same* pre-commit hooks you do (`pre-commit run --all-files`), so
a green local run and a green CI run cannot drift apart.

### About the coverage floor

`.coveragerc` sets `fail_under = 90`. If a change drops coverage below that,
the honest fix is a test, not a lower threshold. If you genuinely believe the
floor is wrong, say so in the pull request and change it as its own commit, so
the decision is visible in the history.

### About examples

A new example is a faithful port of a KL1 original from the
[kl1c repository](https://github.com/CesarBallardini/kl1c), and its result is
asserted in `tests/unit/test_examples.py`. The script's `main()` runs the
original at full size; the unit test uses a smaller instance when the full one
would take more than a few seconds.

## Releasing

There is no version number in a tracked file. `uv-dynamic-versioning` derives
the package version from the newest git tag, and the `release` workflow
(manual dispatch) uses `cz bump` to work out the next tag from the commit
history. Releasing is therefore just: merge, then run the workflow.

## Reporting a security issue

Please do not open a public issue — see [SECURITY.md](SECURITY.md).
