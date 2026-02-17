.PHONY: install test lint fmt discover ingest db-up db-down clean

install:  ## Install all dependencies (including dev)
	uv sync --extra dev

test:  ## Run test suite
	uv run pytest tests/ -v

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
