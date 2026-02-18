# Multi-stage, multi-target build for production deployment
# Targets: api, ingest, worker
#
# Build examples:
#   docker build --target api -t plotlot-api .
#   docker build --target ingest -t plotlot-ingest .
#   docker build --target worker -t plotlot-worker .

# ── Stage 1: Install dependencies with uv ──
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra prefect --no-install-project

# Copy source and install project
COPY src/ src/
RUN uv sync --frozen --no-dev --extra prefect


# ── Stage 2: Shared runtime base ──
FROM python:3.13-slim AS runtime

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Put venv on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Non-root user
RUN useradd --create-home appuser
USER appuser


# ── Target: API server ──
FROM runtime AS api
EXPOSE 8000
CMD ["uvicorn", "plotlot.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]


# ── Target: One-shot ingestion ──
FROM runtime AS ingest
CMD ["plotlot-ingest", "--all"]


# ── Target: Prefect worker ──
FROM runtime AS worker
CMD ["prefect", "worker", "start", "--pool", "plotlot-pool", "--type", "process"]
