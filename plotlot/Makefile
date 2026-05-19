.PHONY: install install-local-tools auth-readiness auth-bootstrap live-agent-e2e mutation test verify-local verify-local-no-browser lint fmt discover ingest db-up db-down clean

install:  ## Install all dependencies (including dev)
	uv sync --extra dev --extra eval --extra mlflow

install-local-tools:  ## Sync backend/frontend deps and Playwright browser for local verification
	bash scripts/verify_local_success.sh --install --skip-backend --skip-frontend

auth-readiness:  ## Report which credential-backed/live test lanes are ready
	python3 scripts/check_auth_readiness.py

auth-bootstrap:  ## Bootstrap live credentials into .env via CLIs (see script --help)
	python3 scripts/bootstrap_live_auth.py --help

live-agent-e2e:  ## Start/verify backend and run served frontend live agent Playwright E2E
	bash scripts/run_live_agent_e2e.sh

mutation:  ## Run backend mutation testing (mutmut) on critical harness/tool surfaces (slow)
	uv run mutmut run
	uv run mutmut results

test:  ## Run test suite
	uv run pytest tests/ -v

verify-local:  ## Run deterministic backend + frontend local success gates
	bash scripts/verify_local_success.sh

verify-local-no-browser:  ## Local success gate without Playwright browser tests (useful in port-restricted sandboxes)
	bash scripts/verify_local_success.sh --skip-browser

lint:  ## Run ruff linter
	uv run ruff check src/ tests/

fmt:  ## Auto-format code
	uv run ruff format src/ tests/

discover:  ## Run live municipality discovery against Municode API
	uv run plotlot-ingest --discover

ingest:  ## Ingest all discovered municipalities
	uv run plotlot-ingest --all

db-up:  ## Start PostgreSQL + pgvector (Docker)
	docker compose up -d db

db-down:  ## Stop database
	docker compose down

clean:  ## Remove build artifacts
	rm -rf .venv dist build *.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
