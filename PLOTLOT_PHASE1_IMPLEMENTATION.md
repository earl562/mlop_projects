# PlotLot — Session Handoff: Un‑Ingested‑Address Coverage & Anti‑Hallucination

**Date:** 2026‑06‑10
**Branches touched:** `Phat` (working) → also pushed to `dev`
**Status:** Hallucination bug FIXED and shipped. Generic "analyzations for any county" coverage is partially solved (auto‑ingest for Municode/PDF cities) and BLOCKED for non‑Municode cities pending a decision (see §8).

> **Read this first if you are a new session.** This document is the full context of one working session. It captures what we shipped, what we tried and abandoned, the two deep architectural insights we uncovered, and the exact decisions left open. Pair it with the repo's `CLAUDE.md` (monorepo overview) and `plotlot/CLAUDE.md` (project overview). Everything below is specific to *this* session's work.

---

## 0. The one‑paragraph summary

A user tested PlotLot with **2975 Montessouri St, Las Vegas, NV 89117** — an address in a county we have **not ingested** — to see whether the MCP + ACP pipeline could do a full analysis. It could retrieve the **zoning code** (RS20) but not the **analyzations** (setbacks, density, max units), and the agent **hallucinated** a "could not be retrieved" message with a **fabricated phone number**. We diagnosed that the failure had three layers (wrong search path, no anti‑hallucination contract, and a duplicated bug), fixed all three, and then went deep on *why* un‑ingested addresses can't be analyzed generically. Two root causes emerged: **(1) jurisdiction resolution** (mailing city ≠ zoning authority) and **(2) a GIS‑code ↔ ordinance‑code vocabulary gap** ("RS20" in the map vs "R‑E" in the code book). Those two fixes — plus a web‑research coverage tier — are the remaining work, gated on one infra question (is `JINA_API_KEY` set on Render?).

---

## 1. The two‑track mental model (internalize this)

PlotLot answers "what can I build here?" by joining **two independent data tracks**:

```
TRACK 1 — WHERE + WHICH CODE          TRACK 2 — THE RULES
(ArcGIS GIS layers, per county)       (ordinance text → RAG over pgvector)
parcel: APN, lot size, geometry       setbacks, density, height, lot coverage
zoning code: "RS20" / "R-E"           the dimensional-standards TABLE
        │                                      │
        └────────────► calculator ◄────────────┘
             pipeline/calculator.py
       max units + buildable envelope (deterministic)
```

- **Track 1 = ArcGIS** (county GIS / `property/` providers + `hub_discovery.py`). Tells you the parcel and its **zoning code**. Has nothing to do with Municode.
- **Track 2 = Municode / PDF / American Legal** ingested into pgvector. Tells you the **rules** for that code. Has no idea where your parcel is.
- **Common misconception to avoid:** *Municode does NOT give the zoning code.* It is the code book (the rules). The code comes from ArcGIS.
- A full analysis needs **both** tracks + the **code crosswalk** that makes Track‑1's code match Track‑2's text.

**Ingestion source decision tree (Track 2):**
- On Municode? → `MunicodeAdapter` (the normal path; 30+ cities use it). `uv run plotlot-ingest --municipality "X" --state YY`.
- Not on Municode but publishes PDFs? → San‑Diego‑style `PDFAdapter` (the *exception*, not the template).
- On American Legal (`codelibrary.amlegal.com`)? → **blocked by Cloudflare** (see §6). Needs the web tier.

**How the "NorCal pipeline" works (asked this session):** it is NOT special architecture. `ingestion/discovery.py` holds `NORCAL_METROS` (6 counties → curated city lists) and `SOCAL_METROS`. `discover_ca()` → `_discover_state("CA", NORCAL_METROS)` runs **Municode discovery** per city → standard MunicodeAdapter ingest (scrape→chunk→embed→pgvector). Track‑1 property data for those cities = `CaliforniaProvider` (county ArcGIS parcel layers + CA statewide parcel layer), registered for santa clara, alameda, contra costa, san mateo, sacramento, san diego in `property/__init__.py`. San Jose "works" because it was on the curated list and got ingested; Las Vegas never was.

---

## 2. The bug we were asked to fix

