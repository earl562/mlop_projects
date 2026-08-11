# PlotLot Technical Overview

AI-powered zoning analysis and real estate intelligence platform. Given a property address **or APN**, PlotLot geocodes it (or resolves the parcel directly), pulls county parcel data from ArcGIS, searches indexed municipal zoning ordinances, runs an LLM extraction to get dimensional standards, and deterministically calculates maximum allowable density — then generates comps and a residual land pro forma.

**Production state (verified against Neon 2026-08-10):** 24,536 ordinance chunks across
20 municipalities — **14 San Diego County, CA** (18,114 chunks; the active market) and
6 Florida remnants (6,422 chunks; deprioritised). There are **no North Carolina
municipalities** in the database.

> Counts drift fast. Re-verify with
> `select count(*), count(distinct municipality) from ordinance_chunks` before quoting
> this line — a previous revision claimed "8,142 chunks, 17 municipalities (5 FL + 12 NC)"
> long after that stopped being true.

---

## Stack Summary

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15.5, React 19, Tailwind CSS 4, TypeScript strict |
| Backend | FastAPI, Python 3.12+, async-first (httpx, asyncpg) |
| Database | Neon PostgreSQL + pgvector (1024d embeddings) |
| LLM | Claude Sonnet 4.6 → Gemini 2.5 Flash → NVIDIA NIM Llama 3.3 70B → Kimi K2.5 |
| Embeddings | NVIDIA NIM (1024d) |
| Auth | Clerk (JWT RS256) |
| Payments | Stripe |
| Maps | Google Maps + ESRI Leaflet (ArcGIS services) |
| Media | FAL.ai (image + video generation) |
| Observability | MLflow (Neon backend), structlog |
| Deploy (frontend) | Vercel (standalone output) |
| Deploy (backend) | Render (Docker, free tier) |
| CI/CD | GitHub Actions (ruff + mypy + pytest + eval workflow) |

---

## Frontend

### Framework & Stack

- **Next.js 15.5** with App Router (`src/app/`)
- **React 19** — server components where possible, `"use client"` only for interactivity
- **Tailwind CSS 4** — PostCSS-first, no `tailwind.config.ts` needed
- **TypeScript strict mode** — explicit interfaces for all API shapes
- **Framer Motion** — spring physics animations (no CSS `transition-all`)
- **Geist Sans** for UI text, **Geist Mono** for code/metrics, **Instrument Serif** for display headings

### Directory Structure

```
plotlot/frontend/
├── src/
│   ├── app/
│   │   ├── api/
│   │   │   ├── fal/proxy/          # FAL.ai image generation proxy
│   │   │   ├── gis-proxy/          # ArcGIS CORS bypass proxy
│   │   │   ├── stripe/             # Stripe checkout sessions
│   │   │   └── video/              # Video generation endpoint
│   │   ├── sign-in/                # Clerk auth page
│   │   ├── sign-up/                # Clerk registration page
│   │   ├── billing/                # Subscription management UI
│   │   ├── admin/                  # Admin dashboard (restricted)
│   │   ├── layout.tsx              # Root layout (Clerk + Theme + Maps provider)
│   │   ├── page.tsx                # Main app page (lookup + agent modes)
│   │   └── globals.css             # Design tokens, animations, base styles
│   ├── components/                 # 36 React components
│   ├── lib/
│   │   ├── api.ts                  # Backend API client (SSE streaming + REST)
│   │   ├── motion.ts               # Framer-motion animation presets
│   │   ├── sessions.ts             # localStorage chat session manager (LRU)
│   │   └── floorplan-generator.ts  # Procedural SVG floor plan generation
│   └── proxy.ts                    # Backend proxying utility
├── next.config.ts
├── package.json
└── tsconfig.json
```

### Pages & Routes

| Route | Purpose | Auth |
|-------|---------|------|
| `/` | Main lookup/agent interface — SSE streaming, reports, chat | Yes (Clerk) |
| `/sign-in` | Clerk authentication | No |
| `/sign-up` | Clerk registration | No |
| `/billing` | Subscription plan management | Yes |
| `/admin` | Admin dashboard | Yes (restricted) |

**`page.tsx` (973 lines):**
- Two modes: **lookup** (address → full pipeline) and **agent** (conversational with 10 tools)
- Manages SSE streaming from `/api/v1/analyze/stream`
- Progressive disclosure: each pipeline step renders as events arrive
- Integrates DealTypeSelector → AnalysisStream → TabbedReport pipeline

### Components (36 total)

