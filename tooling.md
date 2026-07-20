# Development tooling

The tooling scaffold for python-kl1: linting, type checking, tests organized by kind,
and security, all wired up from the first commit — so "it's clean" is the default
rather than something someone has to remember to run by hand. The scaffold mirrors
[`localenv-python`](https://github.com/CesarBallardini/localenv-python).

## What's in here

* **[uv](https://docs.astral.sh/uv/)** for dependency and environment management, with separate groups (`dev` vs `deploy`).
* **[ruff](https://docs.astral.sh/ruff/)** as linter and formatter (`ruff.toml`).
* **[pyright](https://microsoft.github.io/pyright/)** + **[pyrefly](https://pyrefly.org/)** as a pair of type checkers, run on purpose, not mid-migration (`pyrightconfig.json`, `pyrefly.toml`).
* **[import-linter](https://import-linter.readthedocs.io/)** to enforce the architectural layers (`[tool.importlinter]` in `pyproject.toml`; see the README appendix) — higher layers may import lower ones, never the reverse.
* **[bandit](https://bandit.readthedocs.io/)** (SAST) with a baseline, and **[pip-audit](https://pypi.org/project/pip-audit/)** + **[OSV-Scanner](https://google.github.io/osv-scanner/)** (SCA) against `uv.lock` for security (`bandit.yaml`). OSV-Scanner is a standalone Go binary, not a PyPI package, so it doesn't go through `uv` — locally it just needs to be on `PATH` (`choco install osv-scanner` on Windows), in CI it runs via Google's official reusable workflow (see `security.yml`).
* **[pytest](https://docs.pytest.org/)** for the test suite (`tests/unit/`).
* **[pre-commit](https://pre-commit.com/)** hooking lint, format, and lockfile checks before every commit.
* A `Makefile` as the single interface — nobody needs to memorize the exact command for each tool.
* Three independent GitHub Actions workflows in `.github/workflows/`, one per concern: `check.yml` (lint + format + types), `pytest.yml` (runs the test suite **and** every example script), `security.yml` (bandit + pip-audit + OSV-Scanner).

## Prerequisites

* [uv](https://docs.astral.sh/uv/) (verified with the latest stable release)
* Python 3.14 (uv installs it automatically if missing, per `.python-version`)
* Git
* [OSV-Scanner](https://google.github.io/osv-scanner/) on `PATH` (only needed for `make security`; on Windows, `choco install osv-scanner`)

## Using the tooling

Install dependencies and the pre-commit hooks:

```bash
make install
```

From there, everything goes through the Makefile:

```bash
make                  # no target: lists all available targets
make lint             # ruff check + ruff format --check
make format           # ruff format + ruff check --fix
make types            # pyright + pyrefly
make test             # pytest (the unit suite)
make examples         # run every example script as a smoke test
make security         # bandit + pip-audit --skip-editable + osv-scanner
make precommit        # run all pre-commit hooks by hand
```

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

This leaves `dist/python_kl1-0.1.0-py3-none-any.whl` and the matching sdist. The
`py.typed` marker in `src/python_kl1/` travels inside the wheel, so consumers inherit
the type hints instead of the type checker treating the package as untyped.
