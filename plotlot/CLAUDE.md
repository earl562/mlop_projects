# PlotLot v2 — Session Handoff (Chat Grounding + Data Sources)

> Full handoff for a fresh agent. Read the **Guiding Principle** first — it governs
> everything. This session was about making the **agentic chat** trustworthy: it was
> hallucinating deal numbers because it bypassed the deterministic pipeline. We
> grounded it, fixed several bugs that surfaced along the way, and built two
> generalizable data-source registries. **Everything below is UNCOMMITTED and LOCAL.**

---

## 1. Project snapshot

**PlotLot v2** — AI land-deal intelligence. Address → geocode → parcel (ArcGIS) →
zoning ordinance search (pgvector hybrid) → agentic LLM extracts numeric zoning
params → **deterministic calculator** computes max buildable units → comps →
residual pro forma → SSE stream. Artifacts: streamed report, one-page Deal Paper
PDF, batch Buy Box screening, and an **agentic chat** (`api/chat.py`).

- **User:** Phat (persona docs say "Earl Perry" — portfolio persona). Values action,
  conciseness, honesty, accuracy, **no silent failures**.
- **Repo:** `d:\mlop_clone\mlop_projects` (git). Work in `plotlot/`. Branch `Phat`.
- **Git config user is "Phat Dang".** Do **not** modify git config. **No Co-Authored-By trailers.**
- **Stack:** FastAPI + Python 3.12 (async), Neon Postgres + pgvector, Next.js 16,
  NVIDIA NIM Llama / Claude / Kimi LLMs. Tooling: `uv`. Dev box: Windows + PowerShell
  (a Bash tool is also available).
- **San Diego is fully ingested** (~2,910 chunks via a custom PDF scraper).
- **Test parcel this whole session:** **1233 Hueneme St, San Diego, CA 92110**,
  zone **RM-3-7**, lot **6,470.61 sqft**. Correct by-right answer = **6 units**
  (RM-3-7 = 1 dwelling unit per 1,000 sqft of lot area, SDMC §131.0406(b)(3)).
  Neighborhood is **Morena** (NOT North Park — the chat hallucinated that).

---

## 2. THE GUIDING PRINCIPLE — anti-hallucination (read this)

PlotLot was previously burned by a hallucinated buildable-unit count. The doctrine:

1. **Math, statutory constants, tiers, citations stay deterministic.** Never let an
   LLM *produce* a number that is actually a fixed fact.
2. **The LLM only extracts/proposes from text; every number is verified** against the
   retrieved source before it's trusted.
3. **Fail loud, not silently wrong.** Unverified/contradicted values are **PROVISIONAL**,
   never confident firm numbers. The firm "base" number is never contaminated by a
   coarse/uncertain layer (bonuses, envelope estimates, regional defaults).