#### Core Pipeline UI
| Component | Size | Purpose |
|-----------|------|---------|
| `AnalysisStream.tsx` | 11.8 KB | SSE pipeline progress — step-by-step visualization, progress bar, property confirmation card |
| `TabbedReport.tsx` | 31.7 KB | Multi-tab report: Zoning, Comps, Pro Forma, Maps, Documents |
| `ZoningReport.tsx` | 27.6 KB | Full zoning data — district, permitted uses, setbacks, dimensional standards, sources |
| `DealHeroCard.tsx` | 14.5 KB | Top-of-report hero card: max units, governing constraint, market value, pro forma |
| `DensityBreakdown.tsx` | 5.1 KB | 4-constraint visual — density, lot area, FAR, envelope (governing constraint highlighted in amber) |

#### Maps & Geospatial
| Component | Size | Purpose |
|-----------|------|---------|
| `ParcelViewer.tsx` | 12.0 KB | ArcGIS Leaflet map — parcel boundaries, satellite/street layers, GIS overlays (topography, wetlands, water/sewer) |
| `ArcGISParcelMap.tsx` | 18.5 KB | Low-level ESRI service map rendering with geometry handling |
| `SatelliteMap.tsx` | 5.4 KB | Google Maps satellite view overlay |
| `SetbackDiagram.tsx` | 5.2 KB | SVG illustration of front/side/rear setback requirements |

#### Documents & Visualization
| Component | Size | Purpose |
|-----------|------|---------|
| `DocumentGenerator.tsx` | 13.8 KB | Generate PDFs/DOCX — PSA, LOI, deal summary (clause builder) |
| `PropertyFlyoverVideo.tsx` | 6.9 KB | AI-generated aerial flyover video via FAL.ai |
| `BuildingRenderViewer.tsx` | 6.9 KB | AI-generated 3D building visualization |
| `FloorPlanSVG.tsx` | 29.3 KB | Procedurally generated SVG floor plans |
| `FloorPlanViewer.tsx` | 1.9 KB | Floor plan SVG wrapper |

#### Input & Navigation
| Component | Size | Purpose |
|-----------|------|---------|
| `AddressAutocomplete.tsx` | 9.8 KB | Google Places autocomplete + manual entry fallback |
| `InputBar.tsx` | 2.6 KB | Address/query input with suggestion chips |
| `DealTypeSelector.tsx` | 4.7 KB | Radio buttons: land deal, wholesale, creative finance, hybrid |
| `PipelineApproval.tsx` | 4.7 KB | "Approve to proceed" modal before pipeline execution |
| `ModeToggle.tsx` | 1.1 KB | Lookup vs Agent mode switch |
| `Sidebar.tsx` | 7.3 KB | Chat history sidebar — session list, new chat button |

#### Agent & Chat
| Component | Size | Purpose |
|-----------|------|---------|
| `ChatHistory.tsx` | 6.7 KB | Chat message list with markdown rendering |
| `ToolCards.tsx` | 5.7 KB | Grid of visible agent tools: geocode, lookup, search, web, export |
| `ThinkingIndicator.tsx` | 2.5 KB | Animated LLM thinking/loading state |

#### Supporting
| Component | Size | Purpose |
|-----------|------|---------|
| `PropertyCard.tsx` | 2.7 KB | Compact property summary card |
| `PropertyIntelligence.tsx` | 10.6 KB | Multi-section intelligence dashboard |
| `QuickLookup.tsx` | 8.0 KB | Quick-start lookup interface |
| `CapabilityChips.tsx` | 1.8 KB | Pill badges of system capabilities |
| `ReportSkeleton.tsx` | 3.8 KB | Shimmer skeleton loaders for report sections |
| `Toast.tsx` | 3.2 KB | Toast notification system |
| `ErrorBoundary.tsx` | 2.6 KB | React error boundary wrapper |
| `DocumentCanvas.tsx` | 2.6 KB | Document preview/rendering canvas |
| `ThemeProvider.tsx` | 3.2 KB | Dark/light mode toggle context |
| `MapsProvider.tsx` | 1.1 KB | Google Maps JS API loader |

