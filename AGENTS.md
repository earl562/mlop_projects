# EP Engineering Lab — Agent Handoff Document

> **This file is the source of truth for new agents picking up this codebase.**
> Read it top to bottom before touching any code. It contains diagnosed bugs, session history, and exact next steps.

---

## Current User Direction (September 7, 2026)

- Work on `cpt-pro`. Launch targets are Miami-Dade, Broward, Palm Beach and Lee
  counties in Florida, plus Mecklenburg and Gaston counties in North Carolina.
  San Diego is deferred; preserve its existing code, data and evidence.
- Make small, reviewed checkpoint commits as work is completed and verified, and
  push those commits to this project's GitHub development branch. The user has
  explicitly authorized this as the standard; it supersedes earlier no-commit and
  no-push instructions in historical production-readiness notes.
- Inspect and stage exact paths or hunks. Keep implementation with its direct
  tests; exclude secrets, generated diagnostics and unrelated/pre-existing work.
  Do not use blanket staging to make a mixed dirty tree look clean.
- Verify the branch, remote, staged content and relevant checks before each push.
  Report checkpoint hashes, GitHub/CI status, and remaining uncommitted work.
  A checkpoint is not a production-readiness or deployment claim.
- No force-push, history rewriting, merge to `main`, deployment or production
  database migration without separate explicit authorization. Keep Earl Perry's
  configured authorship and do not add Co-Authored-By trailers.
- Reliable real-property results remain the priority before sign-in configuration.
  The dated handoff sections below are history, not current release evidence.

---

## Who You Are Working With

**User:** Phat (Vietnamese-American, based in Bay Area/San Diego market)
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

## What We Built This Session

### 1. San Diego Ingestion Pipeline (DONE — committed, pushed to `Phat` branch)

San Diego is NOT on Municode. Built a custom PDF scraper for `docs.sandiego.gov`.

**Files created/modified:**
- `plotlot/src/plotlot/ingestion/san_diego_scraper.py` — PDF scraper targeting Ch11–Ch15
- `plotlot/src/plotlot/pipeline/ingest.py` — added `ingest_san_diego()` function
- `plotlot/src/plotlot/cli.py` — added `--san-diego` CLI flag
- `plotlot/src/plotlot/ingestion/discovery.py` — added `SOCAL_METROS` dict

**Critical bug found and fixed during this session:**
PDF text from `docs.sandiego.gov` uses single `\n` between lines, NOT `\n\n`. The paragraph-based chunker (`re.split(r"\n{2,}", text)`) treated entire 143k-char PDFs as one paragraph → one chunk. Fixed by detecting double-newline absence and falling back to single-newline splitting. Result: **226 chunks → 2,910 chunks** for San Diego.

**Current chunk counts (as of 2026-05-28):**
San Diego: 2,910 | Miami-Dade: 2,666 | Oakland: 2,399 | Hayward: 2,537 | Boca Raton: 1,538 | (30+ other municipalities)

**To re-run ingestion:** `cd plotlot && uv run plotlot-ingest --san-diego`

### 2. Outreach Agent (DONE — on `outreach-agent` branch, NOT on `Phat`)

Autonomous B2B outreach: Brave Search → Hunter.io enrichment → Gmail API send.

**Key rules (do not revert):**
- Sign-off: `Regards,\nPhat` (not `— Earl`)
- No demo URL in cold pitches — share URL only after prospect replies with interest
- CoStar is permanently excluded from all outreach
- LinkedIn notes are drafted by agent but sent manually by Phat (4–5/day)

### 3. Stripe Billing (ALREADY EXISTS — not built this session, discovered via audit)

Billing is fully wired up at `src/plotlot/api/billing.py`. Current hardcoded price: **$49/month** for Pro tier (5 analyses/month free, unlimited on Pro).

**To close Kevin Woo:** Create a 50% coupon in the Stripe dashboard → send him the billing page URL + promo code. Recommended charge: **$150/month** (founding San Diego rate, half of future $300 price).

**Missing:** Customer portal, coupon/discount system in-app, `STRIPE_*` env vars need to be set in Render.

---

## Active Bugs — DIAGNOSED, NOT YET FIXED

These bugs were observed in a live Kevin Woo chat session on PlotLot using **1233 Hueneme St, San Diego CA 92110**. Fix these before demoing to Kevin.

### Bug 1 — Wrong Density Answer (CRITICAL)

**Symptom:** Agent returned "1 dwelling unit per 4 acres" for RM-3-7 zone. This is wrong. RM-3-7 allows much higher density (~1 unit per 700 sq ft lot area).

**Root cause (fully traced):**

