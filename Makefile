.DEFAULT_GOAL := help

.PHONY: help install lint format types layers test examples security precommit

help: ## Show this list of available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Sync the environment (from the committed lockfile) and install pre-commit hooks
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

examples: ## Run every example script as a smoke test
	@for example in examples/[!_]*.py; do \
		echo "=== $$example ==="; \
		uv run --frozen python "$$example"; \
	done

security: ## Run security scans (bandit SAST + pip-audit + OSV-Scanner SCA)
	uv run --frozen bandit -c bandit.yaml -r src
	uv run --frozen pip-audit --skip-editable
	osv-scanner --lockfile=./uv.lock

precommit: ## Run all pre-commit hooks against every file
	uv run --frozen pre-commit run --all-files
