# Multi-stage build for production deployment
#
# Default: API server (uvicorn)
# Override CMD for other modes:
#   docker build -t plotlot .
#   docker run plotlot                              # API (default)
#   docker run plotlot plotlot-ingest --all          # Ingestion
#   docker run plotlot prefect worker start ...      # Prefect worker

# ── Stage 1: Install dependencies with uv ──
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and install project
COPY src/ src/
RUN uv sync --frozen --no-dev


# ── Stage 2: Runtime (API server by default) ──
FROM python:3.13-slim

WORKDIR /app

# Copy venv AND source from builder (uv editable install needs src/)
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Put venv on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "uvicorn plotlot.api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