`hybrid_search` in `search.py:18` takes a `zone_code` parameter used as BOTH the keyword query (`plainto_tsquery(:query)`) AND the `zone_code = ANY(zone_codes)` metadata filter. When the chat agent calls `search_zoning_ordinance`, it passes the user's natural language question (e.g. `"density calculation"`) as the `query` arg — NOT the zone code "RM-3-7".

So `hybrid_search` receives:
- `municipality = "San Diego"`
- `zone_code = "density calculation"` ← user's question, not the zone

The keyword arm runs `plainto_tsquery('density calculation')` which matches any chunk with those words — including the **rural cluster alternative** section in Ch13 which uses "density" and "calculation" prominently and ranks highly. The `zone_code = ANY(zone_codes)` filter never fires because `"density calculation"` is never in the `zone_codes[]` array. The RRF fusion has no idea what zone it's searching for, so the wrong section wins.

**Two-part fix:**

**Part A — `src/plotlot/api/chat.py` system prompt / `_execute_zoning_search`:**
The agent must be instructed to always include the zone code in the search query. After `lookup_property_info` returns `zoning_code = "RM-3-7"`, the next `search_zoning_ordinance` call should use `"RM-3-7 density"` not just `"density"`. Update the system prompt instruction for how to construct `search_zoning_ordinance` queries: _"Always prefix the search query with the zone code obtained from lookup_property_info (e.g. 'RM-3-7 density dwelling units per lot area')."_

**Part B — `src/plotlot/retrieval/search.py` `_hybrid_rrf` function (line ~80):**
Add a zone-code boost to the RRF score for chunks where the zone code is in `zone_codes[]`. The `zone_codes` column is already populated — it's just not used as a ranking signal. SQL change inside the `fused` CTE:

```sql
-- Current (no boost):
COALESCE(1.0 / (:rrf_k + v.vrank), 0) +
COALESCE(1.0 / (:rrf_k + k.krank), 0) AS rrf_score

-- Fixed (zone-code boost):
COALESCE(1.0 / (:rrf_k + v.vrank), 0) +
COALESCE(1.0 / (:rrf_k + k.krank), 0) +
CASE WHEN :zone_code = ANY(COALESCE(v.zone_codes, k.zone_codes)) THEN 0.1 ELSE 0 END AS rrf_score
```

This ensures chunks that explicitly reference "RM-3-7" in their `zone_codes` metadata float above generic density provisions, even if the semantic and keyword scores are similar. The 0.1 boost is larger than most RRF score differences at the top of the ranking (~0.015 per rank position).

**Files to change:**
- `src/plotlot/retrieval/search.py` — `_hybrid_rrf` SQL query (~line 80)
- `src/plotlot/api/chat.py` — `AGENT_SYSTEM_PROMPT` query construction instructions

### Bug 2 — `search_municode_live` Returns Nothing for San Diego (CRITICAL)

**Symptom:** Chat log shows "search_municode_live returned no results" for San Diego queries.

**Root cause:** `_execute_municode_live_search()` in `chat.py:1281` calls `get_municode_configs()` which queries the Municode API to find a municipality's library. San Diego is **not on Municode** — it's served by our custom PDF pipeline. So `configs.get("san_diego")` returns `None` → the function immediately returns `no_results`.

**The agent then falls through to `web_search`**, which fails separately (see Bug 3).

**Fix needed:** Add a short-circuit in `_execute_municode_live_search()` that checks if municipality == "San Diego" (or more generally, if municipality is in our PDF-scraped list) and returns a message saying "use search_zoning_ordinance instead — this municipality uses local PDF index." Alternatively, suppress `search_municode_live` from the tool list when the current municipality is San Diego.

**File:** `src/plotlot/api/chat.py:1281` (`_execute_municode_live_search` function)

### Bug 3 — Web Search Fails with Payment Error

**Symptom:** "web_search failed due to a payment error"

**Root cause:** Web search uses Jina.ai (`_execute_web_search` at `chat.py:1401`). The `JINA_API_KEY` is either not set in Render env vars, or the Jina free tier is exhausted. Code returns error if `settings.jina_api_key` is falsy.

**Fix needed:** Verify `JINA_API_KEY` is set in Render environment. If Jina is on a paid tier, add the key. If not using Jina, switch to Brave Search API (already have `BRAVE_API_KEY` in outreach-agent).

**File:** `src/plotlot/api/chat.py:1401` (`_execute_web_search`)

### Bug 4 — Agent Lost Address Context Mid-Conversation

**Symptom:** When user asked "I want to extract all the legal documents and Pro Forma" (in the same session as 1233 Hueneme St), the agent responded "I need more information about the address."

**Root cause:** The session stores geocode and property data in `_SessionCache` (LRU dict). The `_build_report_context()` function at `chat.py:303` injects address/zoning info into the system prompt — but only if a `ZoningReport` is attached to the session. In the chat flow, after `lookup_property_info` succeeds, the report is stored. If the session's active report was not set (because the user never ran a full `/analyze` pipeline, only individual tool calls), the context is empty.

