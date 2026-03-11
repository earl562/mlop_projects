---
description: Rules for working on the PlotLot Python/FastAPI backend
globs: plotlot/src/**/*.py, plotlot/tests/**/*.py
---

# PlotLot Backend Rules

## Python Conventions
- Python 3.12+ required. Use modern syntax (`match`, `type` aliases, `X | Y` unions).
- Type hints on ALL function signatures. Use `from __future__ import annotations` if needed.
- Pydantic `BaseModel` for data structures, `BaseSettings` for config. Never pass raw dicts across function boundaries.
- Async-first for I/O: `httpx.AsyncClient` (not requests), `asyncpg`, `async def`.
- No `print()` in library code. Use `structlog` or `logging` with structured fields.

## FastAPI Patterns
- All endpoints return Pydantic response models. Define them in `api/schemas.py`.
- Use `Depends()` for dependency injection (database sessions, config, auth).
- SSE endpoints use `StreamingResponse` with `text/event-stream` content type.
- Include heartbeat (`data: {"type": "heartbeat"}\n\n`) every 15s for Render's 30s proxy timeout.
- Error responses use the custom exception hierarchy in `core/errors.py`.

## ArcGIS API Handling
- MDC has two-layer zoning (land use + zoning overlay). Don't assume single-layer.
- Broward and Palm Beach use different ArcGIS schemas. Check `retrieval/property.py` for adapters.
- Always use `httpx.AsyncClient` with timeout (30s default). ArcGIS APIs can be slow.
- Cache property lookups where possible (same address, same data within a session).

## LLM Client (`retrieval/llm.py`)
- Primary: NVIDIA NIM Llama 3.3 70B. Fallback: Kimi K2.5.
- Per-model circuit breakers. If primary fails 3x in 5min, switch to fallback.
- Tool calling for structured extraction (`NumericZoningParams`).
- Token budget: 50K per chat session. Track via MLflow.
- All LLM calls must be traced via MLflow (`@mlflow.trace` or context manager).

## Database
- SQLAlchemy async with `asyncpg` driver.
- pgvector for embeddings (1024d NVIDIA NIM vectors).
- Hybrid search: combine cosine similarity + BM25/full-text with RRF fusion.
- Alembic for migrations. Never modify tables directly.

## Error Handling
- Use custom exceptions from `core/errors.py`, not bare `Exception`.
- Pipeline steps should raise specific errors (e.g., `GeocodingError`, `PropertyLookupError`).
- Retry with exponential backoff for network-bound steps (scrape, embed, ArcGIS).
- Circuit breakers for external APIs that might be down.
