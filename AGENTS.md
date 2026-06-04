# EP Engineering Lab — Agent Handoff Document

> **Read this entire file before touching any code.**
> This is the authoritative context document for new agents. It covers what was built, what is broken, what was attempted, and exact next steps.

---

## Who You Are Working With

**User:** Phat (Vietnamese-American, Bay Area / San Diego market)
**Goal:** Ship PlotLot as a real product with paying customers. Kevin Woo is the first paying prospect in San Diego.
**Working style:** Action over talk. Ship first, explain after. No Co-Authored-By trailers. Commits under Earl Perry git name only.

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

## PlotLot v2 — What It Is

AI-powered land deal intelligence platform. Given a US property address:
1. Geocodes → retrieves zoning ordinances
2. Agentic LLM extracts numeric dimensional standards (setbacks, FAR, density)
3. Deterministic calculator computes max allowable dwelling units
4. Comparable sales analysis estimates land value
5. Pro forma calculates max offer price
6. Frontend streams results via SSE with progressive disclosure

Live at **plotlot.app** (frontend Vercel, backend Render, database Neon PostgreSQL).

---

## What Was Built / Accomplished This Session

### 1. San Diego Ingestion Pipeline — DONE (committed, pushed to `Phat` branch)

San Diego is NOT on Municode. Built a custom PDF scraper for `docs.sandiego.gov`.

**Files:**
- `plotlot/src/plotlot/ingestion/san_diego_scraper.py` — PDF scraper targeting Ch11–Ch15
- `plotlot/src/plotlot/pipeline/ingest.py` — `ingest_san_diego()` function
- `plotlot/src/plotlot/cli.py` — `--san-diego` CLI flag
- `plotlot/src/plotlot/ingestion/discovery.py` — `SOCAL_METROS` dict

**Critical chunker bug found and fixed:**
PDF text from `docs.sandiego.gov` uses single `\n` between lines, NOT `\n\n`. The paragraph-based chunker treated entire 143k-char PDFs as one chunk. Fixed by detecting absence of `\n\n` and falling back to single-newline splitting.
Result: **226 chunks → 2,910 chunks** for San Diego.

**To re-run ingestion:** `cd plotlot && uv run plotlot-ingest --san-diego`

### 2. Permissions — DONE

`.claude/settings.json` updated to allow all tool calls (`Bash(*)`, `Edit(*)`, `Write(*)`, `Read(*)`, `WebFetch(*)`, `WebSearch(*)`). Destructive ops still denied (`rm -rf`, force push, `reset --hard`).
`.gitignore` updated to exclude `.claude/settings.json`.

### 3. Stripe Billing — ALREADY EXISTS (discovered via audit, not built this session)

Fully wired at `src/plotlot/api/billing.py`. Current hardcoded price: **$49/month** Pro tier.
Free tier: 5 analyses/month. Pro: unlimited.

**To close Kevin Woo:**
- Create 50% coupon in Stripe dashboard
- Send him billing page URL + promo code
- Recommended price: **$150/month** (founding San Diego rate, half of eventual $300)

**Missing:** `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRO_PRICE_ID` need to be set in Render env vars.

### 4. Outreach Agent Permit Scraper — PARTIALLY BUILT (see Dead Ends section)

New files created in `outreach-agent/`:
- `src/outreach/tools/permit_scraper.py` — county assessor ArcGIS scraper (see limitations below)
- `src/outreach/agents/permit_prospect_finder.py` — dedup + SQLite insert logic
- `permits.py` — CLI entry point (`uv run python permits.py`)

**Status:** Unit tests pass. Live data retrieval has critical limitations (see Dead Ends).

---

## Current Data Coverage (as of 2026-05-28)

| Municipality | Chunks | County | Source |
|-------------|--------|--------|--------|
| San Diego | **2,910** | San Diego | Custom PDF scraper |
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
| + 20 more Bay Area / FL cities | ... | ... | Municode |

Total: ~35,000+ chunks across 30+ municipalities.

---

## Active Bugs in PlotLot Chat — DIAGNOSED, NOT YET FIXED

