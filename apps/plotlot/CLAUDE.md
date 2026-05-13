# PlotLot v2 — Claude Code Instructions

## Persona

See `.claude/prompts/` for full persona definition. TL;DR: Distinguished ML/LLMOps Engineer, production-first, direct, ships working code with tests and observability.

## Project Overview

PlotLot v2 is an AI-powered land deal intelligence platform. Core flow:
1. User enters a property address (any US county via ArcGIS Hub discovery)
2. System geocodes → retrieves property data → fetches zoning ordinances
3. Agentic LLM extracts numeric dimensional standards
4. Deterministic calculator computes max allowable dwelling units
5. Comparable sales analysis estimates land value
6. Pro forma calculates max offer price
7. Frontend streams results via SSE with progressive disclosure

## Architecture & Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI + Python 3.12+ (async-first, Pydantic everywhere) |
| **Database** | Neon PostgreSQL + pgvector (hybrid search, RRF fusion) |
| **Frontend** | Next.js 16 + React 19 + Tailwind CSS 4 (Vercel) |
| **LLM** | Groq → NVIDIA NIM → OpenAI/Codex OAuth → OpenRouter fallback |
| **Embeddings** | NVIDIA NIM (1024d) |
| **Observability** | MLflow tracing → Neon PostgreSQL |
| **Property Data** | ArcGIS Hub (universal) + hardcoded county providers |
| **Zoning Docs** | Municode API (88 municipalities discoverable) |

## Project Structure

```
plotlot/
├── src/plotlot/
│   ├── api/           # FastAPI app (routes, schemas, chat, cache)
│   ├── pipeline/      # lookup, calculator, comps, proforma, contracts
│   ├── retrieval/     # llm, search, geocode, property
│   ├── property/      # Universal + county-specific ArcGIS providers
│   ├── core/          # types.py, errors.py
│   ├── config.py      # Pydantic Settings
│   ├── observability/ # MLflow tracing
│   ├── ingestion/     # Municode scraper, chunker, embedder
│   ├── documents/     # PDF/docx generation
│   └── storage/       # Database models, Firestore cache
├── frontend/
│   ├── src/app/       # Next.js App Router
│   ├── src/components/ # React components
│   └── src/lib/       # API client, utilities
└── tests/             # unit/, eval/, integration/
```

## API Endpoints

- `POST /analyze` — SSE streaming pipeline. Events: `geocode`, `property`, `zoning`, `analysis`, `calculator`, `comps`, `proforma`, `heartbeat`, `error`, `done`
- `POST /chat` — Agentic chat with 10 tools
- `GET /health` — Health check
- `POST /admin/ingest` — Municipality ingestion

## Deep Dive References

Detailed domain knowledge is in rule files (auto-loaded based on files you touch):
- **Pipeline steps & error taxonomy:** `.claude/rules/plotlot-pipeline.md`
- **Data models (PropertyRecord, NumericZoningParams, etc.):** `.claude/rules/plotlot-data-models.md`
- **Ingestion pipeline:** `.claude/rules/plotlot-ingestion.md`
- **Chat system (10 tools, dynamic masking):** `.claude/rules/plotlot-chat.md`
- **Backend conventions:** `.claude/rules/plotlot-backend.md`
- **Frontend conventions:** `.claude/rules/plotlot-frontend.md`

## Quick Commands

```bash
uv run uvicorn plotlot.api.main:app --reload --port 8000  # Backend
cd frontend && npm run dev                                  # Frontend
uv run pytest tests/unit/ -v                                # Unit tests
uv run pytest tests/eval/ -v                                # Eval suite
uv run ruff check src/ tests/                               # Lint
uv run mypy src/plotlot/                                    # Type check
uv run plotlot-ingest --municipality "City Name"            # Ingest
```

## Coding Standards

### Python
- Python 3.12+, type hints on all signatures
- Pydantic `BaseModel` for data, `BaseSettings` for config
- Async-first: `httpx.AsyncClient`, `asyncpg`, `async def`
- No `print()` — use `structlog` or `logging`
- Ruff for linting/formatting

### TypeScript
- Next.js App Router, React 19, Tailwind CSS 4
- Explicit interfaces for all API response shapes
- Components in `src/components/`, utilities in `src/lib/`

## Testing

- **Unit tests:** `tests/unit/` — mock external services
- **Eval tests:** `tests/eval/` — 10 golden cases
- **Integration tests:** `tests/integration/` — live API tests
- Every production failure → regression test (the Ramp pattern)
- `asyncio_mode = "auto"` — no need for `@pytest.mark.asyncio`

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | Neon PostgreSQL connection string |
| `GROQ_API_KEY` | Preferred | Groq OpenAI-compatible LLM API |
| `NVIDIA_API_KEY` | Fallback | NVIDIA NIM API |
| `OPENAI_API_KEY` / `OPENAI_ACCESS_TOKEN` | Fallback | OpenAI-compatible direct key or bearer token |
| `PLOTLOT_USE_CODEX_OAUTH` | Local fallback | Use saved local Codex OAuth tokens |
| `OPENROUTER_API_KEY` | Optional | OpenRouter fallback LLM provider |
| `GEOCODIO_API_KEY` | Yes | Geocodio geocoding |
| `NEXT_PUBLIC_API_URL` | Yes | Backend API URL |
| `SENTRY_DSN` | No | Sentry error tracking |

## Deployment

| Service | Platform | Auto-deploys from `main` |
|---------|----------|--------------------------|
| Backend | Render (Docker) | Yes |
| Frontend | Vercel | Yes |
| Database | Neon | N/A |

## Common Errors to Avoid

1. All I/O must be `async`. Use `httpx.AsyncClient`, not `requests`.
2. `NumericZoningParams` fields are `Optional[float] = None`. Don't make required.
3. Package is `plotlot`, not `src.plotlot`. Imports: `from plotlot.core.types import ...`
4. SSE format: `data: {json}\n\n`. Frontend uses EventSource pattern in `api.ts`.
5. MDC has two-layer zoning. Don't assume single-layer.
6. Render 30s proxy timeout — SSE heartbeat required for long operations.

## Rules

1. Every code change ships with tests. No exceptions.
2. No over-engineering. Build what's needed now.
3. Track everything in MLflow.
4. Constraints beat capabilities.
5. Every production failure → regression test.
6. Use configured non-Google LLM providers for generated content.
7. No `print()` in library code.
8. Pydantic everywhere. No raw dicts across function boundaries.
9. Async-first for I/O.
10. SSE heartbeat for long operations.
11. CLI-first tooling (`vercel`, `gh`, `uv`, `npx`).
