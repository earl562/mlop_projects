# PlotLot v2 — Session Handoff (Data Authority + Narrator Trust)

> Fresh-agent handoff. Read the **Guiding Principle (§2)** first — it governs
> everything. This supersedes the old "Chat Grounding + Data Sources" handoff.
>
> **Current branch is `integration/phat-harness-mvp`, not `Phat`** (as of 2026-08-10).
> Market focus has shifted to **San Diego**; Florida is deprioritised. The
> session-specific state below (§3–§7) predates that shift — treat it as history and
> verify before relying on it.

---

## 1. Project snapshot

**PlotLot v2** — AI land-deal intelligence. Address → geocode → parcel (ArcGIS) →
zoning ordinance search (pgvector hybrid) → agentic LLM extracts numeric zoning
params → **deterministic calculator** → comps → residual pro forma → SSE stream.
Plus an **agentic chat** (`api/chat.py`) that narrates GROUNDED numbers only.

- **User:** Phat (persona "Earl Perry"). Values action, conciseness, honesty,
  **no silent failures**.
- **Repo:** `d:\mlop_clone\mlop_projects` (git — **one level below** the `d:\mlop_clone`
  the environment banner reports as "not a git repository"). Work in `plotlot/`.
  Branch `integration/phat-harness-mvp`.
  **Git user is "Phat Dang"** — do not modify git config. **No Co-Authored-By.**
- **Stack:** FastAPI + Python 3.12 (async), Neon Postgres + pgvector, Next.js 16,
  NVIDIA NIM Llama / Claude / Kimi. Tooling: `uv`. Dev box: Windows + PowerShell
  (Bash tool also available).
- **Concurrent agents:** this repo has been edited by THIS agent *and* an
  Opencode/Deepseek session, both committing to `Phat`. Coordinate; verify the
  tree (`git status`) before assuming state. Deepseek built `pipeline/permits.py`.

### Canonical test parcel — **1233 Hueneme St, San Diego, CA 92110**
- Zone **RM-3-7** (1 dwelling unit per 1,000 sqft lot area, SDMC Art.01 Div.04).
- **Lot 7,710 sqft** — County Assessor (authoritative), NOT the 6,471 the CA
  statewide parcel polygon reports. → **7 units by-right** (7,710 ÷ 1,000 = 7.71).
- Owner **"1233 HUENEME LLC"**; **20 active city permits** — it is an **active
  development**, not raw land. Neighborhood Morena. Flood Zone X; not in coastal
  jurisdiction; no wetlands; CGS landslide/liquefaction **not evaluated** (geotech
  unknown, not a clearance); **Airport Influence Area — Review Area 2 (SDIA)**.

---

## 2. THE GUIDING PRINCIPLE — anti-hallucination (read this)

1. **Math, statutory constants, citations stay deterministic.** Never let an LLM
   *produce* a number that is a fixed fact. The chat agent does **no mental math** —
   it calls the `calculate` tool (`pipeline/safe_calc.py`).
2. **The LLM only extracts/proposes; every number is verified** against the source
   before it's trusted — *including inputs*. "Verified" must cover the lot size, not
   just the ordinance rule.
3. **Fail loud, not silently wrong.** Unverified/uncertain values are PROVISIONAL.
   A geometry-estimated lot → the unit count is provisional even if the rule verified.
4. **Honesty about gaps.** Coarse estimates are labeled as such. **Don't hardcode
   unverified data** (no fabricated comps, fees, citations, or section numbers).

---

## 3. What's built (current systems)

### A. Lot-size authority — `property/california.py`
- SD lot size now comes from the **County Assessor** layer (`PDS/PDS_Layers/
  MapServer/0`) by APN — `_assessor_lot_sqft()` returns `(lot_sqft, owner_name)`.
  The CA statewide polygon (`Shape__Area`) was ~16% low and flipped 7→6 units.
- `PropertyRecord.lot_size_source` ∈ {`assessor`, `geometry`, `""`}. A `geometry`
  lot forces the chat unit count to PROVISIONAL (chat gates on this).

### B. Narrator trust — `api/chat.py` (`GROUNDING_POLICY` + `_format_grounded_analysis`)
- **Deterministic citation echo** (`_build_source_answer`): "what's the source?"
  is answered verbatim from the verified driver's section+citation — no fabricated
  §131.0445.
- **Exit/GDV line**, **sensitivity grid** surfacing, **CA program** names/statutes
  (no invented "SB9"), **internal reconciliation warnings suppressed**.
- **MATH RULE / FEE RULE**: all arithmetic via the `calculate` tool; no fabricated
  fee breakdowns (the phantom "police fee" is banned by name).
- **Development activity**: flags active permits before any land-price framing.

### C. `calculate` tool — `pipeline/safe_calc.py`
- AST-sandboxed arithmetic (numbers + `+ - * / // % **` only). No code-exec surface.
  Registered in `CHAT_TOOLS`/`CORE_TOOLS` + a `ToolContract` (guard test enforces).

### D. Site risk — `pipeline/site_risk.py`
- FEMA flood + NWI wetlands + **CGS geologic** (fault/landslide/liquefaction; codes
  3/4 = "not evaluated" = honest unknown) + **SD Airport Influence Areas**
  (`webmaps.sandiego.gov/.../DSD/Airports/MapServer/1`). Topography fabrication banned.

### E. Permits / development — `pipeline/permits.py` (Deepseek) + wiring (this agent)
- `fetch_development_signals(apn, county)` → SD Accela DSDPermits by APN. Wired into
  `analyze_property_deep` → `report.development_signals` → chat `development_activity`.