These bugs were observed in a live Kevin Woo chat session on PlotLot using **1233 Hueneme St, San Diego CA 92110**.

### Bug 1 — Wrong Density Answer (CRITICAL)

**Symptom:** Chat returned "1 dwelling unit per 4 acres" for RM-3-7 zone. Correct answer is ~1 unit per 700 sq ft lot area.

**Root cause (fully traced):**
`hybrid_search` in `search.py:18` takes a `zone_code` parameter used as BOTH the keyword query AND the `zone_code = ANY(zone_codes)` metadata filter. The chat agent passes the user's natural language question (e.g. `"density calculation"`) as this parameter — NOT the actual zone code `"RM-3-7"`. So `plainto_tsquery('density calculation')` matches the rural cluster alternative section in Ch13 which uses those exact words prominently. The `zone_code = ANY(zone_codes)` filter never fires because `"density calculation"` is never in the zone_codes array.

**Two-part fix:**

**Part A — `src/plotlot/api/chat.py` system prompt:**
Instruct agent to always prefix search queries with the zone code from `lookup_property_info`. Example: `"RM-3-7 density"` not just `"density"`.

**Part B — `src/plotlot/retrieval/search.py` `_hybrid_rrf` SQL (~line 80):**
Add zone-code boost to RRF score for chunks where zone code is in `zone_codes[]`:
```sql
-- Replace this line in the fused CTE:
COALESCE(1.0 / (:rrf_k + v.vrank), 0) +
COALESCE(1.0 / (:rrf_k + k.krank), 0) AS rrf_score

-- With:
COALESCE(1.0 / (:rrf_k + v.vrank), 0) +
COALESCE(1.0 / (:rrf_k + k.krank), 0) +
CASE WHEN :zone_code = ANY(COALESCE(v.zone_codes, k.zone_codes)) THEN 0.1 ELSE 0 END AS rrf_score
```
The 0.1 boost is larger than most RRF score differences at top of ranking (~0.015 per rank position).

### Bug 2 — `search_municode_live` Returns Nothing for San Diego (CRITICAL)

**Symptom:** Chat log shows `search_municode_live returned no results` for San Diego.

**Root cause:** `_execute_municode_live_search()` at `chat.py:1281` calls `get_municode_configs()` which queries the Municode API. San Diego is NOT on Municode — it uses our custom PDF pipeline. So `configs.get("san_diego")` returns `None` → immediate `no_results`. Agent then falls through to `web_search` which also fails (Bug 3).

**Fix:** Add short-circuit in `_execute_municode_live_search()` at `chat.py:1281`:
```python
# At the top of _execute_municode_live_search, before calling get_municode_configs():
PDF_ONLY_MUNICIPALITIES = {"San Diego"}
if municipality in PDF_ONLY_MUNICIPALITIES:
    return json.dumps({
        "status": "no_results",
        "message": f"{municipality} uses local PDF index — use search_zoning_ordinance instead."
    })
```

### Bug 3 — Web Search Fails with Payment Error

**Symptom:** `web_search failed due to a payment error`

**Root cause:** `_execute_web_search` at `chat.py:1401` uses Jina.ai. `JINA_API_KEY` is either unset in Render env vars or free tier exhausted.

**Fix:** Check Render env vars for `JINA_API_KEY`. If missing, add it. If Jina is on free tier, upgrade or switch to Brave Search API (key already exists in outreach-agent).

### Bug 4 — Agent Lost Address Context Mid-Conversation

**Symptom:** After multiple tool calls, agent said "I need more information about the address" despite the address being in the same session.

**Root cause:** `_build_report_context()` at `chat.py:303` only injects address context if a full `ZoningReport` is attached to the session. In chat, if user only ran individual tool calls (not `/analyze`), no ZoningReport is set → context is empty → agent forgets the address.

**Fix:** After `geocode_address` + `lookup_property_info` succeed, persist `property_address` and `municipality` into a session-level dict that gets injected into the system prompt on every subsequent turn. The `_SessionCache` class at `chat.py:~186` needs a new `set_address_context()` / `get_address_context()` method.

### Bug 5 — "What Can I Build" Repeated Setback Info

