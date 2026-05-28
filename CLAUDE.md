# EP Engineering Lab — Monorepo

## Who This Is For (Read First)

**User:** Phat (the actual user — the persona files say "Earl Perry" but you are working with Phat)
**Goal:** Build PlotLot into a real product with paying users. Secondary goal: portfolio for a high 6-7 figure ML/LLMOps role.
**Working style:** Action over talk. Ship first, explain after. No Co-Authored-By trailers on commits. Commits under Earl Perry's git name only.

---

## Monorepo Structure

| Directory | Project | Status |
|-----------|---------|--------|
| `plotlot/` | PlotLot v2 — AI zoning analysis | **Active** |
| `outreach-agent/` | Autonomous sales outreach agent | **Active** |
| `mangoai/` | MangoAI — Agricultural vision | Planned |
| `agent-forge/` | Agent Forge — Multi-agent tools | Planned |
| `agent-eval/` | Agent Eval — LLM evaluation | Planned |

---

## PlotLot v2

### What It Is

AI-powered land deal intelligence platform. Given a US property address:
1. Geocodes the address → retrieves zoning ordinances
2. Agentic LLM extracts numeric dimensional standards (setbacks, FAR, density)
3. Deterministic calculator computes max allowable dwelling units
4. Comparable sales analysis estimates land value
5. Pro forma calculates max offer price
6. Frontend streams results via SSE with progressive disclosure

Live at **plotlot.app** (frontend Vercel, backend Render, database Neon PostgreSQL).

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Python 3.12+ (async-first, Pydantic everywhere) |
| Database | Neon PostgreSQL + pgvector (hybrid search, RRF fusion) |
| Frontend | Next.js 16 + React 19 + Tailwind CSS 4 (Vercel) |
| LLM | Claude Sonnet 4.6 → Gemini 2.5 Flash → NVIDIA Llama 3.3 70B → Kimi K2.5 |
| Embeddings | NVIDIA NIM (1024d) |
| Observability | MLflow tracing → Neon PostgreSQL |
| Property Data | ArcGIS Hub (universal) + hardcoded county providers |
| Zoning Docs | Municode API (88 municipalities) + custom PDF scrapers |

### Current Data Coverage (as of 2026-05-28)

| Municipality | Chunks | County | Source |
|-------------|--------|--------|--------|
| Unincorporated Miami-Dade | 2,666 | Miami-Dade | Municode |
| Hayward | 2,537 | Alameda | Municode |
| Oakland | 2,399 | Alameda | Municode |
| Richmond | 1,738 | Contra Costa | Municode |
| Boca Raton | 1,538 | Palm Beach | Municode |
| Milpitas | 1,420 | Santa Clara | Municode |
| San Jose | 1,409 | Santa Clara | Municode |
| Lafayette | 1,361 | Contra Costa | Municode |
| Miami Gardens | 1,187 | Miami-Dade | Municode |
| Los Altos | 1,159 | Santa Clara | Municode |
| East Palo Alto | 1,138 | San Mateo | Municode |
| Campbell | 1,083 | Santa Clara | Municode |
| Moraga | 1,016 | Contra Costa | Municode |
| Morgan Hill | 1,004 | Santa Clara | Municode |
| Rocklin | 990 | Placer | Municode |
| Citrus Heights | 955 | Sacramento | Municode |
| Saratoga | 952 | Santa Clara | Municode |
| Los Gatos | 884 | Santa Clara | Municode |
| Mountain View | 815 | Santa Clara | Municode |
| Portola Valley | 814 | San Mateo | Municode |
| Alameda | 806 | Alameda | Municode |
| El Cerrito | 742 | Contra Costa | Municode |
| Newark | 690 | Alameda | Municode |
| Lincoln | 670 | Placer | Municode |
| Orinda | 655 | Contra Costa | Municode |
| Daly City | 569 | San Mateo | Municode |
| Woodside | 453 | San Mateo | Municode |
| Monte Sereno | 405 | Santa Clara | Municode |
| Hillsborough | 249 | San Mateo | Municode |
| **San Diego** | **2,910** | San Diego | **Custom PDF scraper** |
| Miramar | 241 | Broward | Municode |
| Fort Lauderdale | 136 | Broward | Municode |
| Belmont | 44 | San Mateo | Municode |
| Redwood City | 5 | San Mateo | Municode |

**Total: ~35,000+ chunks** across 30+ municipalities.

### Key Architecture Notes