4. **Honesty about gaps.** Coarse estimates and unmodeled items are labeled as such —
   never fabricated to fill a hole. **Do not hardcode unverified data** ("relocating the
   hallucination into trusted code" is still a hallucination).

This session repeatedly applied this doctrine: to the chat agent, to the verifier, and
to the calculator.

---

## 3. The problem we started with

The user tested the **chat** (`POST /api/v1/chat`, SSE, session-based) with 12 deal
questions on 1233 Hueneme St and got hallucinations. **Root cause:** the chat agent's
tools were geocode / lookup / zoning-search / web-search / doc-gen — **none of the
deterministic numeric tools** (calculator, comps, proforma, site_risk, entitlement,
cost model). So it freelanced units, comps, fees, and risk from LLM general knowledge.

**Audited hallucinations (all wrong except the 6-unit base):**
- "RM-3-7 = 7 units/acre, 3 stories" — fabricated; the digits are NOT density.
- "North Park" neighborhood — wrong (it's Morena).
- Fabricated land comps ($250–400/sqft) and exit ($400–500/sqft).
- Broken pro forma (construction = lot_sqft × $/sf; circular residual).
- Hallucinated impact fees with fake categories ("police impact fee $8–18k").
- "Assuming Zone X" flood/coastal/wetlands (guessed; never called site_risk).
- "CUP to exceed density" (conceptually wrong).
- Suggested "ingest the SD ordinance" — **but SD is already ingested**.

**Primary-source verification:** fetched the actual SD Municipal Code PDF (Ch.13 Art.1
Div.4 §131.0406(b)(3)) → "RM-3-7 permits a maximum density of 1 dwelling unit for each
1,000 square feet of lot area" → **6 units is correct**. Notably the web-search AI
summary itself hallucinated "2,000 sqft/DU"; the primary source vindicated the golden
value. (Lesson: verify against primary sources, not LLM summaries.)

---

## 4. What we built / fixed this session (chronological)

All changes are **UNCOMMITTED** in the working tree.

### A. Grounded the chat agent (`analyze_property` tool)
- **`pipeline/analyze.py::analyze_property_deep(address)`** (NEW) — runs the full
  deterministic composition mirroring the SSE route, without streaming: geocode →
  property → zoning → LLM extraction → **verification** → density, then comps →
  residual proforma → sensitivity → entitlement → site_risk → CA density uplift. Each
  enrichment step is non-blocking.
- **`api/chat.py`** — new `analyze_property` chat tool: definition in `CHAT_TOOLS`,
  added to `CORE_TOOLS`, dispatch in `_execute_tool`, `_execute_analyze_property`
  executor, and `_format_grounded_analysis(report)` which renders a compact grounded
  payload with verification status, comps, residual, fees, risk, entitlement, CA upside,
  and a `grounding_note`.
- **`GROUNDING_POLICY`** constant appended to every chat system prompt — forbids
  emitting any zoning/financial/risk number that didn't come from a tool; forbids
  reading a zone name as density (e.g. "RM-3-7" ≠ 7 u/ac); requires PROVISIONAL labeling.

### B. Bug — `KeyError: 'gateway.execute'` (chat 500'd on the new tool)
- Every chat tool call is authorized through a governance gateway via
  `harness/tool_registry.get_tool_contract(name)`. The new tools had **no ToolContract**,
  so `contract=None` → the code fell into a broken `authorize("gateway.execute")` path →
  `KeyError('gateway.execute')`.
- **Fix:** registered contracts in `harness/tool_registry.py` — `analyze_property`
  (`READ_ONLY`, no approval prompt) and `screen_properties` (`EXPENSIVE_READ`, 50¢
  budget, under the default 100). Added guard test
  `test_every_chat_tool_has_a_harness_contract` (asserts EVERY chat tool has a contract —
  would have caught this at test time).

### C. Caveat features (also built)
- **`screen_properties`** batch buy-box chat tool — wraps `screening.screen_addresses` +
  `analyze_property_full`, capped at 20 addresses, ranks qualified deals by residual.
- **Coastal Prop D overlay moved into the shared path.** The `CoastalHeightOverlay`
  type + `pipeline/coastal_overlay.py` were added by a **concurrent deepseek session**
  (commit `09c7a6c "Added SD Proposition and fixed 12 critical bugs"`), but only wired
  into the SSE route. We wired `fetch_coastal_height_overlay` into
  `lookup.py::lookup_address` (the shared non-SSE path) so chat, JSON `/analyze`, and
  screening all apply the 30 ft cap consistently.

### D. Bug — model abandoned grounded data after turn 1
- On follow-ups (Q3–Q12) the model reverted to "I don't have your assumptions, here's a
  hypothetical" — even inventing a $100k residual while the real $444,900 sat in context.
- **Fix:** persist the grounded payload in the session
  (`SessionStore.set_analysis`/`get_analysis`) and inject an **"ACTIVE GROUNDED ANALYSIS"**
  block into the system prompt every turn via `_build_active_analysis_context(payload)`.
  Strengthened `GROUNDING_POLICY`: don't re-derive with hypotheticals, never suggest
  "ingesting" (SD already ingested), never invent alternative ordinance readings,
  PROVISIONAL ≠ missing data.

### E. Bug — PROVISIONAL instead of firm 6 (THE key fix)
- Diagnosed with a **live diagnostic** (`diag_sd_grounding.py`, THROWAWAY) run against
  Neon: ingestion fine (2,910 chunks), retrieval fine (the §131.0406 chunk ranks #1) —
  but **grounding was not zone-aware**. The §131.0406 chunk lists EVERY RM zone in one
  block (RM-1-1=3,000 … RM-3-7=1,000 … RM-3-9=600). `_ground` did `re.search` and grabbed
  the **first** density (a neighbor zone's value, e.g. 2,500), so the LLM's correct 1,000
  looked like a conflict → marked provisional.
- **Fix (`pipeline/extraction_verify.py`):** `_ground_for_zone(text, patterns, zone_code)`
  anchors the value to the **target zone code's own clause** (bounded by the next zone
  token via `_ZONE_TOKEN_RE`); falls back to global `_ground` when the code isn't present
  (single-zone chunks unchanged). `_verify_field` now takes `zone_code`. And
  `lookup.py` passes the **authoritative ArcGIS `zoning_code`** ("RM-3-7") into the
  verifier (not the LLM's free-text district).
- **Proven live:** diagnostic now prints `FIXED ✓` — zone-aware grounds RM-3-7 → 1,000,
  verifier marks it verified, `offer_is_provisional=False`. Regression tests use the real
  multi-zone text (`SD_RM_TABLE` in `test_extraction_verify.py`).

### F. Bug — 6→4 regression (introduced by our coastal wiring)
- After wiring coastal into `lookup_address`, the live answer dropped to **4 units**. The
  Prop D 30 ft cap fed the **buildable-envelope** constraint
  (`buildable_sqft × stories ÷ min_unit_size`), which computed 4 and *governed* below the
  verified 6 (the model couldn't explain it: "6.47 rounded down to 4").
- This is a **doctrine violation**: a coarse estimate (conservative story height +
  LLM-extracted `min_unit_size`) silently overriding a source-verified statutory number.
- **Fix (`pipeline/calculator.py`):** when density/min-lot-area is **source-verified**,
  floor-area-derived constraints (`buildable_envelope`, `floor_area_ratio`) **cannot
  govern below it** — if lower, the firm count stays and the squeeze becomes a feasibility
  warning ("confirm units fit the massing"). Gated on verification, so unverified behavior
  (envelope can govern) is preserved. Tests: `TestVerifiedEntitlementProtection` in
  `test_calculator.py`.

### G. Fee-itemization hallucination
- `cost_model.py` returns ONE coarse `$40,000` aggregate for SD ("school/park/traffic/
  utility combined"). The model decomposed it into fabricated line items (park/fire/
  **police** $8–18k — SD has no "police impact fee").
- **Fix:** `_format_grounded_analysis` labels `impact_fees_basis` as a coarse aggregate
  and adds `adv_basis` when ADV is a regional default (no comps). `GROUNDING_POLICY`
  forbids decomposing an aggregate — itemize **only** from a real `impact_fee_breakdown`.

### H. #1 + #2 — generalizable data-source registries
The user asked: "do we rebuild from scratch per city?" **Answer: no** — both are
registry patterns mirroring the parcel-provider registry (`property/california.py`
`_COUNTY_CONFIG`). Adding a market = one entry.

- **#1 Comps source registry (`pipeline/comps_sources.py`, NEW):** curated
  `(state,county) → SalesSource` (an ArcGIS layer `layer_url`+`fields`, OR a pluggable
  async `provider` for paid APIs). `resolve_sales_dataset(...)` is tried **before** the
  generic ArcGIS-Hub keyword discovery (the fallback). Wired into `comps.find_comparables`.
  `register_sales_source` / `get_sales_source`.
- **#1 bug fix:** `mcp/server.py::get_comparable_sales` hardcoded `county=""` (→ always
  empty); now **requires `county`** and errors clearly when missing.
- **#2 Fee schedule registry (`pipeline/fee_schedule.py`, NEW):** itemized `FeeSchedule`
  (`FeeComponent`s + `source` + `effective_date`) per jurisdiction. Wired into
  `entitlement.assess_entitlement` (uses schedule total when registered), the
  `analyze_property_deep` proforma (fee override so residual matches), and the chat
  formatter (emits `impact_fee_breakdown` ONLY when a real schedule is registered).
  `register_fee_schedule` / `get_fee_schedule`.
- **NOT POPULATED:** Both SD registries are intentionally **empty** — we did not hardcode
  unverified SD sales endpoints or fee amounts (doctrine). CA counties rarely expose
  arms-length prices via open GIS (real SD comps likely need a paid provider). SD's real
  fee categories are Mobility / Fire-Rescue / Library / Parks DIFs (Build Better SD,
  Resolutions R-314273 / R-314271 / R-314272) — amounts are in the FY26 fee schedule PDF
  (https://www.sandiego.gov/sites/default/files/feeschedule.pdf) + a parcel calculator.

---

## 5. Current state — FIXED vs NOT (be honest with the user)

**Fixed (deterministic + tested; the grounding fix proven live):**
- **Q1 = firm 6 units** (zone-aware grounding → verified → calculator keeps firm 6;
  coastal is a massing note, not a silent cut).
- `gateway.execute` error gone; chat uses `analyze_property`.
- Follow-ups cite grounded numbers (residual ~**$444,900** at 6 units) via the injected
  ACTIVE GROUNDED ANALYSIS block.
- No "ingest SD", no invented ordinance conflict, no fabricated fee breakdown.
- Real FEMA/coastal/wetlands from `site_risk`.
- Comps/fee **mechanisms** built; MCP `county` bug fixed.

**NOT closed (mechanisms exist, SD data not populated):**
- **Comps (Q4 land range, Q5 exit)** still fall back to the **regional default**
  (ADV $750k) — no SD sales source wired, so comps come back empty (now honestly labeled).
- **Fees (Q9)** still the coarse **$40k aggregate** (no SD schedule registered) — labeled,
  not itemized, not the real per-CPA numbers.
- **Utilities (Q11)** not modeled (known gap, by design).

**Deployment caveat:** ALL changes are **uncommitted and LOCAL**. Nothing is on Render.
Restart the local backend so `--reload` picks up changes before testing.

---

## 6. Files changed this session (all UNCOMMITTED)

```
src/plotlot/api/chat.py              analyze_property + screen_properties tools,
                                     GROUNDING_POLICY, _format_grounded_analysis (+ fee
                                     breakdown / provenance labels), _build_active_analysis_context,
                                     SessionStore.set_analysis/get_analysis, tool messages
src/plotlot/pipeline/analyze.py      analyze_property_deep (NEW fn); fee-override threading
src/plotlot/pipeline/lookup.py       coastal overlay in shared path; authoritative zone_code to verifier
src/plotlot/pipeline/extraction_verify.py  zone-aware grounding (_ground_for_zone, _ZONE_TOKEN_RE,
                                     _verify_field zone_code arg)
src/plotlot/pipeline/calculator.py   verified-entitlement protection (envelope/FAR don't override
                                     a verified density/min-lot count)
src/plotlot/harness/tool_registry.py analyze_property + screen_properties ToolContracts
src/plotlot/pipeline/comps_sources.py   NEW — comps source registry
src/plotlot/pipeline/comps.py        wire registry into find_comparables (before Hub fallback)
src/plotlot/pipeline/fee_schedule.py    NEW — itemized fee schedule registry
src/plotlot/pipeline/entitlement.py  use registered fee schedule total when present
src/plotlot/mcp/server.py            get_comparable_sales now requires county
tests/unit/test_chat_analyze_property.py   NEW — grounded payload, policy, persistence, screening, fees
tests/unit/test_data_sources.py      NEW — comps + fee registries, entitlement wiring
tests/unit/test_extraction_verify.py + SD_RM_TABLE zone-aware grounding regression
tests/unit/test_calculator.py        + TestVerifiedEntitlementProtection (6→4 regression lock)
tests/unit/test_mcp_server.py        get_comparable_sales county updates + requires-county test
diag_sd_grounding.py                 THROWAWAY live diagnostic (delete before commit)
```

---

## 7. How to work here (conventions)

### CI gates (run from `plotlot/` before committing)
```bash
uv run ruff format src/ tests/          # apply formatting
uv run ruff format --check src/ tests/  # SEPARATE CI gate from lint
uv run ruff check src/ tests/
uv run mypy src/plotlot/<changed files>
uv run pytest tests/unit/ -q
```
- **Known-environmental failures on this Windows box — IGNORE:**
  `test_status_scripts.py` (4–5 tests run `bash healthcheck.sh` where `python` resolves to
  the Microsoft Store stub → exit 49) and `test_health.py::test_health_degraded_on_db_failure`.
  Everything else passes. This session's last broad run: **327 passed**, only those 2
  environmental failures.

### Live diagnostic (run against the user's env — has DB + keys)
```bash
uv run python diag_sd_grounding.py   # prints ingestion/retrieval/grounding + FIXED ✓ verdict
```
It uses the REAL `hybrid_search` + `extraction_verify` so output = what the extractor sees.
(`diag_sd_grounding.py` is throwaway — delete before committing.)

### Architecture notes
- **Two density-calc entry points** both call `calculate_max_units` and thread verification
  flags: `lookup.py` (`lookup_address`, non-SSE; used by JSON `/analyze`, screening, and
  chat's `analyze_property_deep`) and `api/routes.py` `/analyze/stream` (SSE, its own inline
  pipeline). `extraction_verify.verify_numeric_params` is called **only** in `lookup.py`.
- The chat tool result is the grounded source of truth; the model must narrate from it. The
  ACTIVE GROUNDED ANALYSIS block (injected each turn) is what makes grounding persist.
- New per-city data = ONE registry entry (`comps_sources` / `fee_schedule`), not a rewrite.

### Hard rules
- Every change ships with tests. Commits under the configured git user (Phat Dang),
  **no Co-Authored-By**. Don't modify git config.
- Don't let an LLM emit a statutory constant / unverified number as fact.
- **Don't hardcode unverified external data** (endpoints, fee amounts) — source + date it,
  or build the mechanism and leave population as a verified step.
- Run `ruff format --check` (not just `ruff check`) before committing.

---

## 8. Suggested next steps (offered to user, not yet done)

1. **Verify chat Q1 = firm 6** live (restart local backend first), then **commit** the
   session's work (delete `diag_sd_grounding.py` first).
2. **Populate SD comps source (#1):** write a discovery diagnostic to confirm whether SD
   has a usable public sales layer; if not, wire a paid `provider` (ATTOM/Regrid). Until
   then land range / exit stay regional-default estimates.
3. **Populate SD fee schedule (#2):** pull real itemized DIF amounts from the FY26 fee
   schedule PDF into `fee_schedule.py` (with `source` + `effective_date`). Then Q9 produces
   real itemized fees and the residual/entitlement use them.
4. (Optional) Route the SSE `/analyze` route through the same shared composition as
   `analyze_property_deep` to remove the routes.py vs lookup.py duplication.

---

## 9. Concurrent-session note
A separate **deepseek** session was fixing bugs in parallel and committed
`09c7a6c "Added SD Proposition and fixed 12 critical bugs"` (added `CoastalHeightOverlay`
type + `pipeline/coastal_overlay.py` + 12 bug fixes). Our coastal wiring builds on it. If
you see unfamiliar coastal/Prop-D code, that's its origin. Coordinate before committing so
the two sessions' uncommitted changes don't clash.