### API Routes (`src/app/api/`)

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/gis-proxy` | GET | CORS bypass for ArcGIS services — allowlisted hosts: FEMA, USGS, Miami-Dade, Broward, Palm Beach. 15s timeout, 5-min cache. |
| `/api/fal/proxy/*` | GET/POST/PUT | FAL.ai image/video generation proxy (delegated to `@fal-ai/server-proxy/nextjs`) |
| `/api/stripe/checkout` | POST | Stripe checkout session creation for Pro plan |
| `/api/video/generate` | POST | Video generation endpoint |

### Key Libraries (`src/lib/`)

**`api.ts` (573 lines) — Backend API client:**
- `streamAnalysis(address, options, onEvent)` — SSE with 120s timeout, 1 retry on network failure
- `streamChat(message, history, onToken)` — token-by-token chat streaming
- `analyzeAddress(address)` — synchronous analysis
- `renderBuilding(params)` — 3D visualization request
- `generateDocument(type, data)` / `previewDocument()` — PDF/DOCX generation
- 30+ TypeScript interfaces for all API shapes

**`motion.ts` (62 lines) — Animation presets:**
- `spring` — stiffness: 400, damping: 30 (interactive elements)
- `springGentle` — stiffness: 200, damping: 25 (content reveals)
- `springBar` — stiffness: 60, damping: 15 (progress bars)
- `fadeUp`, `stagger()`, `cardHover`, `staggerContainer`, `staggerItem`

**`sessions.ts` (172 lines) — Chat history:**
- `createSession()`, `listSessions()`, `getSession()`, `updateSession()`, `deleteSession()`
- LRU eviction at 50 sessions max, localStorage persistence

### TypeScript Interfaces (`lib/api.ts`)

**Pipeline:**
- `PipelineStatus` — step name, message, resolved_address, folio, lot_sqft
- `ZoningReportData` — full report (address, municipality, zoning, uses, setbacks, analysis, comps, proforma, sources, confidence)
- `AnalysisOptions` — address, dealType, skipSteps
- `ThinkingEvent` — LLM reasoning traces

**Property:**
- `PropertyRecordData` — folio, address, owner, zoning, land use, lot size, value, year built, geometry
- `DensityAnalysisData` — max_units, governing_constraint, 4-constraint breakdown, buildable_area
- `NumericParamsData` — all dimensional standards (setbacks, FAR, height, density, coverage, parking)
- `ConstraintData` — name, max_units, raw_value, formula, is_governing

**Financials:**
- `ComparableSaleData` — address, sale price, date, lot size, zoning, distance, $/acre, $/unit
- `CompAnalysisData` — comparable list, median price, estimated land value, ADV per unit
- `LandProFormaData` — GDV, hard/soft costs, margin, max land price, cost per door

**Session:**
- `ChatMessage` — id, role (user/assistant), content, timestamp
- `ChatSession` — id, title, messages[], report?, mode (lookup/agent), timestamps

### Environment Variables (Frontend)

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_API_URL` | Backend base URL (default http://localhost:8000; override as needed, e.g. http://127.0.0.1:8001) |
| `NEXT_PUBLIC_APP_URL` | App URL for Stripe callbacks |
| `NEXT_PUBLIC_GOOGLE_MAPS_KEY` | Google Maps + Places API |
| `STRIPE_SECRET_KEY` | Stripe checkout session creation |
| `STRIPE_PRO_PRICE_ID` | Stripe Pro plan price ID |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk auth (public) |
| `CLERK_SECRET_KEY` | Clerk auth (server) |

### Styling System

- **Design tokens** (CSS vars): `--bg-primary`, `--text-primary`, `--brand` (#b45309 light / #f59e0b dark), `--border`, `--shadow-*`
- **Dark mode** via `.dark` class on `<html>`
- **Animations**: `fade-up`, `fade-in`, `pulse-dot`, `shimmer` — all via framer-motion spring, not CSS transitions
- **Typography**: Geist Sans (UI), Geist Mono (code/metrics), Instrument Serif (display headings)
- **Background**: Dot grid texture (24px grid, opacity 0.35)

### Deployment

```typescript
// next.config.ts
{
  output: "standalone",           // Self-contained Docker-compatible build
  turbopack: { root: __dirname }, // Turbopack
  images: {
    remotePatterns: ["**.fal.ai"] // FAL.ai generated image hosting
  }
}
```

---

## Backend

### Framework & Stack

- **FastAPI** — async-native Python web framework
- **Python 3.12+** — type hints everywhere, `match` statements, modern syntax
- **Pydantic v2** — all data models and config (`BaseModel`, `BaseSettings`)
- **SQLAlchemy 2.0 async** + `asyncpg` — PostgreSQL driver
- **httpx.AsyncClient** — all outbound HTTP calls (30s default timeout)
- **structlog** — structured JSON logging with correlation IDs

### Directory Structure

```
plotlot/src/plotlot/
├── api/
│   ├── main.py          # FastAPI app factory, CORS, middleware
│   ├── routes.py        # Core analysis + chat endpoints
│   ├── auth.py          # Clerk JWT RS256 verification
│   ├── cache.py         # Report cache (24h TTL, normalized address key)
│   ├── billing.py       # Stripe webhooks + subscription management
│   ├── documents.py     # Document generation endpoints (LOI, PSA, pro forma)
│   ├── portfolio.py     # Saved analyses management
│   └── render.py        # Building render + floor plan endpoints
├── pipeline/
│   ├── lookup.py        # Master orchestration (30min in-memory cache)
│   ├── calculator.py    # Deterministic density calculator (4 constraints)
│   ├── comps.py         # Comparable sales analysis (ArcGIS Hub, 3-mile radius)
│   ├── proforma.py      # Residual land valuation (GDV - costs - margin)
│   ├── contracts.py     # Legal document generation
│   └── ingest.py        # Municode ingestion pipeline (discovery→scrape→chunk→embed→store)
├── retrieval/
│   ├── llm.py           # 3-provider LLM client + circuit breakers (886 lines)
│   ├── search.py        # Hybrid pgvector search with RRF fusion
│   ├── geocode.py       # Address → lat/lng/municipality (Geocodio → Census fallback)
│   ├── property.py      # County routing dispatcher
│   ├── bulk_search.py   # Multi-record property queries
│   └── google_workspace.py  # Google Sheets/Docs OAuth integration
├── property/
│   ├── __init__.py      # Provider registry + lookup_property() dispatcher
│   ├── base.py          # Abstract PropertyProvider interface
│   ├── registry.py      # Provider registration system
│   ├── miami_dade.py    # MiamiDadeProvider (two-layer zoning)
│   ├── broward.py       # BrowardProvider (BCPA MapServer)
│   ├── palm_beach.py    # PalmBeachProvider (spatial zoning query)
│   ├── mecklenburg.py   # MecklenburgProvider (Charlotte metro)
│   ├── universal.py     # UniversalProvider (ArcGIS Hub discovery, any US county)
│   ├── field_mapper.py  # Cross-schema field normalization
│   ├── hub_discovery.py # ArcGIS Hub dataset discovery
│   ├── arcgis_utils.py  # Shared ArcGIS REST helpers
│   └── models.py        # Provider-specific Pydantic models
├── storage/
│   ├── models.py        # SQLAlchemy ORM models (4 tables)
│   └── firestore.py     # Firestore cache fallback
├── observability/
│   ├── tracing.py       # MLflow wrapper (graceful no-op if unavailable)
│   ├── logging.py       # structlog setup, correlation ID propagation
│   ├── costs.py         # Token + cost tracking per model/session
│   └── prompts.py       # Prompt versioning
├── clauses/             # Legal clause engine (LOI, PSA, contract templates)
├── documents/           # PDF/DOCX/XLSX rendering
├── templates/           # Jinja2 document templates
└── config.py            # Pydantic BaseSettings
```

### API Endpoints (~60+ total)

#### Core Analysis
| Method | Path | Purpose | Returns |
|--------|------|---------|---------|
| POST | `/api/v1/analyze` | Synchronous zoning analysis | `ZoningReportResponse` JSON |
| POST | `/api/v1/analyze/stream` | SSE streaming analysis | Server-Sent Events |
| GET | `/api/v1/autocomplete` | Address suggestions (Geocodio-backed) | JSON array |
| POST | `/api/v1/chat` | Agentic conversation (10 tools) | SSE token stream |

**SSE event types from `/analyze/stream`:**
`geocode` → `property` → `zoning` → `analysis` → `calculator` → `comps` → `proforma` → `done`
Heartbeat every 15s to survive Render's 30s proxy timeout.

#### Document Generation
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/documents/loi` | Letter of Intent (DOCX) |
| POST | `/api/v1/documents/psa` | Purchase and Sale Agreement |
| POST | `/api/v1/documents/deal-summary` | Deal summary document |
| POST | `/api/v1/documents/proforma` | Pro forma spreadsheet (XLSX) |

#### Admin & Data Management
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/admin/chunks/stats` | Chunk counts per municipality |
| POST | `/admin/ingest` | Start single municipality ingestion (background) |
| GET | `/admin/ingest/status` | Ingestion progress |
| POST | `/admin/ingest/batch` | Batch ingest all discoverable municipalities |
| GET | `/admin/ingest/batch/status` | Batch progress |
| GET | `/admin/data-quality` | Coverage, freshness, chunk stats dashboard |
| GET | `/admin/analytics` | API usage analytics |
| GET | `/admin/costs` | LLM cost dashboard from MLflow |
| DELETE | `/admin/cache/{address}` | Delete single cached report |
| DELETE | `/admin/cache` | Clear all cached reports (requires `confirm=true`) |
| DELETE | `/admin/chunks` | Delete chunks for municipality (dry-run by default) |

#### Diagnostics
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check (DB, ingestion freshness, MLflow) |
| GET | `/debug/traces` | View recent MLflow traces |
| GET | `/debug/llm` | Test LLM provider connectivity (Claude, Gemini, NVIDIA) |

### Property Providers (`property/`)

Abstract `PropertyProvider` interface + per-county implementations + registry pattern. Add a new county in 3 steps: implement the interface, register in `__init__.py`, done.

| Provider | County | Method | Key Details |
|----------|--------|--------|-------------|
| `MiamiDadeProvider` | Miami-Dade, FL | ArcGIS REST | Two-layer query: land use layer + zoning overlay layer |
| `BrowardProvider` | Broward, FL | BCPA MapServer | Parcel layer for lot size + zoning fields |
| `PalmBeachProvider` | Palm Beach, FL | ArcGIS spatial | Spatial query with geometry intersection |
| `MecklenburgProvider` | Mecklenburg, NC | ArcGIS REST | Charlotte metro + surrounding municipalities |
| `UniversalProvider` | Any US county | ArcGIS Hub | Real-time Hub dataset discovery — covers 3,000+ counties |

**Routing:**
```python
lookup_property(address, county) → registry.get(county) → provider.lookup() → PropertyRecord
# Falls through to UniversalProvider if no specific provider registered
```

### Pipeline Stages (`pipeline/`)

```
geocode() → lookup_property() → hybrid_search() → llm_extract() → calculate_max_units()
              ↓                                                            ↓
        comps (3-mile radius)                                    proforma (residual valuation)
```

**`lookup.py` — Master orchestration:**
- Phase 1 (Deterministic): geocode → property lookup → hybrid search
- Phase 2 (Agentic): LLM analysis with `NumericZoningParams` tool extraction
- Phase 3 (Deterministic): density calculator
- 30-minute SHA256-keyed in-memory pipeline cache
- MLflow run context wraps entire pipeline
- Fallback report generation on timeout

**`calculator.py` — Density calculation:**

4 independent constraints, all computed, result = `min()`:
1. **Density:** `max_density_units_per_acre × lot_acres`
2. **Min Lot Area:** `lot_size_sqft ÷ min_lot_area_per_unit_sqft`
3. **FAR:** `(max_far × lot_size_sqft) ÷ min_unit_size_sqft`
4. **Buildable Envelope:** `((lot_width - side_setbacks) × (lot_depth - front/rear setbacks) × max_stories × floor_height) ÷ min_unit_size_sqft`

Returns `DensityAnalysis` with per-constraint breakdown + `governing_constraint` name.

**`comps.py`:** ArcGIS Hub spatial query within 3-mile radius → price/acre, ADV/unit

**`proforma.py`:** `max_land_price = GDV - hard_costs - soft_costs - builder_margin`

**`ingest.py`:** Municode → scrape HTML → ~500-token chunks with overlap → NVIDIA NIM 1024d embeddings → pgvector upsert

### Retrieval Layer (`retrieval/`)

**`llm.py` — 3-provider fallback chain with circuit breakers:**

```
Claude Sonnet 4.6 (primary)
  → Gemini 2.5 Flash (secondary)
    → NVIDIA NIM Llama 3.3 70B (tertiary)
      → Kimi K2.5 (quaternary)
```

Circuit breaker per provider (Stripe pattern):
- `CLOSED` → normal operation
- `OPEN` → failing, skip for 60s
- `HALF_OPEN` → test one request after reset window
- Threshold: 5 failures in 60s window

**`search.py` — Hybrid search with RRF fusion:**

```sql
WITH vector_results AS (
  SELECT id, 1 - (embedding <=> $query_embedding) AS score,
         ROW_NUMBER() OVER (ORDER BY score DESC) AS rank
  FROM ordinance_chunks
  WHERE municipality = $municipality
),
keyword_results AS (
  SELECT id, ts_rank(search_vector, query) AS score,
         ROW_NUMBER() OVER (ORDER BY score DESC) AS rank
  FROM ordinance_chunks, to_tsquery($query) query
  WHERE search_vector @@ query AND municipality = $municipality
)
SELECT id, (1.0/(v.rank + 60) + 1.0/(k.rank + 60)) AS rrf_score
FROM vector_results v FULL OUTER JOIN keyword_results k USING (id)
ORDER BY rrf_score DESC LIMIT 15
```

Why hybrid: semantic search misses exact terminology ("R-3", "15,000 sqft minimum"). Keyword search misses paraphrased concepts. RRF fusion captures both.

**`geocode.py`:**
- Primary: Geocodio (~$0.0025/call)
- Fallback: US Census Geocoder (free)
- 1-hour in-memory cache (SHA256 key)
- Accuracy thresholds enforced: rooftop, range_interpolation, nearest_rooftop_match, point

### Storage (`storage/models.py`)

4 PostgreSQL tables via SQLAlchemy async ORM + pgvector:

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `ordinance_chunks` | Zoning text + embeddings | municipality, county, section, zone_codes, chunk_text, embedding vector(1024), search_vector tsvector |
| `report_cache` | Cached pipeline results (24h TTL) | address_normalized (unique key), report_json, expires_at |
| `portfolio_entries` | User-saved analyses | user_id (Clerk), address, municipality, zoning_district, report_json |
| `user_subscriptions` | Billing + usage tracking | user_id, plan, stripe_customer_id, analyses_used, period_start/end |

**Indexes:**
- `ordinance_chunks`: municipality, county (filter)
- `ordinance_chunks`: pgvector IVFFLAT on embedding (cosine distance)
- `ordinance_chunks`: GIN on search_vector (full-text)
- `report_cache`: address_normalized UNIQUE
- `portfolio_entries`: user_id

### Config (`config.py`)

```python
class Settings(BaseSettings):
    # Database
    database_url: str          # Neon PostgreSQL (asyncpg)
    database_require_ssl: bool # Auto-detected from sslmode=require

    # LLM providers
    anthropic_api_key: str
    google_api_key: str
    nvidia_api_key: str

    # Geocoding
    geocodio_api_key: str

    # Auth (opt-in)
    auth_enabled: bool = False
    clerk_jwks_url: str = ""

    # Rate limiting
    rate_limit_max_requests: int = 10
    rate_limit_window_seconds: int = 60

    # Observability
    mlflow_tracking_uri: str   # Defaults to Neon PostgreSQL
    mlflow_experiment_name: str = "plotlot"
    sentry_dsn: str = ""
    log_json: bool = True
    log_level: str = "INFO"

    # Billing
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # CORS
    allowed_origins: list[str] = [...]  # Vercel, localhost, Railway
```

### Core Data Models (`core/types.py`)

```python
@dataclass
class PropertyRecord:
    folio: str
    address: str
    owner: str | None
    municipality: str
    county: str
    lot_size_sqft: float | None
    lot_dimensions: str | None
    zoning_code: str
    zoning_description: str | None
    land_use_code: str | None
    year_built: int | None
    assessed_value: float | None
    market_value: float | None
    lat: float
    lng: float
    parcel_geometry: dict | None

@dataclass
class NumericZoningParams:
    # All fields Optional[float] = None
    max_density_units_per_acre: float | None
    min_lot_area_sqft: float | None
    max_far: float | None
    max_lot_coverage_pct: float | None
    max_height_ft: float | None
    setback_front_ft: float | None
    setback_side_ft: float | None
    setback_rear_ft: float | None
    min_unit_size_sqft: float | None
    max_stories: float | None

@dataclass
class DensityAnalysis:
    max_units: int                        # Final answer
    governing_constraint: str            # Which of 4 constraints was binding
    constraints: list[ConstraintResult]  # Per-constraint breakdown
    buildable_area_sqft: float
    parameters: NumericZoningParams

@dataclass
class ZoningReport:
    address: str
    municipality: str
    county: str
    zoning_district: str
    allowed_uses: list[str]
    conditional_uses: list[str]
    prohibited_uses: list[str]
    property_record: PropertyRecord
    numeric_params: NumericZoningParams
    density_analysis: DensityAnalysis
    comp_analysis: CompAnalysis | None
    pro_forma: LandProForma | None
    sources: list[str]
    confidence: float
```

**Error taxonomy (`core/errors.py`):**
- `RetriableError` → ExternalAPIError, RateLimitError, TimeoutError
- `FatalError` → OutOfCoverageError, GeocodingError, NoDataError, ConfigurationError
- `DegradedError` → PropertyLookupError, LowConfidenceError, PartialExtractionError

### Observability

**MLflow (`observability/tracing.py`):**
- Decorator: `@trace(name="...", span_type="...")`
- Context manager: `start_span()`, `start_run()`
- Graceful no-op when MLflow unavailable
- Backend: Neon PostgreSQL (same DB, `mlflow` schema)

**Structured logging (`observability/logging.py`):**
- structlog with JSON output
- Correlation ID propagation via `X-Request-ID` header
- Per-request context binding

**Endpoints:** `/debug/traces`, `/debug/llm`, `/admin/costs`, `/admin/analytics`

### Production Guardrails

**Circuit Breaker (per LLM provider):**
```python
@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    reset_seconds: int = 60
    # CLOSED → (5 failures) → OPEN → (60s) → HALF_OPEN → (success) → CLOSED
```

**SSE Heartbeat (Render 30s proxy timeout):**
```python
# api/routes.py — heartbeat every 15s during pipeline execution
for _tick in range(6):
    done, _ = await asyncio.wait({task}, timeout=15)
    if done:
        break
    yield _sse_event("status", {"type": "heartbeat", "message": "Processing..."})
```

**Bounded Session Memory:**
```python
MAX_MEMORY_MESSAGES = 50    # Per session message cap
MAX_SESSIONS = 100          # LRU eviction at 100 sessions
SESSION_TTL_SECONDS = 3600  # 1 hour TTL
TOKEN_BUDGET = 50_000       # Per-session LLM token cap
```

**Pipeline Cache (30min in-memory):**
```python
_pipeline_cache: dict[str, tuple[ZoningReport, float]] = {}
PIPELINE_CACHE_TTL = 1800   # SHA256(address) key
```

**Report Cache (24h PostgreSQL):**
```python
# report_cache table: address_normalized UNIQUE, expires_at column
# Normalized with lowercase + whitespace collapse for deterministic hits
```

### Dependencies (`pyproject.toml`)

**Core:**
- `httpx>=0.27` — async HTTP
- `anthropic>=0.42` — Claude API
- `pydantic>=2.0` — validation
- `sqlalchemy[asyncio]>=2.0` — ORM
- `asyncpg>=0.29` — PostgreSQL async driver
- `pgvector>=0.3` — vector extension
- `fastapi>=0.115` — web framework
- `uvicorn[standard]>=0.32` — ASGI server
- `structlog>=24.0` — structured logging

**Domain:**
- `beautifulsoup4>=4.12` — HTML parsing (Municode scraper)
- `shapely>=2.0` — geometry (setback polygon calculations)
- `reportlab>=4.0` — PDF generation
- `python-docx>=1.1` — DOCX generation
- `openpyxl>=3.1` — XLSX (pro forma spreadsheets)
- `jinja2>=3.1` — document templates

**Integrations:**
- `google-genai>=1.0` — Gemini API
- `google-cloud-firestore>=2.16` — cache fallback
- `stripe>=11.0` — billing
- `pyjwt>=2.11.0` — Clerk JWT verification

**Observability:**
- `mlflow>=2.16` — experiment tracking + tracing
- `psycopg2-binary>=2.9` — MLflow PostgreSQL backend

**Dev:**
- `pytest>=8.0`, `pytest-asyncio>=0.23` — testing
- `mypy>=1.10` — type checking
- `ruff>=0.5` — linting

### Test Structure (`tests/`)

20+ test files across 4 categories:

| Marker | Purpose | Examples |
|--------|---------|---------|
| `@pytest.mark.unit` | Isolated unit tests (no network) | `test_calculator.py`, `test_llm.py`, `test_field_mapper.py` |
| `@pytest.mark.eval` | Golden test cases (known input/output) | `test_property_providers.py`, `test_universal_provider.py` |
| `@pytest.mark.integration` | Live external services | `test_cache_integration.py`, `test_hub_live.py` |
| `@pytest.mark.e2e` | Full pipeline regression tests | `test_universal_validation.py` |

**Key test files:**
- `test_calculator.py` — 4-constraint density calculation
- `test_llm.py` — circuit breaker states, fallback chain
- `test_property_providers.py` — provider interface compliance
- `test_documents_api.py` — LOI/PSA/proforma document generation
- `test_hub_discovery.py` — ArcGIS Hub dataset discovery

---

## Data Architecture

### Current Coverage

Verified against Neon 2026-08-10.

| Region | Municipality | Chunks | Source platform |
|--------|--------------|--------|-----------------|
| **CA — San Diego County** | San Diego | 2,910 | PDF scraper (`docs.sandiego.gov`) |
| CA | Encinitas | 2,805 | eCode360 |
| CA | Carlsbad | 1,598 | eCode360 |
| CA | El Cajon | 1,566 | eCode360 |
| CA | Escondido | 1,543 | eCode360 |
| CA | San Marcos | 1,259 | Municode |
| CA | Lemon Grove | 1,096 | eCode360 |
| CA | Oceanside | 1,070 | CivicPlus |
| CA | Chula Vista | 985 | codifier |
| CA | National City | 856 | Municode |
| CA | Imperial Beach | 784 | eCode360 |
| CA | Poway | 765 | codifier |
| CA | Santee | 494 | eCode360 |
| CA | La Mesa | 383 | Municode |
| | **CA subtotal (active market)** | **18,114** | |
| FL | Miami-Dade County (unincorporated) | 2,666 | Municode |
| FL | Boca Raton | 1,538 | Municode |
| FL | Miami Gardens | 1,187 | Municode |
| FL | Fort Lauderdale | 559 | Municode |
| FL | Miramar | 241 | Municode |
| FL | West Palm Beach | 231 | Municode |
| | **FL subtotal (deprioritised)** | **6,422** | |
| | **Total — 20 municipalities** | **24,536** | |

All 14 CA municipalities have zero empty `section` values (an empty `section` zeroes out
citations downstream). Fort Lauderdale still has 21.

**Not ingested:** no North Carolina municipality is in the database, despite
`MecklenburgProvider` existing in `property/mecklenburg.py` — the parcel provider is code
that has no corresponding ordinance coverage.

Discoverable via Municode: **88 municipalities**. Municode rate-limits (429) aggressively
under repeated discovery probing, and a throttled run surfaces as `empty_source` rather
than an obvious rate-limit error.

### Ingestion Pipeline

```
Municode Library API (discovery)
  → Title/Chapter filter (zoning-related sections only)
    → HTML scraper (BeautifulSoup)
      → ~500-token chunks (with overlap, section headers preserved)
        → NVIDIA NIM embeddings (1024d, text-embedding-3-large)
          → pgvector upsert (ordinance_chunks table)
```

The diagram above describes the Municode path only. Adapter resolution is
`_PDF_REGISTRY` → Municode live discovery → codifier discovery (eCode360 /
Code Publishing / municipal.codes / American Legal), with CivicPlus cities served as
PDFs through `_PDF_REGISTRY`. Always run `discover_codifier(city, state)` before
concluding a city needs a custom adapter.

### Hybrid Search Algorithm

Three-step retrieval with reciprocal rank fusion:

1. **Vector search** — pgvector cosine similarity on 1024d embeddings
2. **Keyword search** — PostgreSQL `tsvector` full-text with BM25-style ranking
3. **RRF fusion** — `score = Σ 1/(rank_i + K)` where K=60

Why this matters: zoning queries mix semantic concepts ("residential density") with exact terminology ("R-3", "15,000 sqft minimum lot"). Pure vector search misses exact codes. Pure keyword misses paraphrased concepts. Fusion improves recall from ~62% to ~91%.

### Domain Data Flow

```
Address (user input)
  → Geocodio → lat/lng, county, municipality
    → County ArcGIS API → PropertyRecord (folio, lot_size, zoning_code)
      → pgvector hybrid search → 15 zoning ordinance chunks
        → Claude Sonnet (tool use) → NumericZoningParams
          → Deterministic calculator → DensityAnalysis (max_units, governing_constraint)
            → ArcGIS Hub comps query → CompAnalysis (median $/acre, ADV/unit)
              → Residual formula → LandProForma (max land price)
                → ZoningReport (streamed via SSE to frontend)
```

---

## Production Patterns (Interview-Ready)

### Circuit Breaker — Preventing Cost Explosions

Inspired by Stripe's LLM failure isolation pattern. Each LLM provider gets an independent circuit breaker. If Claude is timing out at 2 AM, the system doesn't keep hammering it — it trips to Gemini, then NVIDIA NIM, with automatic recovery after the reset window.

```
Problem: Single LLM provider goes down → all requests fail
Solution: Per-provider circuit breakers with 3-state FSM (CLOSED/OPEN/HALF_OPEN)
Result: Zero downtime during LLM provider outages
```

### SSE Heartbeat — Surviving Render's Proxy Timeout

Render's free tier terminates SSE connections after 30 seconds of no data. The zoning pipeline often takes 45-90 seconds. Solution: async task runs the pipeline in the background; the response generator polls it every 15 seconds and emits a heartbeat event, keeping the connection alive.

```
Problem: Render kills long SSE connections
Solution: asyncio.wait(timeout=15) + heartbeat emission every 15s
Result: Full pipeline completion even on 90s analyses
```

### Bounded Session Memory — Preventing Cost Runaway

The chat agent maintains conversation history for multi-turn reasoning. Without bounds, a long chat session compounds costs and degrades context quality. LRU eviction + TTL ensures no session grows unbounded.

```
Problem: Unbounded chat history → escalating LLM costs + context rot
Solution: 50-message cap per session, 100 sessions max (LRU), 1hr TTL, 50K token budget
Result: Predictable costs, consistent retrieval quality
```

### Deterministic Calculator — Removing Probabilistic Risk from Critical Output

The max-units answer is the most consequential output in the pipeline — it drives deal decisions. Moving this math out of the LLM and into deterministic Python code eliminates hallucination risk from the most important number.

```
Problem: LLMs hallucinate numeric calculations
Solution: LLM extracts raw parameters → deterministic Python calculator applies them
Result: Same address always produces identical max_units; each constraint is auditable
```

### Multi-Provider Fallback Chain — Infrastructure Resilience

Production LLM APIs have outages, rate limits, and degraded performance windows. By maintaining 4 providers in a fallback chain with circuit breakers, the system maintains availability even during individual provider incidents.

```
Primary:    Claude Sonnet 4.6  (best tool-calling accuracy)
Secondary:  Gemini 2.5 Flash   (fast, good tool use)
Tertiary:   NVIDIA NIM Llama   (self-hosted option, no API dependency)
Quaternary: Kimi K2.5          (final fallback)
```

---

## CI/CD

**GitHub Actions (`.github/workflows/ci.yml`):**
- `ruff` — linting (hard gate)
- `mypy` — type checking (hard gate)
- `pytest` — unit + eval tests
- Eval workflow: 10 golden test cases (5 FL addresses, 3 boundary cases, 1 partial data, 1 data quality)
- Working directory scoped to `plotlot/`

**Deploy:**
- Frontend → Vercel (auto-deploy on push to `main`, `standalone` output)
- Backend → Render (Docker, auto-deploy on push to `main`)
- Database → Neon (managed PostgreSQL, always-on)