- **San Diego is NOT on Municode.** It uses a custom PDF scraper at `plotlot/src/plotlot/ingestion/san_diego_scraper.py` that downloads from `https://docs.sandiego.gov/municode/MuniCodeChapter{N}/Ch{N}Art{A}Division{D}.pdf`. SSL verification disabled (docs.sandiego.gov has a cert issue). Targets Ch11–Ch15.
- **San Diego chunking fix (critical):** PDF text from docs.sandiego.gov uses single `\n`, not `\n\n`. The chunker detects this and falls back to single-newline splitting. Without this, entire 143k-char PDFs become one chunk. This fix raised San Diego from 226 → 2,910 chunks.
- **California property data:** California statewide parcel layer covers all 58 CA counties including San Diego automatically (no separate ArcGIS config needed).
- **Ingestion CLI:** `uv run plotlot-ingest --san-diego` (from `plotlot/` directory). For Municode cities: `uv run plotlot-ingest --municipality "City Name"`.

### API Endpoints

- `POST /analyze` — SSE streaming pipeline. Events: `geocode`, `property`, `zoning`, `analysis`, `calculator`, `comps`, `proforma`, `heartbeat`, `error`, `done`
- `POST /chat` — Agentic chat with 10 tools
- `GET /health` — Health check
- `POST /admin/ingest` — Municipality ingestion

### Quick Commands

```bash
# Backend
uv run uvicorn plotlot.api.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev

# Tests
uv run pytest tests/unit/ -v
uv run pytest tests/eval/ -v

# Lint / type-check
uv run ruff check src/ tests/
uv run mypy src/plotlot/

# Ingest
uv run plotlot-ingest --municipality "City Name"
uv run plotlot-ingest --san-diego
```

---

## Outreach Agent

### What It Is

Autonomous B2B sales outreach system built to find and message potential PlotLot customers — real estate developers, residential builders, proptech reporters, and VCs.

Located at `outreach-agent/` with its own `pyproject.toml`.

### Architecture

- **Agents:** `prospect_finder`, `email_agent`, `event_scout`, `orchestrator`, `pitch_writer`
- **Tools:** Brave Search (LinkedIn discovery), Hunter.io (email enrichment), Gmail API (OAuth2 sending), Twitter/LinkedIn drafting, Eventbrite (event discovery)
- **Storage:** SQLite (`outreach.db`) with `Prospect`, `Event`, `OutreachMessage` tables
- **CLI:** `outreach find`, `outreach run`, `outreach status`

### Key Behaviors (Critical — Do Not Revert)

1. **Sign-off:** All emails/messages close with `Regards,\nPhat` (not `— Earl`)
2. **No demo URL in cold pitches.** The URL is ONLY shared after a prospect replies with interest. The pitch writer prompt explicitly: "Do NOT include any URLs or links. Refer to the product by name (PlotLot) only."
3. **CoStar is excluded.** Never add CoStar contacts or employees to the outreach pipeline.
4. **Domain lookup dict** in `outreach-agent/src/outreach/tools/hunter.py` has 30+ company → domain mappings, plus a partial-match fallback for fuzzy company names.
5. **LinkedIn manual sends:** The agent drafts connection notes; Phat sends them manually at 4–5/day to avoid spam detection.

### Active Prospect Targets

Focus: residential developers, proptech reporters/VCs in Bay Area and San Diego.

Companies/people to avoid: CoStar (explicit exclusion by Phat).

---

## Git State

### Branches

- `main` — production, auto-deploys to Render + Vercel
- `Phat` — **current working branch** (all recent work committed here)
- `feature/outreach-agent` — planned home for outreach-agent code (not yet pushed cleanly)

### What's on the Phat Branch (committed, pushed)

- San Diego PDF scraper (`san_diego_scraper.py`) — full implementation
- San Diego chunker fix (single `\n` fallback)
- `ingest_san_diego()` in `pipeline/ingest.py`
- `--san-diego` CLI flag in `cli.py`
- `SOCAL_METROS` in `ingestion/discovery.py`
- Ruff lint/format fixes across all above files

### Security History (Important)

Earlier in this session, `credentials.json` and `token.json` (Gmail OAuth) were accidentally staged and committed. They were removed via `git reset` + force push. The `outreach-agent/` directory is now **untracked** on the Phat branch — it should stay that way. Those files should never be committed.

`.gitignore` should exclude: `credentials.json`, `token.json`, `*.db`, `outreach.db`.

---

## Active Business Context

### Kevin Woo (LinkedIn — connected)

Kevin Woo is a real estate developer/investor who connected with Phat on LinkedIn and asked for San Diego data. Specifically requested analysis for **1233 Hueneme St, San Diego CA 92110** (Linda Vista area). San Diego is now fully ingested (2,910 chunks). Message to send: "Just added San Diego coverage — try 1233 Hueneme St at plotlot.app"