### F. Comps — `pipeline/comps.py` + `comps_sources.py` + `comps_rentcast.py`
- Resolution order: **curated registry → ArcGIS Hub discovery → RentCast (keyed
  fallback)** → labeled regional default. CA radius widened to 5mi; assessor/parcel
  Hub keywords added.
- **No free SD sold-price layer exists** (verified — CA parcels/assessor have no
  sale price; assessed ≠ market under Prop 13). **RentCast** (`comps_rentcast.py`)
  is the keyed fallback: `/avm/value` → nearby finished-unit sale comps →
  `adv_per_unit`, `adv_source="comps"`. **Needs `RENTCAST_API_KEY` + a live run to
  confirm the response schema mapping** (built to RentCast docs, unit-tested mocked).

---

## 4. Current state — FIXED vs OPEN (be honest)

**Fixed (deterministic + tested; live-verified where noted):**
- Lot 7,710 → **7 units**, source=assessor (live). Citation echo, GDV, sensitivity,
  CA programs (live transcript). Geologic + Airport (live). Permits: 20 active (live).
- `calculate` tool + MATH/FEE rules; owner surfaced; ADV source labeled.

**Open:**
- **Comps exit value — BLOCKED, not merely unverified (diagnosed 2026-08-10).** A
  `RENTCAST_API_KEY` is now present in `.env`, but **every** RentCast endpoint
  (`/avm/value`, `/properties`, `/listings/sale`, `/markets`) returns
  `403 billing/subscription-inactive`. The key is well-formed; the **subscription is
  inactive**. Consequence: with no free CA sold-price layer either, every San Diego
  comp lookup falls through to the labeled **$750k regional default** — identical
  across all 14 CA municipalities, which is why manual comping disagrees with it.
  Reactivate at `app.rentcast.io/app/api`. The response-schema mapping in
  `pipeline/comps_rentcast.py` has **still never run against a live response** — it is
  mock-tested only, so treat the first successful call as the real verification.
- **Impact fees**: SD's verified FY26 Citywide DIFs (Park/Fire/Library/Mobility =
  $23,402/unit for a ~1,000 sqft MF unit) are now **itemized** in the chat
  (`pipeline/fee_schedule.py`). It's a PARTIAL schedule (`covers_all_fees=False`):
  RTCIP/school/utility capacity fees are separate, so the **residual keeps the
  conservative $40k all-in** (never optimistically understated). Remaining: parse
  those separate fees for a full all-in.
- ~~**ESL Steep Hillsides** slope review: not checked~~ — **DONE** (`property/terrain.py`,
  commit `1515a20`): USGS 3DEP sampling gives `is_steep_hillside` (SDMC §113.0103's actual
  two-limb definition) and the broader `slope_constrained` gate. The unit count is
  deliberately **not** reduced — it is labelled an upper bound.
- **Weak-NIM narrator**: `calculate` + deterministic surfacing mitigate, but live
  re-runs of the deal-question sequence are the real regression test.

---

## 5. Conventions / CI gates (run from `plotlot/`)

```bash
uv run ruff format src/ tests/ ; uv run ruff format --check src/ tests/
uv run ruff check src/ tests/
uv run mypy src/plotlot/<changed files>
uv run pytest tests/unit/ -q
```
- **No known-good failures. The suite is fully green:** **2,100 passed, 0 failed**
  (2026-08-13, ~6 min). Treat *any* red test as real.
  The former "5 environmental failures — IGNORE" note is **obsolete**:
  `test_status_scripts.py` (4) was fixed by `9de72f7` (interpreter-portable) and
  `test_health.py::test_health_degraded_on_db_failure` now passes. A standing
  ignore-list outlives its cause and trains you to skip real regressions — do not
  reintroduce one without re-verifying it still fails.
- Every change ships with tests. Commit to `Phat`, git user Phat Dang, no
  Co-Authored-By. Don't modify git config.

### Live diagnostics (env has DB + keys; CA endpoints public)
- Lot/assessor: query `PDS/PDS_Layers/MapServer/0?where=APN='4364230200'`.
- Permits: `fetch_development_signals('4364230200','San Diego')` → 20 active.
- Throwaway diag scripts must be deleted before commit.

---

## 6. Key data sources

| What | Endpoint | Auth | Status |
|------|----------|------|--------|
| SD lot + owner | `gis-public.sandiegocounty.gov/.../PDS/PDS_Layers/MapServer/0` | none | ✅ wired |
| CGS geologic hazard | `services2.arcgis.com/.../CA_State_Parcels/FeatureServer/0` | none | ✅ wired |
| SD Airport Influence | `webmaps.sandiego.gov/.../DSD/Airports/MapServer/1` | none | ✅ wired |
| SD permits (Accela) | `webmaps.sandiego.gov/.../DoIT_Public/DSDPermits/MapServer/0` | none | ✅ wired |
| SD comps (sold price) | RentCast `/avm/value` | `RENTCAST_API_KEY` | ❌ keyed but **403 subscription-inactive** (2026-08-10) |
| SD slope / steep hillside | USGS 3DEP `getSamples` | none | ✅ wired (`property/terrain.py`) |
| SD impact fees (DIF) | `sandiego.gov/.../feeschedule.pdf` | public PDF | ✅ city DIFs parsed (partial) |

---

## 7. Suggested next steps
1. Add `RENTCAST_API_KEY` to `.env`, restart backend, run a deal-question on the test
   parcel → confirm RentCast comps populate `adv_source="comps"` and the schema maps.
2. Parse the FY26 SD DIF fee schedule into `pipeline/fee_schedule.py` (Hermes P2).
3. Re-run the full deal-question sequence live (weak-NIM regression check).