**Fix needed:** After `geocode_address` + `lookup_property_info` succeed in chat, explicitly persist `property_address` and `municipality` into a session-level dict that gets injected into the system prompt on every subsequent turn, regardless of whether a full ZoningReport exists.

**File:** `src/plotlot/api/chat.py` — `_SessionCache` class (~line 186) and the system prompt injection logic (~line 1884)

### Bug 5 — "What Can I Build" Repeated Setback Info Instead of Use Types

**Symptom:** Agent copy-pasted setback response instead of answering what use types are permitted.

**Root cause:** The query "What can I build on this lot?" generated the same embedding vector as the prior setback query (both relate to zoning standards), so the same top-15 chunks were retrieved again. The agent summarized those same chunks.

**Fix needed:** Query diversification — when the user's question is about use types/permitted uses, the search query should include terms like "permitted uses allowed uses conditional uses RM-3-7" rather than the user's natural language verbatim. The LLM should be prompted to reformulate the search query before calling `search_zoning_ordinance`.

**File:** `src/plotlot/api/chat.py` — the system prompt (`AGENT_SYSTEM_PROMPT`) instruction for how to construct `search_zoning_ordinance` queries.

---

## Fix Priority Order

1. **Bug 2** (search_municode_live short-circuit for San Diego) — easiest fix, unblocks Bug 3 cascade
2. **Bug 3** (JINA_API_KEY) — check Render env vars first, 5-minute fix if key is just missing
3. **Bug 1** (wrong density) — zone_codes metadata post-filter on hybrid search
4. **Bug 4** (address context loss) — session state persistence fix
5. **Bug 5** (query diversification) — system prompt update

---

## Business Context

### Kevin Woo — First San Diego Customer

- Connected on LinkedIn
- Requested analysis for **1233 Hueneme St, San Diego CA 92110** (RM-3-7 zone, Linda Vista area)
- San Diego is live (2,910 chunks)
- **Pricing decision:** Charge $150/month as founding San Diego rate (advisor suggested 50% of future $300 price)
- **Action needed:** Fix Bugs 1-4 above, then send Kevin: "Just added San Diego — try it at plotlot.app. Happy to set you up at a founding member rate."
- If he asks how many customers: "You're my first in San Diego — giving you a special founding rate"

### New LinkedIn Connections (Need Intro Messages Drafted)

These people accepted connection requests and are now 1st-degree. No follow-up sent yet. Draft warm intro messages: no URL, close `Regards,\nPhat`, under 300 words, peer-to-peer tone.

- **Jillian D'Onfro** — Bay Area tech/real estate reporter (SF Standard). Angle: PropTech story, not a sales pitch. Position PlotLot as a tool residential developers are using.
- **Jeremy** (last name unclear, may appear as "Jeremy Monty's") — context unknown. General warm intro: PlotLot helps developers underwrite land deals faster, offer to stress-test on a deal he's already looked at.

### Other Active Prospects (awaiting reply)

- **Brian Saliman** — Facebook message sent (Saliman Investments, residential developer)
- **Keith Manson** — Email sent to keithmanson@gmail.com
- **Biz Carson** — Email sent to bizcarson@gmail.com (reporter)
- **Kevin Truong** — Email sent to kevin@sfstandard.com (Vietnamese-American reporter, SF Standard — shared heritage angle used)

---

## Git State

- **Current branch:** `Phat`
- **Committed and pushed:** All San Diego ingestion work (scraper, chunker fix, CLI flag, discovery)
- **Outreach-agent:** Lives in `outreach-agent/` directory, untracked on Phat branch — should stay that way
- **Credentials that must never be committed:** `credentials.json`, `token.json`, `.env`

---

## Key File Locations

| What | Path |
|------|------|
| San Diego scraper | `plotlot/src/plotlot/ingestion/san_diego_scraper.py` |
| Chat tool handlers | `plotlot/src/plotlot/api/chat.py` |
| `_execute_municode_live_search` | `chat.py:1281` |
| `_execute_zoning_search` | `chat.py:1236` |
| `_execute_web_search` | `chat.py:1401` |
| Session cache class | `chat.py:~186` (`_SessionCache`) |
| System prompt injection | `chat.py:~1884` |
| Billing logic | `plotlot/src/plotlot/api/billing.py` |
| Hybrid search | `plotlot/src/plotlot/retrieval/search.py` |
| Outreach pitch writer | `outreach-agent/src/outreach/agents/pitch_writer.py` |
| Hunter domain dict | `outreach-agent/src/outreach/tools/hunter.py` |

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
8. `search_municode_live` will always return nothing for San Diego — this is a known bug (Bug 2 above).
