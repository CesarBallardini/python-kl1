# Development tooling

The tooling scaffold for python-kl1: linting, type checking, tests organized by kind,
and security, all wired up from the first commit — so "it's clean" is the default
rather than something someone has to remember to run by hand. The scaffold mirrors
[`localenv-python`](https://github.com/CesarBallardini/localenv-python).

## What's in here

* **[uv](https://docs.astral.sh/uv/)** for dependency and environment management, with separate groups (`dev` vs `deploy`).
* **[ruff](https://docs.astral.sh/ruff/)** as linter and formatter (`ruff.toml`).
* **[pyright](https://microsoft.github.io/pyright/)** + **[pyrefly](https://pyrefly.org/)** as a pair of type checkers, run on purpose, not mid-migration (`pyrightconfig.json`, `pyrefly.toml`).
* **[import-linter](https://import-linter.readthedocs.io/)** to enforce the architectural layers (`[tool.importlinter]` in `pyproject.toml`; see `python-kl1-general.md` §5.4) — higher layers may import lower ones, never the reverse.
* **[bandit](https://bandit.readthedocs.io/)** (SAST) with a baseline, and **[pip-audit](https://pypi.org/project/pip-audit/)** + **[OSV-Scanner](https://google.github.io/osv-scanner/)** (SCA) against `uv.lock` for security (`bandit.yaml`). OSV-Scanner is a standalone Go binary, not a PyPI package, so it doesn't go through `uv` — locally it just needs to be on `PATH` (`choco install osv-scanner` on Windows), in CI it runs via Google's official reusable workflow (see `security.yml`).
* **[gitleaks](https://github.com/gitleaks/gitleaks)** for secret scanning, at both ends: a pre-commit hook over staged changes, and a whole-tree scan in CI and in `make secrets`. `.gitleaks.toml` keeps the tree scan off `.venv/` and the other generated directories. The hook and the CI job are pinned to the same version. Locally it needs to be on `PATH` (`choco install gitleaks` on Windows).
* **[pytest](https://docs.pytest.org/)** for the test suite (`tests/unit/`), configured in `pytest.ini`: warnings are errors, and **[pytest-timeout](https://pypi.org/project/pytest-timeout/)** fails a hung test after 300 s. Coverage is a **gate, not a report**: `.coveragerc` sets `fail_under = 90`, so `make coverage` and CI exit non-zero below it.
* **[pre-commit](https://pre-commit.com/)** hooking lint, format, lockfile, secret-scanning, Markdown link and file-hygiene checks before every commit — and CI runs *the same hooks* via `pre-commit run --all-files`, so what passes locally and what passes in CI can't drift apart. A `no-commit-to-branch` hook blocks commits to `main`.
* **[pip-licenses](https://pypi.org/project/pip-licenses/)** for license compliance: the whole toolchain gets reported, but only the *distributed* dependency closure is gated. The library has no runtime dependencies, so today the gate has nothing to check.
* **[commitizen](https://commitizen-tools.github.io/commitizen/)** for [Conventional Commits](https://www.conventionalcommits.org/), checked on the commit message locally (`commit-msg` hook) and on the PR title in CI (`validate_pr_title.yaml`) — a squash merge takes the title as the commit subject, so that is the one that lands. A `pre-push` hook (`.pre-commit-hooks/check-branch-name.sh`) checks that the branch is named `<type>/<slug>` and warns when GitHub would propose a non-conforming PR title.
* A **devcontainer** (`.devcontainer/`, `Dockerfile`) and shared editor settings (`.vscode/settings.json`), so a fresh clone gets the same toolchain without a setup ritual.
* A `Makefile` as the single interface — nobody needs to memorize the exact command for each tool.
* Independent GitHub Actions workflows in `.github/workflows/`, one per concern: `check.yml` (pre-commit + pyright + pyrefly + import-linter), `pytest.yml` (the test suite with the coverage gate, **and** every example script), `security.yml` (bandit + pip-audit + licenses + gitleaks + OSV-Scanner), `validate_pr_title.yaml`, `scorecard.yaml` ([OpenSSF Scorecard](https://scorecard.dev/)) and `release.yaml` (manual dispatch, tags the next version).
* **Supply-chain hygiene in the workflows themselves**: every action pinned to a commit SHA with a `# vX.Y.Z` comment, a default-deny `permissions: {}` at the top of each workflow with each job opting back into just what it needs, `concurrency` so a new push supersedes the run it replaced, and `timeout-minutes` on every job. The shared setup lives in two composite actions (`.github/actions/install-uv`, which pins the uv version, and `.github/actions/setup-python`).
* **[Dependabot](https://docs.github.com/code-security/dependabot)** (`.github/dependabot.yml`) for `uv`, `github-actions` and `pre-commit`, weekly and grouped into one PR per ecosystem, with a 10-day `cooldown`. Each ecosystem sets a Conventional Commits `commit-message` prefix, so Dependabot's PR titles (`chore(deps): bump …`, `ci(deps): bump …`) pass `validate-pr-title`.

## Prerequisites

* [uv](https://docs.astral.sh/uv/) (verified with the latest stable release)
* Python 3.14 (uv installs it automatically if missing, per `.python-version`)
* Git
* [OSV-Scanner](https://google.github.io/osv-scanner/) and [gitleaks](https://github.com/gitleaks/gitleaks) on `PATH` (only needed for `make security` and `make secrets`; on Windows, `choco install osv-scanner gitleaks`)

## Using the tooling

Install dependencies and the git hooks (`pre-commit`, `commit-msg` and `pre-push`):

```bash
make install
```

From there, everything goes through the Makefile:

```bash
make                  # no target: lists all available targets
make lint             # ruff check + ruff format --check
make format           # ruff format + ruff check --fix
make types            # pyright + pyrefly
make layers           # import-linter: the architectural layer contract
make test             # pytest (the unit suite)
make coverage         # pytest with coverage, failing below the 90% floor
make examples         # run every example script, stopping at the first failure
make qa               # lint, types, layers, coverage, examples -- in order, stopping at the first failure
make security         # bandit + pip-audit + osv-scanner + secrets + licenses
make secrets          # gitleaks over the working tree
make licenses         # report every license, gate the distributed ones
make release-next     # show the version the next release would get (creates no tag)
make precommit        # run all pre-commit hooks by hand
make clean            # remove build, cache and coverage artifacts
```

`make qa` is the gate to pass before pushing; `make qa security` adds the scans. The
attribution check is deliberately not a make target: its pattern would match the Makefile
itself.

`make examples` is also what CI's `pytest.yml` runs after the test suite. It takes a few
minutes rather than seconds, because `mastermind.py` (~100 s), `life.py` and `puzzle.py`
(~20 s each) run their originals at full size; the unit tests cover the same programs on
smaller instances in a few seconds.

## Updating dependencies

By default, `uv run` and `uv sync` can re-resolve and rewrite `uv.lock` on their own if
they detect `pyproject.toml` changed. For any command meant to just *run* something
(CI, onboarding, a given `make test`), pin the lockfile to exactly what's committed:

```bash
uv sync --frozen              # installs exactly what uv.lock says, resolves nothing
uv run --frozen pytest        # same idea, for any one-off command
```

The local pre-commit hook (`uv lock --check`) fails if `uv.lock` drifts out of sync
with `pyproject.toml`. To update dependencies **on purpose**:

```bash
uv lock --upgrade-package ruff   # updates just that package to the max pyproject.toml allows
uv lock --upgrade                # updates everything pyproject.toml's constraints allow
```

Both rewrite `uv.lock` — review the diff (`git diff uv.lock`) before continuing, then:

```bash
uv sync --all-groups
make lint types test security
```

## Building a wheel

The installable package is `python_kl1` (`[project] name` is `python-kl1`, the
importable package `python_kl1`; see `[tool.hatch.build.targets.wheel]` in
`pyproject.toml`, with `hatchling` as build backend):

```bash
uv build
```

This leaves `dist/python_kl1-<version>-py3-none-any.whl` and the matching sdist. The
version is not written in any tracked file: `uv-dynamic-versioning` derives it from the
newest `v*` git tag (with no tag yet, it is `0.0.0`). Releasing is tagging: the `release`
workflow (manual dispatch) asks `cz bump --get-next` for the next version from the
Conventional Commits history and pushes the tag. The
`py.typed` marker in `src/python_kl1/` travels inside the wheel, so consumers inherit
the type hints instead of the type checker treating the package as untyped.