**Symptom:** Agent copy-pasted setback response instead of listing permitted use types.

**Root cause:** "What can I build" has similar embedding to prior setback query → same top-15 chunks retrieved → agent summarizes same content again.

**Fix:** Update `AGENT_SYSTEM_PROMPT` to instruct agent to reformulate queries for `search_zoning_ordinance` based on the intent — use "permitted uses allowed uses conditional uses RM-3-7" for use-type questions, not the user's literal question.

**Fix Priority:** Bug 2 → Bug 3 → Bug 1 → Bug 4 → Bug 5

---

## Dead Ends — Building Permit / Developer Prospect Scraper

Phat asked to scrape CA open data building permit portals to find developer/investor names. Spent significant time investigating. Here is the complete findings so the next agent does not repeat these failures:

### What Was Tried and Failed

| Source | What Happened |
|--------|--------------|
| Socrata Discovery API (`api.us.socrata.com`) | Returns datasets from random other cities due to federation. Oakland's catalog returned Orlando and Chicago datasets. |
| Direct city Socrata catalogs (`data.oaklandca.gov/api/catalog/v1`) | Same problem — federated datasets from other cities appear. Dataset IDs from the catalog return 404 when queried on the city's own domain. |
| Known Socrata dataset IDs | All return 404. Datasets were moved or removed. |
| ArcGIS county parcel layers | Most CA counties do NOT expose owner names. Verified field-by-field: Alameda, San Mateo, Santa Clara, San Diego parcel layers have no owner name field. Contra Costa and Sacramento DO have owner fields, but the Contra Costa service URL in the codebase was pointing to Kansas data (wrong ArcGIS org). |
| CSLB contractor portal | Website accessible but no REST API; form-based search returns 404. |

### What the Current Permit Scraper Files Do

The files created (`permit_scraper.py`, `permit_prospect_finder.py`, `permits.py`) implement:
- County parcel layer querying via ArcGIS
- Repeat-owner detection (2+ parcels = developer signal)
- SQLite dedup + insert
- Unit tests (pass)

But the live data doesn't return results because the ArcGIS layer field discovery correctly identifies no owner field for most counties.

### What Actually Works — Recommended Next Step

**CEQA Clearinghouse** (`ceqanet.opr.ca.gov`) is the best free confirmed-accessible source:
- All California development projects above a threshold file CEQA notices
- Contains: applicant name, company, project address, city, description
- Covers all our CA municipalities
- Has a working web interface; API status needs verification
- These are exactly the developers Phat wants — people filing entitlements for new construction (multifamily, ADU projects, commercial)

**Secondary option:** City-specific permit portals (web scrape with Playwright):
- Oakland: `ebis.oaklandnet.com`
- San Jose: `eplan.sanjoseca.gov`
These have UIs with permit data but no REST API.

**Do NOT re-attempt** Socrata or ArcGIS parcel owner scraping without first verifying a specific dataset ID works end-to-end.

---

## Business Context

### Kevin Woo — First San Diego Paying Prospect

- Connected on LinkedIn
- Requested analysis for **1233 Hueneme St, San Diego CA 92110** (RM-3-7 zone, Linda Vista area)
- San Diego is fully ingested (2,910 chunks)
- **Action needed before demo:** Fix Bugs 1–4 above so chat gives correct answers
- **Pricing:** $150/month founding rate. If he asks about other customers: "You're my first in San Diego — giving you a founding rate."
- **Message to send now:** "Just added San Diego — try 1233 Hueneme St at plotlot.app"

### LinkedIn — New Connections (Need Intro Messages Drafted)

These people accepted connection requests. No follow-up sent yet. Draft warm LinkedIn intro: no URL, close with `Regards,\nPhat`, under 300 words, peer-to-peer tone.

- **Jillian D'Onfro** — Bay Area tech/real estate reporter (SF Standard). Angle: PropTech story about AI land analysis tool. Not a sales pitch — position PlotLot as story-worthy.
- **Kevin Woo** — Real estate developer/investor. Already active (see above).
- **Jeremy** (last name unclear, "Jeremy Monty's" in notes) — context unknown. General warm intro: PlotLot helps developers underwrite land deals faster, offer to stress-test on a deal he's already looked at.