**Symptom (verbatim from the user's agent output, first version):**
> "The zoning code for 2975 Montessouri St… could not be retrieved through standard tools. … Contact Clark County Zoning Division at **(702) 455‑5860**…"

The phone number was **fabricated**, and the claim "could not be retrieved" was **false** — the zoning code (RS20) *was* retrieved. The user wants: a **generic** agent that retrieves zoning **and** analyzations for **any** un‑ingested US address, **with no hallucinations**.

**Root‑cause diagnosis (3 distinct defects):**

| # | Defect | Where |
|---|--------|-------|
| 1 | The MCP `run_full_analysis` → `lookup_address` path **never invoked the ACP** auto‑ingestion. Only the web `/analyze` route did. So un‑indexed cities got zero ordinance text → no standards. | `pipeline/lookup.py`, `api/routes.py:286` |
| 2 | **No anti‑hallucination contract.** The tool returned `zoning_district="RS20"` plus nulls and *no instructions*, so the LLM invented a polished dead‑end with a fake phone number. | `mcp/server.py`, `api/chat.py` |
| 3 | **Duplicated San Jose bug.** `routes.py:277` still used `else municipality` as the search query (returns 0 results); the fix existed only in `lookup.py`. | `api/routes.py` |

**Critical realization mid‑session:** the user's agent is the **agentic chat** (`api/chat.py`), *not* the MCP server. The chat calls `lookup_property_info` + `search_zoning_ordinance` as **separate tools** and never calls `lookup_address`. So the first round of fixes (MCP path) did not reach the surface the user was testing — we then fixed the chat path too.

---

## 3. What we SHIPPED this session (all on `Phat` + `dev`)

### 3.1 Completed Options 2 & 3 in ArcGIS discovery — `property/hub_discovery.py`
- `_probe_arcgis_server()` — crawls any ArcGIS REST tree (root → relevant folders → MapServer/FeatureServer → layers), scores with `_score_dataset()`, validates coverage with `_has_coverage()`.
- `_search_state_servers()` (**Option 2**) — probes known state‑level ArcGIS servers from `_STATE_SERVERS` (NC `nconemap.gov`, FL DEP, WA King County, PA DOT).
- `_probe_county_url_patterns()` (**Option 3**) — generates county slugs and probes 16 `_COUNTY_URL_PATTERNS`; concurrent HEAD probe → live servers → `_probe_arcgis_server`.
- `discover_datasets()` now cascades **Hub → state servers → URL patterns**.
- Tests: `tests/unit/test_hub_discovery_fallbacks.py` (9), `test_hub_discovery_state.py` (state‑abbrev expansion `_expand_state` "NV"→"nevada").

### 3.2 Self‑healing coverage (auto‑ingest) — `pipeline/lookup.py`
- New constants: `GENERIC_ZONING_QUERY` (shared with `routes.py`, kills the San Jose bug in both), `_AUTOINGEST_TTL = 86400`, `_autoingest_attempts`.
- New `_run_hybrid_search()` and `_gather_ordinance_sections(municipality, state, county, query) -> (results, coverage_status)`.
  - On a search **miss**, calls the **ACP** `run_on_demand_ingestion(IngestRequest(...))`, then re‑searches.
  - `coverage_status ∈ {"indexed", "auto_ingested", "ingest_empty", "uncovered"}`.
  - 24h per‑place TTL guard so a dead source (city not on Municode) isn't re‑hammered.
  - Degrades **honestly** — never raises; caller still has the ArcGIS zoning code.
- Wired into `lookup_address` Step 3; logs `coverage_status` to MLflow params.
- Tests: `tests/unit/test_lookup_autoingest.py` (5).

### 3.3 Anti‑hallucination contract — `mcp/server.py`
- `run_full_analysis` now returns a **`data_status`** block (`coverage: full | zoning_only | none`, plus `zoning_district_found`, `dimensional_standards_found`, `ordinance_text_indexed`, `max_units_computed`) and a **`presentation_guidance`** string that tells the agent to state the retrieved zoning plainly, never claim "could not be retrieved" when a code exists, offer `ingest_municipality`, and **never fabricate phone numbers/URLs/values**.
- FastMCP `instructions` hardened with explicit GROUNDING RULES. Version bumped `2.0.0 → 2.1.0`.
- Tests added to `tests/unit/test_mcp_server.py` (full/zoning_only/none coverage + version + instructions).

### 3.4 Anti‑hallucination on the chat path — `api/chat.py` + `observability/prompts.py`
- `chat_agent` prompt **v6 → v7** (`CHAT_AGENT_PROMPT_V2`): two new grounding rules — (a) never invent phone numbers/emails/URLs; only provide a contact/link that appears verbatim in a tool result; (b) if `lookup_property_info` returned a `zoning_code`, never say the zoning "could not be retrieved" — state it, then say standards aren't indexed and offer to ingest.
- `_execute_zoning_search(municipality, query, session_id="")` — on `no_results`, echoes the session's known `zoning_code` (from property context) and returns `presentation_guidance` banning fabrication. Dispatcher threads `session_id`.
- Tests: `tests/unit/test_chat_live_tools.py` (+3), `test_grounding_rules.py` (+2, version→v7), `test_hybrid_search.py` (version→v7).

### 3.5 Routes consistency — `api/routes.py`
- Replaced the `else municipality` search‑query fallback with the shared `GENERIC_ZONING_QUERY` import.

### 3.6 Earlier in the session (also shipped)
- `ClarkCountyNVProvider` (`property/clark_county_nv.py`) registered under `"clark"` — returns APN, lot size, and zoning via spatial queries. **This is what makes RS20 retrievable.**
- State abbreviation fix + config `hub_discovery_timeout 10→20`.

**Commits (chronological):** `23118f5` (Options 2&3 + Clark provider + San Jose), `609483f` (unused pytest imports), `c8091db` (ruff format), `229d877` (mypy `_get_json` typing), `923376d` (self‑healing + MCP contract + routes fix), `8f5204a` (chat anti‑hallucination v7).

**Verification result (live, end‑to‑end):** `run_full_analysis("2975 Montessouri St…")` now returns `zoning_district="RS20"`, `data_status.coverage="zoning_only"`, and honest `presentation_guidance` — **no fabrication**. The user re‑tested the chat and confirmed the new output states RS20 correctly and **no longer invents a phone number** (it now offers a web search instead).

---

## 4. Test status

- **1178 passing.** New tests this session: ~14.
- **5 pre‑existing failures, unrelated to our work, Windows‑only:**
  - `test_health.py::test_health_degraded_on_db_failure`
  - `test_status_scripts.py::*` (4) — they `subprocess.run` shell scripts that don't exist on Windows → `FileNotFoundError: [WinError 2]`.
  - These were red **before** this session started. Do not chase them on Windows.
- Lint (`ruff check` + `ruff format`) and `mypy` clean on all touched files.

---

## 5. The DEEP diagnosis — the real generic problems (NOT yet built)

After the hallucination fix, the user pushed on the actual goal: *full analyzations for any un‑ingested address*. We did a manual, source‑level investigation and found **two** generic root causes. **These are the highest‑value remaining work.**

### 5.1 Jurisdiction resolution (mailing city ≠ zoning authority)
- "Las Vegas, NV 89117" is just the **USPS mailing city**. The parcel is in **unincorporated Clark County** — proven spatially: the **City of Las Vegas** zoning layer (MapServer/**7**) returns **0 features**, the **Clark County** layer (MapServer/**11**) returns **RS20**.
- The reliable signal is **which zoning layer returns a polygon at the parcel point**, *not* a city‑vs‑county guess.
- **Concrete bug:** `ClarkCountyNVProvider` hardcodes `record.municipality = "Las Vegas"` even when the **county** layer matched. The pipeline then ingests/searches under "Las Vegas" (not on Municode) instead of "Clark County" (on Municode).
- **Generalization (honest):** "route to county" is correct for the **largest bucket** (unincorporated land in county‑zoning states: most of West/South/Midwest, Hawaii, consolidated city‑counties) but **breaks** in **township‑zoning states** (NJ, PA, much of NY/OH/MI/IL, New England — the *town* zones, not the county) and **enclave/misleading‑mail‑city** cases. The correct rule is **spatial jurisdiction resolution**; county‑routing falls out as the unincorporated case.

### 5.2 GIS‑code ↔ ordinance‑code crosswalk (the vocabulary gap)
- The GIS layer reports **`RS20`** ("Residential Single‑Family 20"). **"RS" is NOT a Clark County ordinance code** — the user confirmed it in the Title 30 "Zoning Districts and Map" chapter. The real single‑family districts are **R‑U, R‑A, R‑E, R‑D, R‑1, R‑T, R‑2, RUD, R‑3, R‑4, R‑5**.
- `RS20` maps to **R‑E** ("rural estates residential district") — the **only** single‑family district with a **20,000 sqft** minimum lot (R‑U=80k, R‑A=40k, **R‑E=20k**, R‑D=10k). Lot‑area is the anchor that proves the mapping.
- **Consequence:** even after we ingest Clark County Title 30, a hybrid search for `"RS20"` will **never** match the `"R‑E"` text (no lexical overlap). The agent needs a **code crosswalk** (normalize GIS code → ordinance district code) **before** it searches. This is a **nationwide** problem (GIS codes routinely differ from ordinance codes — normalized labels, abbreviations, old‑vs‑new codes).

---

## 6. Trials & errors / dead ends (so you don't repeat them)

- **American Legal Publishing (`codelibrary.amlegal.com`) is Cloudflare‑walled.** Direct `httpx` → 403 "Just a moment…". **Jina Reader free tier** (`r.jina.ai`) → also 403 CAPTCHA. So a clean American‑Legal scraper (the convention every other adapter follows) is **not viable**. The *City* of Las Vegas Title 19 lives here — that's why the city code can't be auto‑ingested. (A **paid** Jina Reader usually renders through Cloudflare — unverified, see §8.)
- **No web key locally.** `settings.jina_api_key` is **empty**. The `BRAVE_API_KEY` in `.env` belongs to **outreach‑agent**, not loaded into PlotLot settings. So no web search/reader could be verified locally.
- **Auto‑ingest in the chat tool would risk Render's 30s proxy timeout** — the chat tool loop has **no heartbeat** during tool execution, and ingestion (embedding hundreds of chunks) can take minutes. So we deliberately kept heavy auto‑ingest in the **`/analyze` SSE pipeline** (which streams `ingestion_progress`) and `lookup_address`, NOT in the chat tool. The chat tool only does anti‑hallucination + offer‑to‑ingest.
- **Parcel layer intermittency:** `Assessor/LandApp/MapServer/9` occasionally returns 0 features on a cold query; retries return APN reliably. Don't over‑react to a single empty parcel response.
- **`uv run python /tmp/x.py` needs the project cwd** — run `cd /d/mlop_clone/mlop_projects/plotlot && uv run …` or the venv isn't found (`ModuleNotFoundError: httpx`).
- **PowerShell here‑strings break mid‑pipeline** in this harness — use multiple `-m` flags for multi‑paragraph commit messages; a lint fix once landed on the wrong local branch (`dev`) and had to be cherry‑picked onto `Phat`.

---

## 7. Verified facts & data (Las Vegas test case)

**Address:** 2975 Montessouri St, Las Vegas, NV 89117
**Geocodio (rooftop, accuracy 1):** lat **36.135181**, lng **‑115.248308**, county "Clark", state "NV", municipality "Las Vegas".

**Clark County ArcGIS endpoints** (`maps.clarkcountynv.gov/arcgis/rest/services`):
- Parcels (APN + acreage): `Assessor/LandApp/MapServer/9`
- City of Las Vegas zoning: `OpenData/PlanningandZoning/MapServer/7` → **0 features here** (not in city)
- Clark County zoning: `OpenData/PlanningandZoning/MapServer/11` → **ZNCLASS="RS20", Description="Residential Single-Family 20"**
- Spatial query params: `geometry=lng,lat`, `geometryType=esriGeometryPoint`, `inSR=4326`, `spatialRel=esriSpatialRelIntersects`, `f=json`.
- Public one‑stop viewer the user used: `https://maps.clarkcountynv.gov/ow/`

**Parcel:** APN **163‑10‑701‑007**, **0.54 acres = 23,522.4 sqft**, irregular **10‑vertex cul‑de‑sac** polygon, bbox ≈ **152 ft (E‑W) × 160 ft (N‑S)**, frontage ≈ **104 ft**.

**RS20 = R‑E** standards (Title 30, **Table 30.40‑1 "Rural Residential Districts"**, R‑E column):
| Standard | R‑E value |
|---|---|
| Dwelling density | 2 du / gross acre |
| Min lot area (net) | 20,000 (18,000) sqft |
| Lot coverage | 50% |
| Front setback | 40 ft |
| Interior side | 10 ft (principal) |
| Side‑street (corner) | 15 ft |
| Rear setback | 30 ft (principal; −10 ft if access only from collector/arterial) |
| Max height | 35 ft (principal), 25 ft (accessory) |

**Manual calculation (taught + worked through with the user):**
- **Max units = 1** (single‑family; `0.54 ac × 2 du/ac = 1.08 → 1`; lot < 2× min so unsplittable; +1 only if an ADU is permitted).
- **Coverage‑cap footprint** `F_cov = 0.50 × 23,522 = 11,761 sqft`.
- **Setback envelope** (rectangular bbox approximation, upper bound) `F_env = (152 − 2×10) × (160 − 40 − 30) = 132 × 90 = 11,880 sqft`. (True value lower due to irregular lot.)
- **Governing footprint** ≈ **11,761 sqft** (coverage ≈ setbacks).
- **Stories:** the code caps **height at 35 ft**, *not* a story count → **2 stories typical**, up to 3 if floors are short (unless Chapter 30.56 states a story max).
- **Max floor area (GLA)** ≈ `11,761 × 2 ≈ 23,500 sqft` at 2 stories.
- **Calculator mapping:** this is exactly `pipeline/calculator.py`'s `calculate_max_units` (density/min‑lot/FAR/buildable‑envelope, final = min) + buildable‑envelope/GLA logic.

**Ingestion routing facts:**
- "Clark County, NV" **IS on Municode** (`library.municode.com/nv/clark_county`; discovery: client=11836, product=16214, job=484650). → its Title 30 IS auto‑ingestable; the blocker is that the pipeline searched under "Las Vegas", not "Clark County".
- "Las Vegas, NV" (the **city**) is **not** on Municode → `resolve_adapter` raises `NoAdapterError`; its Title 19 is on American Legal (Cloudflare).

---

## 8. OPEN DECISIONS / what's pending (start here)

1. **User chose "Both (tiered)" for coverage** (American Legal adapter + generic web‑research tier) — *before* we discovered American Legal is Cloudflare‑walled. Plan pivoted.
2. **User is checking `JINA_API_KEY` on the Render backend** and will report whether it's **paid / free / not set**. The web‑tier build is gated on this:
   - **Paid** → build `retrieval/web_research.py` (`web_search` via `s.jina.ai`, `read_url` via `r.jina.ai`) + constrained LLM extraction (`NumericZoningParams` only from retrieved text, per‑value source URL, `confidence="unofficial — web‑sourced, verify"`), wired into `lookup_address` as a **Tier‑3 fallback** when `coverage_status ∈ {ingest_empty, uncovered}` and no numeric params. Paid Jina Reader also reaches American Legal → subsumes Tier 2.
   - **Free** → same build, but Cloudflare publishers (American Legal) may still CAPTCHA; works for non‑CF sources.
   - **Not set** → web tier can't run in prod; revisit (add a key, or rely on PDF/jurisdiction routing).
3. **Key‑independent builds offered, not yet started (recommended, do these regardless):**
   - **(a) Surgical jurisdiction fix:** make `ClarkCountyNVProvider` label `municipality` by the matching layer ("Las Vegas" when layer 7 hits, "Clark County" when layer 11 hits). With auto‑ingest already in place, this should yield **full RS20→R‑E analyzations today** (Clark County is on Municode), no key, no Cloudflare. **Highest‑ROI next step** — but pair with (c) or the search will still miss.
   - **(b) General jurisdiction resolution:** lift (a) into a spatial `jurisdiction` resolution in the provider/pipeline so any county benefits; county‑routing as the unincorporated fallback. Mind township‑state exceptions.
   - **(c) GIS‑code → ordinance‑code crosswalk:** normalize the GIS code (e.g., `RS20`) to the ordinance district (`R‑E`) before hybrid search, else ingested text never matches. Needed for (a)/(b) to actually return standards.
4. The user explicitly said **do NOT** pursue a Las‑Vegas‑specific PDF probe; the goal is the **generic** agent. Las Vegas is only the test probe.

---

## 9. Persistent project constraints (do not violate)

- **Git:** commits under **Earl Perry**'s name only; **no `Co-Authored-By` trailers**. Branch `Phat` is the working branch; also mirror to `dev`. `main` auto‑deploys to Render + Vercel.
- **Never commit** `credentials.json`, `token.json`, `.env`, `*.db`.
- **Outreach‑agent (separate project):** never add CoStar; no demo URL in cold pitches; messages close with `Regards,\nPhat`.
- **Code standards:** Python 3.12+, async‑first (`httpx.AsyncClient`), Pydantic everywhere, no `print()`, ruff + mypy must pass, every change ships with tests (mock external services).
- **The user is Phat** (persona files say "Earl Perry" — that's the portfolio persona). Action over talk; ship then explain; be honest about uncertainty.

---

## 10. Suggested next action for the new session

- If the user has reported the `JINA_API_KEY` tier → start the web‑research tier per §8.2.
- If not → build **§8.3(a) + §8.3(c) together** (Clark provider jurisdiction labeling + GIS‑code→ordinance crosswalk). With the auto‑ingest already shipped, that should make the Las Vegas test address return **real R‑E standards and max‑units** with zero new infra — then re‑verify end‑to‑end and ship with tests.
- Always: branch `Phat`, mirror `dev`, no Co‑Authored‑By, run `ruff` / `mypy` / `pytest tests/unit` before pushing. Live‑probe scripts go in `/tmp` and run via `cd /d/mlop_clone/mlop_projects/plotlot && uv run python /tmp/x.py`.
