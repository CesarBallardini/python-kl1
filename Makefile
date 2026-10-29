.DEFAULT_GOAL := help

.PHONY: help install lint format types layers test coverage examples qa security secrets licenses \
        release-next precommit clean

help: ## Show this list of available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Sync the environment (from the committed lockfile) and install the git hooks
	uv sync --all-groups --frozen
	uv run --frozen pre-commit install

lint: ## Check formatting and lint rules without modifying files
	uv run --frozen ruff check .
	uv run --frozen ruff format --check .

format: ## Auto-fix formatting and lint issues
	uv run --frozen ruff format .
	uv run --frozen ruff check --fix .

types: ## Run both type checkers (pyright + pyrefly)
	uv run --frozen pyright
	uv run --frozen pyrefly check

layers: ## Check the architectural layers (import-linter)
	uv run --frozen lint-imports

test: ## Run the test suite
	uv run --frozen pytest

coverage: ## Run the test suite with coverage and enforce the floor from .coveragerc
	uv run --frozen pytest -n auto --cov=python_kl1 --cov-config=.coveragerc --cov-report=term-missing --cov-report=html

examples: ## Run every example script as a smoke test, stopping at the first failure
	@for example in examples/[!_]*.py; do \
		echo "=== $$example ==="; \
		uv run --frozen python "$$example" || exit 1; \
	done

qa: lint types layers coverage examples ## Run every quality gate in order, stopping at the first failure

security: ## Run every security scan (SAST + CVEs + secrets + licenses)
	uv run --frozen bandit -c bandit.yaml -r src
	uv run --frozen pip-audit --skip-editable
	osv-scanner --lockfile=./uv.lock
	$(MAKE) secrets
	$(MAKE) licenses

secrets: ## Scan the working tree for committed secrets (needs gitleaks on PATH)
	gitleaks dir . --redact --verbose -c .gitleaks.toml

licenses: ## Report dependency licenses and gate the ones that actually ship
	uv run --frozen pip-licenses --format=markdown
	@runtime=$$(uv export --frozen --no-dev --no-emit-project --no-hashes --format requirements.txt \
	   | sed -e 's/[[:space:]]*[;#].*$$//' -e 's/[=<>!~].*$$//' -e '/^$$/d' \
	   | paste -sd' ' -); \
	if [ -z "$$runtime" ]; then \
	  echo "No runtime dependencies to check; nothing is distributed yet."; \
	else \
	  echo "Checking: $$runtime"; \
	  uv run --frozen pip-licenses --packages $$runtime \
	    --fail-on="GNU General Public License (GPL);GNU General Public License v2 or later (GPLv2+);GNU General Public License v3 (GPLv3);GNU Affero General Public License v3 or later (AGPLv3+)"; \
	fi

release-next: ## Show the version the next release would get (creates no tag)
	uv run --frozen cz bump --get-next --yes

precommit: ## Run all pre-commit hooks against every file
	uv run --frozen pre-commit run --all-files

clean: ## Remove build, cache and coverage artifacts
	rm -rf dist/ build/ htmlcov/ .coverage coverage.xml \
	       .pytest_cache/ .ruff_cache/ .pyrefly_cache/ .import_linter_cache/
