# PlotLot v2 — Claude Code Instructions

## Persona

See `.claude/prompts/` for full persona definition. TL;DR: Distinguished ML/LLMOps Engineer, production-first, direct, ships working code with tests and observability.

## Project Overview

PlotLot v2 is an AI-powered zoning analysis platform for South Florida real estate. The core flow:
1. User enters a property address (Miami-Dade, Broward, Palm Beach — 104 municipalities)
2. System geocodes → retrieves property data from county ArcGIS APIs → fetches zoning ordinances from Municode
3. Agentic LLM extracts numeric dimensional standards (density, setbacks, FAR, height, lot coverage)
4. Deterministic calculator computes max allowable dwelling units with 4-constraint breakdown
5. Frontend streams results via SSE with progressive disclosure

**Business metric:** Serves 104 municipalities across 3 South Florida counties.

**Why it matters for the portfolio:**
- RAG pipeline with hybrid search (not just naive vector similarity)
- Agentic LLM with structured tool calling (not just chat completion)
- Deterministic calculator validates LLM output (constrain, don't trust)
- Multi-provider fallback with circuit breakers (production resilience)
- Real data from government APIs (not synthetic/toy data)

## Multi-Model Routing (Claude Code Router)

For development, use `ccr code` instead of `claude` to enable multi-model routing between Claude and Gemini:

```bash
ccr code  # Launches Claude Code with routing
```

**Routing config** (`~/.claude-code-router/config.json`):
| Task Type | Model | Rationale |
|-----------|-------|-----------|
| `default` (code gen) | Claude Opus 4.6 | Most intelligent Claude model, best for agents + coding |
| `background` (scanning) | Gemini 3 Flash | Frontier-class performance at fraction of cost |
| `think` (reasoning) | Gemini 3.1 Pro | Advanced intelligence, complex problem-solving |
| `longContext` (large files) | Gemini 3.1 Pro | Extended context window |
| `webSearch` | Gemini 3.1 Pro | Built-in web grounding |

**Available models (as of 2026-03-11):**
- Anthropic: `claude-opus-4-6` (20250826), `claude-sonnet-4-6` (20250827), `claude-sonnet-4-5` (20250929), `claude-haiku-4-5` (20251001)
- Google (preview): `gemini-3.1-pro-preview`, `gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`
- Google (stable): `gemini-2.5-pro`, `gemini-2.5-flash`
- Deprecated (do not use): `claude-3-7-sonnet`, `claude-3-5-sonnet`, `gemini-1.5-*`

Switch models mid-session: `/model gemini,gemini-3.1-pro-preview` or `/model anthropic,claude-opus-4-6`

**API doc lookups:** Use `chub` (Context Hub by Andrew Ng) for token-efficient doc retrieval:
```bash
chub search anthropic        # Find available docs
chub get anthropic/claude-api --lang py  # Fetch Python SDK docs
chub get gemini/genai --lang py          # Fetch Gemini SDK docs
```

## Architecture & Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| **Backend** | FastAPI + Python 3.12+ | Async-first, Pydantic models everywhere |
| **Database** | Neon PostgreSQL + pgvector | Hybrid search (RRF fusion), 8,142 chunks across 5 municipalities |
| **Frontend** | Next.js 16 + React 19 + Tailwind CSS 4 | Vercel deployment, SSE streaming |
| **LLM** | Claude Sonnet 4.6 (primary) | Fallback: Gemini 2.5 Flash → NVIDIA Llama 3.3 70B → Kimi K2.5. Per-model circuit breakers |
| **Embeddings** | NVIDIA NIM (1024d) | Used for chunk embedding at ingestion time |
| **Observability** | MLflow tracing → Neon PostgreSQL | Persistent across deploys |
| **CI/CD** | GitHub Actions | ruff + mypy + pytest + eval suite |
| **Geocoding** | Geocodio API | Address → county/municipality identification |
| **Property Data** | County ArcGIS REST APIs | MDC (two-layer zoning), Broward parcels, Palm Beach spatial |
| **Zoning Docs** | Municode API | 73 municipalities with auto-discovery |

## Project Structure

```
plotlot/
├── src/plotlot/
│   ├── api/                  # FastAPI application
│   │   ├── main.py           # App factory, startup/shutdown
│   │   ├── routes.py         # /analyze SSE endpoint, /chat, /admin
│   │   ├── schemas.py        # Pydantic request/response models
│   │   ├── cache.py          # Response caching layer
│   │   ├── chat.py           # Agentic chat with 10 tools
│   │   ├── geometry.py       # Shapely geometry operations
│   │   └── middleware.py     # CORS, error handling, request logging
│   ├── pipeline/
│   │   ├── calculator.py     # Deterministic density calculator (4-constraint)
│   │   ├── lookup.py         # Property lookup orchestration
│   │   ├── ingest.py         # Municipality ingestion pipeline
│   │   └── eval_flow.py      # Evaluation pipeline runner
│   ├── retrieval/
│   │   ├── llm.py            # LLM client (NVIDIA NIM, Kimi K2.5 fallback)
│   │   ├── search.py         # pgvector hybrid search (RRF fusion)
│   │   ├── geocode.py        # Geocodio API client
│   │   ├── property.py       # County ArcGIS property lookup
│   │   └── bulk_search.py    # Batch search operations
│   ├── core/
│   │   ├── types.py          # NumericZoningParams, DensityAnalysis, enums
│   │   └── errors.py         # Custom exception hierarchy
│   ├── config.py             # Pydantic Settings (env-based config)
│   ├── observability/        # MLflow tracing, prompts
│   ├── ingestion/            # Municode scraper, chunker, embedder
│   ├── documents/            # PDF proforma generation
│   ├── storage/              # Database models, migrations
│   └── cli.py                # CLI entry points
├── frontend/
│   ├── src/app/              # Next.js app router (page.tsx, layout.tsx)
│   ├── src/components/       # React components (14 components)
│   │   ├── AnalysisStream.tsx    # Main SSE streaming UI
│   │   ├── ZoningReport.tsx      # Full zoning report card
│   │   ├── DensityBreakdown.tsx  # 4-constraint visual breakdown
│   │   ├── SatelliteMap.tsx      # Google Maps satellite view
│   │   ├── EnvelopeViewer.tsx    # 3D buildable envelope
│   │   ├── FloorPlanViewer.tsx   # Generated floor plans
│   │   └── PropertyCard.tsx      # Property summary card
│   └── src/lib/
│       ├── api.ts            # Backend API client + SSE parser
│       └── floorplan-generator.ts
├── tests/
│   ├── unit/                 # Unit tests (pytest)
│   ├── eval/                 # LLM evaluation suite (10 golden cases)
│   ├── integration/          # Integration tests
│   └── conftest.py           # Shared fixtures
├── pyproject.toml            # Python deps, scripts, tool config
└── .env.example              # Required environment variables
```

## API Endpoints

### Analysis Pipeline
- `POST /analyze` — SSE streaming endpoint. Accepts `{"address": "..."}`. Streams events: `geocode`, `property`, `zoning`, `analysis`, `calculator`, `heartbeat`, `error`, `done`.
- `GET /health` — Health check. Returns `{"status": "ok"}`.

### Chat
- `POST /chat` — Agentic chat endpoint. Accepts `{"message": "...", "session_id": "..."}`. Uses 10 tools for property research.
- Tools available: geocode, lookup_property_info, search_zoning_ordinance, web_search, property_search, filter, dataset_info, export, spreadsheet, document_creation.

### Admin
- `POST /admin/ingest` — Ingest single municipality. Background task.
- `POST /admin/ingest/batch` — Batch ingest multiple municipalities.
- `GET /admin/ingest/batch/status` — Check batch ingestion status.

### Debug
- `GET /debug/llm` — LLM diagnostics (model status, circuit breaker state).
- `GET /debug/traces` — Recent MLflow traces.

## Quick Commands

```bash
# Backend dev server (from plotlot/)
uv run uvicorn plotlot.api.main:app --reload --port 8000

# Frontend dev server (from plotlot/frontend/)
npm run dev

# Run unit tests
cd plotlot && uv run pytest tests/unit/ -v

# Run eval suite (requires live API keys)
cd plotlot && uv run pytest tests/eval/ -v

# Run all tests with coverage
cd plotlot && uv run pytest tests/ --cov=src/plotlot --cov-report=term-missing

# Lint + format check
cd plotlot && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/

# Type check
cd plotlot && uv run mypy src/plotlot/

# Ingest a municipality
cd plotlot && uv run plotlot-ingest --municipality "City Name"

# Search zoning chunks
cd plotlot && uv run plotlot-search --municipality "Miami Gardens" --query "residential density" --limit 5

# Run single eval test
cd plotlot && uv run pytest tests/eval/test_eval_experiment.py -v -k "miami_gardens"

# Check database chunk counts
cd plotlot && uv run python -c "from plotlot.storage.db import get_chunk_counts; print(get_chunk_counts())"
```

## Coding Standards

### Python (Backend)
- Python 3.12+, type hints on all function signatures
- Pydantic `BaseModel` for all data structures, `BaseSettings` for config
- Async-first: use `httpx.AsyncClient` (not requests), `asyncpg` (not psycopg2)
- No `print()` in library code — use `structlog` or `logging`
- Ruff for linting and formatting (configured in pyproject.toml)
- All API endpoints return Pydantic models, never raw dicts

### TypeScript (Frontend)
- Next.js App Router (not Pages Router)
- React 19 with server components where possible
- Tailwind CSS 4 for styling — no CSS modules, no styled-components
- Explicit TypeScript interfaces for all API response shapes
- Components in `src/components/`, utilities in `src/lib/`

## Testing

- **Unit tests:** `tests/unit/` — mock external services (ArcGIS, Geocodio, LLM)
- **Eval tests:** `tests/eval/` — 10 golden cases (5 positive, 3 boundary, 1 partial, 1 data quality)
- **Integration tests:** `tests/integration/` — end-to-end with real (or staged) APIs
- **Every production failure becomes a regression test case** (the Ramp pattern)
- Eval suite uses `pytest` markers: `@pytest.mark.eval`, `@pytest.mark.live`
- `asyncio_mode = "auto"` in pyproject.toml — no need for `@pytest.mark.asyncio`
- CI runs: ruff lint + format → mypy → pytest unit → pytest eval

### Eval Test Structure
Each eval case in `tests/eval/test_eval_experiment.py` defines:
- `address` — the input property address
- `expected_municipality` — ground truth municipality name
- `expected_zoning` — expected zoning code (e.g., "RS-1", "RM-25")
- `density_range` — acceptable range for max dwelling units
- `required_fields` — fields that must be non-null in `NumericZoningParams`

### Test Fixtures (`tests/conftest.py`)
- `mock_geocode_response` — fake Geocodio API response
- `mock_property_response` — fake ArcGIS property data
- `mock_llm_response` — fake LLM extraction with `NumericZoningParams`
- `sample_zoning_chunks` — pre-embedded zoning text chunks

## Common Errors Claude Makes

1. **Forgetting async:** All I/O functions must be `async`. Don't use `requests` — use `httpx.AsyncClient`.
2. **Missing Pydantic field defaults:** `NumericZoningParams` fields are `Optional[float] = None`. Don't make them required.
3. **Wrong import paths:** Package is `plotlot`, not `src.plotlot`. Imports: `from plotlot.core.types import ...`
4. **SSE format:** Backend SSE uses `data: {json}\n\n` format. Frontend parses with `EventSource` pattern in `api.ts`.
5. **Calculator assumptions:** The density calculator uses 4 constraints (density, min_lot_area, FAR, buildable_envelope). All are optional — handle `None` gracefully.
6. **ArcGIS API quirks:** MDC has two-layer zoning (land use + zoning overlay). Broward and Palm Beach use single-layer. Don't assume uniform schema.
7. **Render timeout:** Render free tier has 30s proxy timeout. Long operations need SSE heartbeat or background tasks.
8. **mypy strictness:** 28 known type errors (CI uses `|| true`). Don't introduce new ones. Goal: fix and make hard gate.

## Environment Variables

| Variable | Required | Used By | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | Backend | Neon PostgreSQL connection string (includes pgvector) |
| `NVIDIA_API_KEY` | Yes | Backend | NVIDIA NIM API for LLM + embeddings |
| `GEOCODIO_API_KEY` | Yes | Backend | Geocodio geocoding service |
| `GOOGLE_MAPS_API_KEY` | Yes | Frontend | Google Maps satellite view + Places autocomplete |
| `SENTRY_DSN` | No | Both | Sentry error tracking |
| `MLFLOW_TRACKING_URI` | No | Backend | Auto-derived from `DATABASE_URL` if not set |
| `KIMI_API_KEY` | No | Backend | Kimi K2.5 fallback LLM (optional) |
| `NEXT_PUBLIC_API_URL` | Yes | Frontend | Backend API URL for client-side requests |

Copy `.env.example` to `.env` and fill in values. Never commit `.env` files.

## Deployment

| Service | Platform | URL Pattern |
|---------|----------|-------------|
| Backend API | Render (free tier, Docker) | `plotlot-api.onrender.com` |
| Frontend | Vercel (free tier) | `plotlot.vercel.app` |
| Database | Neon (free tier) | PostgreSQL connection string in `DATABASE_URL` |
| MLflow | Neon PostgreSQL backend | Auto-derived from `DATABASE_URL` |

**Deploy checklist:**
1. Backend: push to `main` → Render auto-deploys from Dockerfile
2. Frontend: push to `main` → Vercel auto-deploys
3. Database migrations: `uv run alembic upgrade head` (run before deploy if schema changed)
4. Verify health: `curl https://plotlot-api.onrender.com/health`

### Render-Specific Concerns
- Free tier has 30s proxy timeout — all long operations need SSE heartbeat or background tasks
- Cold start can take 30-60s. First request after idle may timeout.
- Docker build uses `plotlot/Dockerfile`. Build context is `plotlot/`.
- Health check endpoint: `/health`

### Vercel-Specific Concerns
- `next.config.ts` configures API rewrites to avoid CORS issues in production
- Environment variables set in Vercel dashboard (not committed)
- Serverless function timeout: 10s on free tier

## Pipeline Deep Dive

The analysis pipeline runs as a sequence of steps, each streamed to the frontend via SSE:

1. **Geocode** (`retrieval/geocode.py`) — Geocodio API → lat/lng, county, municipality, FIPS code
2. **Property Lookup** (`pipeline/lookup.py` + `retrieval/property.py`) — Routes to correct county ArcGIS API:
   - MDC: two-layer query (land use layer + zoning overlay layer)
   - Broward: parcel layer with zoning field
   - Palm Beach: spatial zoning query with geometry
3. **Zoning Search** (`retrieval/search.py`) — pgvector hybrid search (RRF fusion of cosine similarity + BM25), limit=15 chunks
4. **LLM Extraction** (`retrieval/llm.py`) — Agentic LLM with tool calling extracts `NumericZoningParams`:
   - `max_density_units_per_acre` — e.g., 25.0 for RM-25
   - `min_lot_area_sqft` — minimum lot size per unit
   - `max_far` — floor area ratio
   - `max_lot_coverage_pct` — maximum lot coverage percentage
   - `max_height_ft` — maximum building height
   - `setback_front_ft`, `setback_side_ft`, `setback_rear_ft` — setback requirements
5. **Calculator** (`pipeline/calculator.py`) — Deterministic computation:
   - Applies 4 constraints: density, min_lot_area, FAR, buildable_envelope
   - Each constraint produces a max-units figure
   - Final result = `min(all constraints)` — the binding constraint
   - Returns `DensityAnalysis` with per-constraint breakdown

## Data Model Reference

### `NumericZoningParams` (core/types.py)
All fields are `Optional[float] = None`. The LLM extracts what it can find; the calculator handles `None` gracefully.

Key fields: `max_density_units_per_acre`, `min_lot_area_sqft`, `max_far`, `max_lot_coverage_pct`, `max_height_ft`, `setback_front_ft`, `setback_side_ft`, `setback_rear_ft`, `min_unit_size_sqft`, `max_stories`

### `DensityAnalysis` (core/types.py)
Result of the calculator. Contains:
- `max_units` — final answer (integer)
- `binding_constraint` — which of the 4 constraints limited the result
- `constraint_results` — dict of each constraint's individual max-units figure
- `buildable_area_sqft` — lot area minus setbacks
- `parameters` — the `NumericZoningParams` used

### `PropertyInfo` (core/types.py)
Property data from ArcGIS: `address`, `lot_area_sqft`, `zoning_code`, `land_use`, `county`, `municipality`, `folio_number`, `geometry`

## Ingestion Pipeline

The ingestion pipeline (`pipeline/ingest.py`) processes a municipality's zoning ordinances:

1. **Discovery** — Query Municode API to find the municipality's code library
2. **Scrape** — Download all zoning-related sections (Title/Chapter filtering)
3. **Chunk** — Split into ~500-token chunks with overlap, preserving section headers
4. **Embed** — NVIDIA NIM embeddings (1024d vectors)
5. **Store** — Upsert into pgvector with metadata (municipality, section, chapter)

Currently ingested municipalities and chunk counts:
| Municipality | Chunks | Notes |
|-------------|--------|-------|
| Miami Gardens | 3,561 | Most complete coverage |
| Miami-Dade County | 2,666 | Unincorporated MDC |
| Boca Raton | 1,538 | Palm Beach County |
| Miramar | 241 | Broward County |
| Fort Lauderdale | 136 | Broward County |

88 municipalities are discoverable on Municode. West Palm Beach uses enCodePlus (not supported yet).

## Chat System

The agentic chat (`api/chat.py`) provides conversational property research:

- **10 tools** available per turn, dynamically masked based on conversation state
- **3-step workflow:** geocode → lookup_property_info → search_zoning_ordinance
- **Session memory:** LRU cache, 100 sessions max, 1hr TTL per session
- **Token budget:** 50K tokens per session to prevent runaway costs
- **Geocode cache:** Session-level lat/lng cache for consistent coordinate precision

## Performance & Cost

- **LLM costs:** NVIDIA NIM Llama 3.3 70B is the primary model. Circuit breaker trips after 3 failures in 5 minutes, falls back to Kimi K2.5.
- **Embedding costs:** NVIDIA NIM embeddings at ingestion time only. No per-query embedding cost (queries are embedded at search time).
- **Database:** Neon free tier (0.5 GB storage, 190 compute hours/month). Currently at ~8,142 chunks.
- **Caching:** Response cache in `api/cache.py` prevents duplicate pipeline runs for same address.
- **Retry strategy:** Exponential backoff on network-bound steps (scrape, embed, ArcGIS). Max 3 retries.

## Current State (as of 2026-03-11)

### What's Built
- Full agentic pipeline: geocode → property lookup → zoning search → LLM extraction → calculator
- Agentic chat with 10 tools, session memory (LRU, 100 sessions, 1hr TTL)
- SSE streaming with heartbeat for Render timeout
- Municode auto-discovery (88 municipalities), scraper, chunker, NVIDIA embedder
- pgvector hybrid search (RRF fusion, limit=15)
- Multi-county property lookup (MDC two-layer, Broward, Palm Beach)
- Admin ingestion endpoints (single + batch)
- MLflow tracing to Neon PostgreSQL
- Per-model circuit breakers, token budget (50K cap), dynamic tool masking
- PDF proforma generation, satellite map, 3D envelope viewer, floor plans
- CI/CD: GitHub Actions (lint + type-check + test + eval)
- UI polish: collapsible sections, setback diagram, property intelligence card, copy-to-clipboard

### Known Issues
1. **Data coverage:** 5 municipalities ingested (Miami Gardens, MDC, Boca Raton, Miramar, Fort Lauderdale). 88 discoverable.
2. **Render cold start:** Free tier sometimes returns `x-render-routing: no-server`. May need keep-warm.
3. **mypy:** 28 type errors with `|| true` in CI. Needs cleanup.
4. **West Palm Beach:** Moved to enCodePlus (not on Municode). Needs alternate scraper.
5. **Frontend tests:** Playwright tests exist but are not yet integrated into CI.

## Key File Paths

| File | Purpose |
|------|---------|
| `src/plotlot/api/routes.py` | All API endpoints (/analyze, /chat, /admin) |
| `src/plotlot/api/schemas.py` | Request/response Pydantic models |
| `src/plotlot/pipeline/calculator.py` | Deterministic density calculator |
| `src/plotlot/pipeline/lookup.py` | Property lookup orchestration |
| `src/plotlot/retrieval/llm.py` | LLM client with fallback chain |
| `src/plotlot/retrieval/search.py` | pgvector hybrid search |
| `src/plotlot/retrieval/property.py` | County ArcGIS API clients |
| `src/plotlot/core/types.py` | Core data models (NumericZoningParams, DensityAnalysis) |
| `src/plotlot/config.py` | Environment config (Pydantic Settings) |
| `frontend/src/app/page.tsx` | Main frontend page |
| `frontend/src/components/AnalysisStream.tsx` | SSE streaming UI |
| `frontend/src/lib/api.ts` | Backend API client |
| `tests/eval/test_eval_experiment.py` | Main eval test suite |

## Development Workflow

### Starting a Session
1. Launch with multi-model routing: `ccr code`
2. Rules auto-load based on files you touch (`.claude/rules/`)
3. Memory persists across sessions in `~/.claude/projects/.../memory/`

### Slash Commands
- `/dev` — Start backend + frontend dev servers
- `/test` — Run lint + type check + unit tests + eval
- `/deploy` — Deploy to Render + Vercel with pre-flight checks
- `/ingest <municipality>` — Ingest zoning ordinances into vector DB

### Quality Gates (Automatic via Hooks)
- **Python files** auto-linted with ruff after every edit
- **TypeScript files** auto-linted with next lint after every edit
- **Stop hook** runs ruff check + unit tests before Claude finishes
- **Sensitive files** (.env, credentials, lock files) blocked from edits

### API Doc Lookups
Use `chub` (not Context7) for token-efficient docs:
```bash
chub search anthropic        # Find available docs
chub get anthropic/claude-api --lang py  # Fetch Python SDK docs
```

### Model Switching
```bash
/model gemini,gemini-3.1-pro-preview   # For research/thinking
/model anthropic,claude-opus-4-6       # For code generation
```

## Rules

1. **Every code change ships with tests.** No exceptions.
2. **No over-engineering.** Build what's needed now. Ship fast, iterate.
3. **Track everything in MLflow.** Every pipeline run, experiment, eval.
4. **Constraints beat capabilities.** Don't throw bigger models at problems — constrain with structured tools, circuit breakers, clear system prompts.
5. **Every production failure becomes a regression test.** The Ramp pattern.
6. **Use Claude Sonnet for email generation** as specified in global config.
7. **No `print()` in library code.** Structured logging only.
8. **Pydantic everywhere.** No raw dicts crossing function boundaries.
9. **Async-first for I/O.** `httpx`, `asyncpg`, `async def` — no blocking calls in async contexts.
10. **SSE heartbeat for long operations.** Render's 30s proxy timeout is real.
11. **CLI-first tooling.** Always prefer CLIs over manual steps or web dashboards — `vercel`, `gh`, `uv`, `npx`, etc. CLIs are scriptable, reproducible, and auditable. Example: `vercel env ls` over checking the Vercel dashboard.