### Other Active Prospects (awaiting reply)

- **Brian Saliman** — Facebook message sent (Saliman Investments, residential developer)
- **Keith Manson** — Email sent to keithmanson@gmail.com
- **Biz Carson** — Email sent to bizcarson@gmail.com (reporter)
- **Kevin Truong** — Email sent to kevin@sfstandard.com (Vietnamese-American reporter — shared heritage angle used)

---

## Outreach Agent — Key Rules (Do Not Revert)

- **Sign-off:** All emails/messages close with `Regards,\nPhat` (not `— Earl`)
- **No demo URL in cold pitches.** Share URL only after prospect replies with interest.
- **CoStar is permanently excluded** from all outreach.
- **LinkedIn notes** are drafted by agent but sent manually by Phat (4–5/day to avoid spam detection).
- Outreach agent source files are in `outreach-agent/src/outreach/` — the `.py` source files exist (compiled `.pyc` in `__pycache__`). Do NOT commit `credentials.json`, `token.json`, or `outreach.db`.

---

## Git State

- **Current working branch:** `Phat`
- **Committed and pushed to Phat:** San Diego scraper, chunker fix, CLI flag, SOCAL_METROS, ruff fixes, CLAUDE.md + AGENTS.md updates, `.claude/settings.json` permissions + `.gitignore` update
- **Outreach-agent:** Lives in `outreach-agent/` directory, untracked on Phat branch — keep it that way
- **Never commit:** `credentials.json`, `token.json`, `.env`, `outreach.db`

---

## Key File Locations

| What | Path |
|------|------|
| San Diego scraper | `plotlot/src/plotlot/ingestion/san_diego_scraper.py` |
| Chat tool handlers | `plotlot/src/plotlot/api/chat.py` |
| `_execute_municode_live_search` (Bug 2) | `chat.py:1281` |
| `_execute_zoning_search` | `chat.py:1236` |
| `_execute_web_search` (Bug 3) | `chat.py:1401` |
| Session cache class (Bug 4) | `chat.py:~186` (`_SessionCache`) |
| System prompt injection (Bug 4) | `chat.py:~1884` |
| Hybrid search RRF SQL (Bug 1) | `plotlot/src/plotlot/retrieval/search.py:~80` |
| Billing logic | `plotlot/src/plotlot/api/billing.py` |
| Permit scraper (partial) | `outreach-agent/src/outreach/tools/permit_scraper.py` |
| Permit finder agent (partial) | `outreach-agent/src/outreach/agents/permit_prospect_finder.py` |
| Permit CLI | `outreach-agent/permits.py` |

---

## Quick Commands

```bash
# Backend
cd plotlot && uv run uvicorn plotlot.api.main:app --reload --port 8000

# Frontend
cd plotlot/frontend && npm run dev

# Re-run San Diego ingestion
cd plotlot && uv run plotlot-ingest --san-diego

# Lint / format (must pass before push)
cd plotlot && uv run ruff check src/ tests/
cd plotlot && uv run ruff format src/ tests/

# Tests
cd plotlot && uv run pytest tests/unit/ -v

# Permit scraper (partial, see Dead Ends)
cd outreach-agent && uv run python permits.py
cd outreach-agent && uv run python permits.py --cities Richmond "Citrus Heights"
```

---

## Rules (Never Violate)

1. Every code change ships with tests.
2. No Co-Authored-By trailers. Commits under Earl Perry git name only.
3. Never commit `credentials.json`, `token.json`, or `.env`.
4. CoStar is excluded from all outreach permanently.
5. No demo URL in cold pitches — share only after prospect replies with interest.
6. Ruff lint + format must pass before any push.
7. San Diego uses the custom PDF pipeline, NOT Municode API.
8. `search_municode_live` will always return nothing for San Diego — this is Bug 2 above, fix it before demoing.
9. Do NOT re-attempt Socrata or ArcGIS parcel owner scraping without first verifying a specific dataset ID works end-to-end in a test script.
10. The next developer prospect scraper to build should target **CEQA Clearinghouse** (`ceqanet.opr.ca.gov`).