### New LinkedIn Connections (Need Intro Message Drafted)

These people accepted Phat's LinkedIn connection request and are now 1st-degree connections. They have NOT yet received a follow-up message. The next agent should draft a warm LinkedIn intro for each — longer than a connection request (since we're now connected, the character limit is lifted), no demo URL, close with `Regards,\nPhat`.

- **Jillian D'Onfro** (name may be spelled Gillian DeFron in some notes) — Reporter, likely SF Standard or similar Bay Area tech/real estate publication. Angle: PropTech story, PlotLot as an AI land analysis tool that residential developers are starting to use. She covers tech + real estate at the intersection. Write something that positions PlotLot as a story worth covering, not a sales pitch.

- **Jeremy** (last name unclear — may appear as "Jeremy Monty's" or similar in notes) — Connection context unknown. Draft a general warm intro that introduces PlotLot, mentions it helps residential developers underwrite land deals faster with AI-powered zoning analysis, and offers to let him stress-test it on a deal he's already underwritten. Do not include the URL — only share after he expresses interest.

**Tone for all:** Warm, peer-to-peer. Not a sales pitch. Phat is Vietnamese-American and values authentic connection. Reference the LinkedIn context naturally (e.g., "glad we connected"). Keep under 300 words each.

### Other Active Prospects (reached out, awaiting reply)

- **Brian Saliman** — Facebook message sent (Saliman Investments, residential developer)
- **Keith Manson** — Email sent to keithmanson@gmail.com
- **Biz Carson** — Email sent to bizcarson@gmail.com (reporter)
- **Kevin Truong** — Vietnamese-American reporter at SF Standard (kevin@sfstandard.com), tailored message leveraging shared Vietnamese heritage

---

## Coding Standards

### Python
- Python 3.12+, type hints on all signatures
- Pydantic `BaseModel` for data, `BaseSettings` for config
- Async-first: `httpx.AsyncClient`, `asyncpg`, `async def`
- No `print()` — use `structlog` or `logging`
- Ruff for linting/formatting (CI gate — must pass before push)

### TypeScript
- Next.js App Router, React 19, Tailwind CSS 4
- Explicit interfaces for all API response shapes
- Components in `src/components/`, utilities in `src/lib/`

### Testing
- Unit tests: `tests/unit/` — mock external services
- Eval tests: `tests/eval/` — 10 golden cases
- Integration tests: `tests/integration/` — live API tests
- `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed

---

## Environment Variables

| Variable | Project | Required | Description |
|----------|---------|----------|-------------|
| `DATABASE_URL` | plotlot | Yes | Neon PostgreSQL connection string |
| `NVIDIA_API_KEY` | plotlot | Yes | NVIDIA NIM API (pay-as-you-go plan) |
| `GEOCODIO_API_KEY` | plotlot | Yes | Geocodio geocoding |
| `GOOGLE_MAPS_API_KEY` | plotlot | Yes | Google Maps (frontend) |
| `NEXT_PUBLIC_API_URL` | plotlot | Yes | Backend API URL |
| `BRAVE_API_KEY` | outreach-agent | Yes | Brave Search for LinkedIn discovery |
| `HUNTER_API_KEY` | outreach-agent | Yes | Hunter.io email enrichment |

---

## Rules

1. Every code change ships with tests. No exceptions.
2. No over-engineering. Build what's needed now.
3. Track everything in MLflow.
4. Constraints beat capabilities.
5. Every production failure → regression test.
6. No `print()` in library code.
7. Pydantic everywhere. No raw dicts across function boundaries.
8. Async-first for I/O.
9. SSE heartbeat for long operations (Render 30s proxy timeout).
10. CLI-first tooling (`vercel`, `gh`, `uv`, `npx`).
11. **Never commit credentials.json, token.json, or .env files.**
12. **Never add CoStar to outreach targets.**
13. **No demo URL in cold pitch messages.**
14. **Commits under Earl Perry's git name only. No Co-Authored-By trailers.**

---

## AI Assistant Persona Reference

Persona files in `.claude/prompts/`: soul, spirit, creed, doctrine, mind, principles, personality, user, system.
Rule files in `.claude/rules/`: plotlot-backend, plotlot-frontend, plotlot-pipeline, plotlot-data-models, plotlot-ingestion, plotlot-chat, git-discipline.

TL;DR: Distinguished ML/LLMOps Engineer, production-first, direct, ships working code. The user is Phat (not Earl — Earl is the portfolio persona). Phat wants things done, not discussed.
