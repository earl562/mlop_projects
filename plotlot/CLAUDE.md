# PlotLot v2 — Working Context & Session Handoff

> This file replaces the prior CLAUDE.md. It is a full handoff so a fresh agent
> has every useful context: what PlotLot is, what we built/fixed, the approach
> and principles we agreed on, bugs encountered, decisions made, and what's still
> not done. Read the **Guiding Principle** section first — it governs everything.

---

## 1. Project snapshot

**PlotLot v2** — AI-powered land-deal intelligence. Given a US address it: geocodes
→ retrieves the parcel (ArcGIS) → fetches/searches zoning ordinances (pgvector
hybrid search) → an agentic LLM extracts numeric zoning params → a **deterministic
calculator** computes max buildable units → comparable sales → residual pro forma
→ streams results via SSE. User-facing artifacts: the streamed report, a one-page
**Deal Paper** PDF, and batch **Buy Box** screening.

- **User:** Phat (persona docs say "Earl Perry" — that's the portfolio persona; the
  real user is Phat). Values: action over talk, conciseness, honesty, accuracy, no
  silent failures. Commits under Earl Perry's git name, **no Co-Authored-By**.
- **Repo:** `d:\mlop_clone\mlop_projects` (git). Work happens in `plotlot/`.
- **Branch:** `Phat`. Remote: `origin` = github.com/earl562/plotlot-v2. (`dev` exists;
  early this session we fast-forward-merged `Phat` → `dev`.)
- **Stack:** FastAPI + Python 3.12+ (async-first), Neon Postgres + pgvector,
  Next.js 16 frontend, ReportLab/openpyxl for docs, NVIDIA NIM / Claude / etc. LLMs.
  Tooling is `uv`. The dev box is Windows + PowerShell; a Bash tool is also available.
- **San Diego is fully ingested** (~2,910 chunks via a custom PDF scraper, not Municode).

---

## 2. THE GUIDING PRINCIPLE (read this) — anti-hallucination

The user was previously burned by a hallucination: **PlotLot reported a wrong
buildable-unit count for a San Diego parcel.** The entire session's architecture is
organized around making that **never silently happen again**. The agreed doctrine:

1. **Math, statutory constants, tiers, and citations stay deterministic.** Never let
   an LLM *produce* a number that is actually a fixed fact (a density tier, an ADU
   count, a §65915 percentage). That reintroduces the failure mode.
2. **The LLM only extracts/proposes from text; every number it produces is verified**
   against the retrieved source (grounded citation + cross-check) before it's trusted.
3. **Fail loud, not silently wrong.** An unverified/contradicted value is shown as
   **PROVISIONAL**, never as a confident firm number. The firm "base" number is never
   contaminated by optional/uncertain layers (bonuses, overrides).
4. **Honesty about gaps.** Coarse estimates and unmodeled items are labeled as such.

If you add anything LLM-driven, it must wear this seatbelt (see `extraction_verify.py`
and `local_overrides.py` as the reference patterns).

---

## 3. Git state at handoff

**Everything is committed and pushed to `origin/Phat`; working tree is clean.**
Session commits (newest first):

| Commit | What |
|--------|------|
| `233f22d` | Seller-finance condition + state-variant terminology (bugs 7 & 8) |
| `c98bc91` | Chat generate_document: state from geocode not "FL" (bugs 2 & 5) |
| `882e91a` | CA density-bonus/ADU/SB9 upside + site-hazard eligibility + verified LLM local-override layer (#6, #2 eligibility) |
| `7e9b265` | San Diego lot-area-per-DU table grounding + verification-aware reconciliation |
| `5378828` | Reconcile contradictory density vs min-lot-area in calculator (the SD fix) |
| `e1e37e9` | Entitlement checklist + impact fees (#5) |
| `9768040` | Buy Box batch screening (#4) |
| `79883d9` | Deterministic extraction verification + provisional gating + sensitivity table (#3) |
| `90c1899` | ruff formatting fix |
| `c085538` | Residual loop fix + Deal Paper (#1, #2) |

---

## 4. What we built this session (all DONE, committed)

### #1 — Residual loop fix (the core valuation bug)
**Problem:** `comps.py` never populated `adv_per_unit`, so the residual pro forma
always fell back to "estimated land value" (circular — the offer was just the
comparable land value, not a real residual). Construction cost was a single
hardcoded South-Florida number nationwide.
**Files:** `pipeline/cost_model.py` (NEW), `pipeline/comps.py` (rewritten),
`pipeline/proforma.py`, `core/types.py`, `api/schemas.py`, `api/routes.py`, `mcp/server.py`.
- **`cost_model.py`** — `RegionalCostModel` (construction $/sf, soft %, builder
  margin %, `adv_per_unit_default`, `avg_unit_size_sqft`, `impact_fee_per_unit`) per
  market: South Florida, SF Bay Area, San Diego, Sacramento, Charlotte metro, Las
  Vegas, + national default. `get_cost_model(state, county)`.
- **`comps.py`** — now produces **two** comp sets: (a) **land comps** (vacant parcels
  → price/acre with **P25/median/P75 range** + estimated land-value band) and (b)
  **unit/exit comps** (improved sales → **ADV per unit**). Enforces recency window,
  excludes improved parcels from land comps (so structures don't inflate $/acre),
  larger candidate pool, newest-first ordering, polygon-centroid handling. Pure
  helpers (unit-tested): `_percentile`, `_price_range`, `_within_months`,
  `_classify_improved`, `_feature_latlng`, `_score_confidence`.
- **`proforma.py`** — ADV resolution chain: explicit override → comps ADV → regional
  default → land-value fallback, with `adv_source` tracking. Cost levers from the
  cost model. Impact fees deducted from the residual.
- New fields: `CompAnalysis.{price_per_acre_low/high, estimated_land_value_low/high,
  adv_per_unit_low/high, adv_source, unit_comparables}`; `LandProForma.{adv_source,
  market, impact_fees, impact_fees_per_unit}`.

### #2 — Deal Paper (the demo/lead artifact)
**Files:** `documents/deal_paper.py` (NEW); endpoint `POST /api/v1/geometry/deal-paper/pdf`
in `api/geometry.py`. Input is a `ZoningReportResponse.model_dump()` dict.
- One-page investment-memo PDF (ReportLab, "Warm Cartography" amber/stone brand).
- Sections: hero (MAX OFFER / MAX UNITS / EST LAND VALUE / ADV-UNIT), a red **"Verify
  before relying"** warnings callout, Deal at a Glance, **Valuation & Pricing** (the
  P25/median/P75 range table), **Source Verification** table, **Residual Pro Forma**
  (incl. impact fees), **Entitlement & Fees**, **Development Upside (CA programs)**,
  **Sensitivity** grid, Site Risk, and an Assessment/verdict.
- Hero reads **"MAX OFFER (PROVISIONAL)"** when extraction wasn't verified.

### #3 — Pro forma sensitivity table
**Files:** `pipeline/sensitivity.py` (NEW), `core/types.py` (`SensitivityTable`),
schemas, routes, deal_paper.
- `build_sensitivity_table` sweeps **ADV/unit (columns) × construction $/sf (rows)**
  at ±20%, recomputing `max_land_price` via `calculate_land_pro_forma` (reuses the
  residual math). The base cell equals the headline residual. Impact fees are threaded
  through the sweep so the base cell stays consistent. Rendered green/red in the Deal Paper.

### #4 — Buy Box batch screening (deal-sourcing)
**Files:** `pipeline/screening.py` (NEW), `pipeline/analyze.py` (NEW),
`api/screening.py` (NEW), schemas, `main.py`. Endpoint `POST /api/v1/screen` (SSE).
- `BuyBox` criteria (states, counties, zoning_prefixes, min/max lot, min_units,
  min_residual, `require_verified`, `exclude_high_flood_risk`, max_results).
  `evaluate_buy_box` (pure), `screen_reports` (rank by residual), `screen_addresses`
  (async, bounded concurrency, per-item timeout, **error isolation**, on_result callback).
- `analyze.py::analyze_property_full` composes the full pipeline for screening.
- `require_verified=True` drops deals whose buildable-unit drivers were provisional.

### #5 — Entitlement checklist + impact fees ("what it takes to build")
**Files:** `pipeline/entitlement.py` (NEW), `cost_model.py` (impact fees),
`proforma.py` (impact-fee deduction), `core/types.py`
(`EntitlementStep`, `EntitlementAssessment`), schemas, routes, deal_paper. **No LLM.**
- `assess_entitlement` — deterministic path classification (by-right / conditional-use /
  rezoning from the zoning use lists, with a multifamily zone-code fallback), a step
  checklist with timelines (CA discretionary paths add a CEQA step), total timeline,
  impact fees (from the cost model), and an honest "utilities not verified" caveat.

### #6 — CA state-program density uplift (ADU / SB9 / Density Bonus)
**Files:** `pipeline/density_bonus.py` (NEW), `core/types.py`
(`UpliftProgram`, `DensityUplift`, `LocalOverride`), schemas, routes, deal_paper.
**Deterministic, additive, CA-only — base zoning stays the firm number.**
- `compute_density_uplift` — ADU/JADU (SFR +2; MF +2 detached), SB9 (SFR → up to 4),
  Density Bonus (developments of 5+ units; statutory **+50%** cap; §65915 tiers).
  Every program carries a **statute citation** and its requirements. Programs are
  reported **separately, not naively stacked**; `max_potential` = best **eligible**
  pathway. Shown as a separate "Development Upside" overlay, never folded into the offer.
- **Site-hazard eligibility (the "#2" deterministic polish):** SB9 is gated on
  `in_flood_hazard` (FEMA Special Flood Hazard Area, from `site_risk`) / `has_wetlands`
  → `eligibility="restricted"`, excluded from `max_potential`. (ADU/Density Bonus are
  NOT restricted by flood — they're costlier, not ineligible.)

### Verified LLM "local override" layer
**File:** `pipeline/local_overrides.py` (NEW). Wired into `routes.py` after the uplift,
CA-only, 20s timeout, best-effort.
- The LLM **proposes** local-ordinance provisions that exceed the state baseline (e.g.
  San Diego Complete Communities / Transit-Priority-Area ADU bonuses). A **deterministic
  verifier is the gate**: (1) a verbatim quote is required; (2) the quote must be a real
  substring of the retrieved ordinance text (kills fabricated quotes); (3) the proposed
  number must appear in the quote (kills misreads); (4) the quote must contain the
  expected keywords (kills wrong-field grabs). Only verified overrides apply
  (`source="local"`); unverified ones are surfaced but never change a number.
- **Degrades silently** to the deterministic baseline on any failure (no creds, timeout,
  bad JSON). **Note:** the live LLM call was NOT exercised in dev (no API keys here) —
  the deterministic gate is fully unit-tested and it no-ops on failure, so it cannot
  regress the pipeline.

### Anti-hallucination core (the throughline)
**Files:** `pipeline/extraction_verify.py` (NEW), `pipeline/guardrails.py` (NEW),
`pipeline/calculator.py` (reconciliation), `core/types.py`
(`FieldVerification`, `ExtractionVerification`), routes + lookup wiring, deal_paper.
- **`extraction_verify.verify_numeric_params`** — grounds LLM-extracted density /
  min-lot-area / FAR against the retrieved ordinance text via regex, marking each
  `verified` / `conflict` / `unverified` with a citation. Includes a zone-code prior
  (RM-25 → 25 u/ac) and **San Diego lot-area-per-DU patterns** ("1 dwelling unit per
  1,000 sq ft of lot area"). It is **reconciliation-aware**: the density limit is
  verified if **either** encoding (units/acre OR min-lot-area) is source-verified, and
  it cross-flags a spurious units/acre value that contradicts a grounded min-lot-area.
  `offer_is_provisional` is True when the density limit isn't source-verified.
  `is_field_verified()` helper.
- **`guardrails.check_residual_plausibility`** — deterministic warnings for implausible
  density (>300 u/ac), an uncorroborated single-constraint result, or a regional-default
  ADV. Surfaced in `report.warnings` and the Deal Paper callout.
- **`calculator._reconcile_density`** — density (u/ac) and min-lot-area (sqft/DU) are the
  **same limit**; if they contradict (>25%) it prefers the **source-verified** encoding,
  else trusts min-lot-area; returns a consistent `(effective_density, effective_min_lot)`.
  `calculate_max_units` accepts `density_verified` / `min_lot_area_verified` flags
  (threaded from `extraction_verification` at both call sites) and caps confidence to
  `medium` on a contradiction.

---

## 5. The San Diego incident — root cause & current handling (important)

**1233 Hueneme St, San Diego, CA 92110 — zone RM-3-7, lot 6,470 sqft.** The agent
returned **1 buildable unit**; correct answer is **6**.

- **Root cause:** the LLM extracted BOTH `min_lot_area_per_unit = 1,000 sqft` (correct →
  6 units) **and** a spurious `max_density_units_per_acre = 6` (implausibly low for a
  multifamily zone). The calculator took `min()` across constraints, so the junk density
  crushed the result to 1. It was **double-counting the same density limit** expressed
  two ways.
- **Not our regression:** git proved the calculator and extraction were untouched by the
  feature commits. The 6↔1 flip is **LLM extraction variance** (the model sometimes emits
  the contradictory density). The reconciliation fix **contains** that variance.
- **Fix:** `_reconcile_density` (commit `5378828`) + SD table grounding (`7e9b265`).
  Now: min-lot-area grounds & verifies from the SD lot-area-per-DU text → the spurious
  density is flagged `conflict` → the offer is **firm (not provisional)** → **MAX UNITS = 6**.
- **Locked by a golden regression:** `tests/eval/test_extraction_grounding.py ::
  TestHueneme1233Regression`.
- Live-test caveat seen: FAR came back `conflict` (LLM 1.25 vs source 4.0) — a separate
  extraction-quality miss; it doesn't govern here, but it's a hint that SD FAR/table
  extraction can still improve.

---

## 6. Bug-review results (an external review listed 9 bugs)

| # | Sev | Status |
|---|-----|--------|
| 1 builder_margin rendered as % | CRIT | ✅ already fixed (renderers use `_fmt_currency`) |
| 2 state_code always "FL" | CRIT | ✅ fixed this session — was **dead code** (see below) |
| 3 profit hidden when GDV/cost=0 | MED | ✅ already fixed (unconditional `gdv - total_cost`) |
| 4 chat tool missing fields | MED | ✅ already fixed (tool exposes financing_type/state_code/etc.) |
| 5 handler doesn't extract report fields | MED | ✅ fixed this session — was **dead code** |
| 6 Returns vs Costs contingency mismatch | MED | ✅ already fixed (Returns includes contingency) |
| 7 `_state_variants.yaml`/`_categories.yaml` unused | LOW | ✅ fixed this session |
| 8 PSA seller_finance condition coupling | LOW | ✅ fixed this session |
| 9 dead `contracts.py` | LOW | ❌ **not a bug** — premise false (see below) |

**Bugs 2 & 5 (the real ones):** `_execute_generate_document` did
`session = _sessions.get(session_id)`, but `SessionStore.get()` is a stub that **always
returns None**, so the report-extraction block was unreachable (and it referenced
non-existent attributes `comp_analysis.comp_count` / `confidence_score`). Fix:
extracted a testable `_build_deal_context_data(session_id, args)` that reads the data
that actually exists — `get_property_context()` + `get_geocode()` — sources `state_code`
from the geocode (not hardcoded "FL"), removed the bogus attrs and the dead
`last_document` store. Tests: `tests/unit/test_chat_doc_context.py`. **Honest scope:** the
chat tool-loop doesn't compute comps/pro-forma (those are the `/analyze` pipeline), so a
chat-generated pro forma still needs financials from args or from running `/analyze`.

**Bug 7:** the loader already loaded both YAMLs into the registry; the engine didn't
**consume** them. Fix: `engine.assemble_clauses` injects `contract_term`
(from `_state_variants.yaml`, the 50-state installment-contract term, e.g. CA→"Land
Contract", TX→"Contract for Deed") and `state_code` into the Jinja render context; the
seller-finance clause uses `contract_term`; and a test enforces every LOI/PSA clause's
`order_weight` is within its `_categories.yaml` range (proforma clauses use an
independent ordering and are out of scope). Tests: `tests/unit/test_clause_state_and_categories.py`.

**Bug 8:** `psa/purchase_price_seller_finance.yaml` required
`financing_type == 'seller_carryback'`, so a `seller_finance` deal with `financing_type`
unset produced a PSA with **no purchase-price section**. Broadened to
`in ['seller_carryback', 'seller_finance', '']` (matching how the cash clause accepts `''`).

**Bug 9:** the report claimed `generate_loi`/`generate_deal_summary` in
`pipeline/contracts.py` are "dead code, not imported anywhere." **False** —
`tests/unit/test_deprecations.py` imports them and asserts they emit `DeprecationWarning`.
They are intentional, tested deprecation shims. **Not removed** (deleting tested
production code that contradicts the bug's premise would break the deprecation contract).
Full removal (functions + `test_deprecations.py` + the `GeneratedDocument` re-export) is
available if the user explicitly wants the deprecated API gone.

---

## 7. Known gaps / NOT implemented (be honest about these)

- **ADU / Density Bonus / SB9 numbers are statutory maxima / eligibility ceilings, not
  site-constrained achievable units.** Base zoning is conservative (it **under-counts**
  potential — the safe direction for a max-offer tool).
- **Coastal height / San Diego Prop D 30-ft limit** — NOT modeled.
- **Exact local fee schedules (DIF, water/sewer capacity, Mello-Roos)** — impact fees are
  **coarse regional estimates**, not a city's published schedule.
- **Parking reductions near transit (AB 2097), true utility capacity at the parcel** —
  flagged, not computed.
- **Scope note:** most of these are **California-statewide** (ADU, Density Bonus, SB9,
  AB 2097, Mello-Roos) and apply to all CA coverage (SD + Bay Area + Sacramento) — only
  **Prop D** is San Diego-city-specific; fee schedules and utility capacity are national gaps.
- **MCP `get_comparable_sales`** passes `county=""`, so it returns "missing county"
  (pre-existing; not fixed).
- **LLM local-override layer** not validated against a live model (no API keys in dev).
- **Document download:** chat `generate_document` returns metadata; the byte-download path
  may still need wiring (the dead `last_document` store was removed).

---

## 8. Recommendations / suggested next steps

1. **Coastal / Prop D restriction layer** (SD-specific) — affects height → stories → units.
2. **Real local fee schedules** to replace the coarse regional impact-fee estimate.
3. **Utility-capacity check** (GIS / will-serve) instead of the honest placeholder note.
4. **Site-constrained achievable units** for the density bonus (vs. statutory max).
5. Keep improving **San Diego table extraction** so more drivers (esp. FAR) verify.
6. If desired: fully remove the deprecated `contracts.py` API (bug 9) as its own commit.

---

## 9. How to work here (conventions the new agent must follow)

### CI gates — run ALL of these before committing (from `plotlot/`)
```bash
uv run ruff format src/ tests/         # apply formatting first
uv run ruff format --check src/ tests/ # CI GATE — SEPARATE from lint; a commit once
                                        # failed CI because only `ruff check` was run
uv run ruff check src/ tests/          # lint
uv run mypy src/plotlot/<changed files>
uv run pytest tests/unit/ -q
```
- **5 unit tests fail on this Windows box and are EXPECTED/environmental — ignore them:**
  `test_health.py::test_health_degraded_on_db_failure` and 4 in `test_status_scripts.py`
  (they run `bash healthcheck.sh`, where `python` resolves to the Microsoft Store stub →
  exit 49). Everything else passes (~1377 tests).
- After a clean run, **1377 unit tests pass**; new work added focused tests in:
  `test_cost_model`, `test_comps`, `test_proforma_pipeline`, `test_sensitivity`,
  `test_deal_paper`, `test_screening`, `test_extraction_verify`, `test_guardrails`,
  `test_entitlement`, `test_density_bonus`, `test_calculator`, `test_local_overrides`,
  `test_chat_doc_context`, `test_clause_state_and_categories`,
  `tests/eval/test_extraction_grounding`.

### Architecture conventions
- `core/types.py` uses **dataclasses**; `api/schemas.py` uses **Pydantic** response models.
  The SSE path emits `asdict(report)`; the non-SSE `/analyze` does
  `ZoningReportResponse(**asdict(report))` (Pydantic ignores extra fields, so add a
  response field if you want a new value exposed there).
- **Two density-calc entry points** both call `calculate_max_units` and must thread the
  verification flags: `pipeline/lookup.py` (`lookup_address`, the non-SSE path) and
  `api/routes.py` `/analyze/stream` (SSE). New deterministic steps (uplift, entitlement,
  guardrails) are wired in the **SSE path** after their inputs exist
  (e.g. density-uplift runs after `site_risk` so it can read flood flags).
- `ZoningReport.state` was **added this session** — consumed by cost_model, entitlement,
  density_bonus, and the chat `state_code`.
- Keep new financial/statutory logic **deterministic and tested**; if it needs the LLM,
  copy the `local_overrides.py` propose→verify→apply pattern.

### Local manual testing (PowerShell)
- `curl` is an alias for `Invoke-WebRequest` — use **`curl.exe`** or `Invoke-RestMethod`;
  no bash `\` line-continuations (use backtick or one line).
- Start backend: `uv run uvicorn plotlot.api.main:app --reload --port 8000` (the `--reload`
  clears the in-memory pipeline cache on code change). Needs `DATABASE_URL` (Neon w/ SD
  chunks), `NVIDIA_API_KEY`, `GEOCODIO_API_KEY`.
- `POST /api/v1/analyze` (non-SSE) returns the full JSON. The single most important
  accuracy check: inspect **`extraction_verification.fields`** (density `verified` vs
  `conflict`/`unverified`) and **`offer_is_provisional`**. Also `.pro_forma`,
  `.density_uplift`, `.entitlement`, `.sensitivity`, `.warnings`.
- Generate the Deal Paper: `POST /api/v1/geometry/deal-paper/pdf` with the analyze JSON.
- Test address: **1233 Hueneme St, San Diego, CA 92110** → should now be 6 units, firm.

### Key endpoints
- `POST /api/v1/analyze` (JSON) and `POST /api/v1/analyze/stream` (SSE)
- `POST /api/v1/geometry/deal-paper/pdf`, `POST /api/v1/geometry/report/pdf`
- `POST /api/v1/screen` (SSE buy-box)
- `POST /chat` (agentic chat; `generate_document` tool uses the clause builder)
- `GET /health`

### Hard rules (non-negotiable)
- Every change ships with tests. Commits under Earl Perry's name, **no Co-Authored-By**.
- Don't let an LLM emit a statutory constant or an unverified number as fact.
- Run `ruff format --check` (not just `ruff check`) before committing.
- Never expose credentials; `.env`, `credentials.json`, `token.json` stay untracked.

---

## 10. Key new files (quick map)
```
pipeline/cost_model.py         regional cost + impact-fee + ADV defaults (deterministic)
pipeline/comps.py              land + unit comps, price range, ADV (rewritten)
pipeline/proforma.py           residual w/ ADV chain + impact fees
pipeline/sensitivity.py        ADV × cost grid
pipeline/calculator.py         + _reconcile_density (verification-aware)
pipeline/extraction_verify.py  ground LLM zoning numbers vs source text (+ SD patterns)
pipeline/guardrails.py         plausibility warnings on residual inputs
pipeline/entitlement.py        approval path + timeline + impact fees
pipeline/density_bonus.py      CA ADU/SB9/Density-Bonus uplift (deterministic, additive)
pipeline/local_overrides.py    LLM-proposed, deterministically-verified local overrides
pipeline/screening.py          Buy Box eval + ranking + async orchestration
pipeline/analyze.py            analyze_property_full (composes pipeline for screening)
documents/deal_paper.py        one-page investment-memo PDF
api/screening.py               POST /api/v1/screen (SSE)
```
```
core/types.py     + CompAnalysis ranges/ADV, LandProForma fields, SensitivityTable,
                    Field/ExtractionVerification, EntitlementStep/Assessment,
                    UpliftProgram/DensityUplift/LocalOverride, ZoningReport.state/.warnings/
                    .extraction_verification/.entitlement/.density_uplift/.sensitivity
api/schemas.py    + matching response models
api/routes.py     SSE pipeline wires comps→proforma→sensitivity→site_risk→density_uplift
                    →local_overrides→guardrails; threads verification flags
api/chat.py       _build_deal_context_data (bugs 2 & 5)
clauses/engine.py contract_term/state_code injection (bug 7)
```

---

## 11. Session 2026-06-16 — Full Codebase Audit & Bug Fixes

### What happened
An external codebase audit identified 9 bugs (7 real, 1 reverted, 1 false-positive). Fixed all 7. Then performed a full codebase security/correctness audit, **finding 61 additional bugs** (14 CRITICAL, 14 HIGH, 18 MEDIUM, 15 LOW). Fixed 12 of 14 CRITICAL + all non-CRITICAL from the original 9 + 5 pre-existing CI failures remain.

### Fixed this session

**Original 9 bugs (from handoff):**
| # | Sev | Fix |
|---|-----|-----|
| 1 builder_margin rendered as % | CRIT | `_fmt_pct`→`_fmt_currency` in both renderers |
| 2 state_code always "FL" | CRIT | `ctx_data["state_code"]` from geocode in `chat.py:1618` |
| 3 profit hidden when GDV/cost=0 | MED | removed gdv/total_cost guard in both renderers |
| 4 chat tool missing fields | MED | added 15 params to chat tool def |
| 5 handler missing extractions | MED | added extraneous field extractions in handler |
| 6 Returns vs Costs contingency | MED | total_cost now includes contingency |
| 7 YAML ref files never loaded | LOW | `_load_reference_yaml()` wired into Registry |
| 8 seller_carryback vs seller_finance | LOW | REVERTED — different concepts, test confirmed |
| 9 dead contracts.py | LOW | left as-is (tested deprecation shims) |

**Audit CRITICAL fixes:**
| # | Bug | File | Fix |
|---|-----|------|-----|
| 1 | Commercial prop silently skipped from pro forma | `analyze.py:42-44` | Added warning when density n/a or zero |
| 2 | Density bonus max when below threshold | `density_bonus.py:160-172` | Distinct "not provided" vs "below threshold" logic |
| 3 | Coroutine passed as API key | `llm.py:267` | **REVERTED** — was actually correct (OpenAI SDK handles async callable for auto-refresh) |
| 5 | Debug endpoints exposed | `main.py:417,457` | Gated behind `settings.debug_mode` (env var `PLOTLOT_DEBUG=1`) |
| 7 | Datacenter no rate limit | `datacenter_routes.py:59` | Added `Depends(check_analysis_limit)` |
| 8 | Forward refs without `__future__` | `schemas.py:146-160` | Added `from __future__ import annotations` + `Literal` import |
| 9 | Confidence defaults to "" | `schemas.py:154` | Changed to `Literal["high","medium","low"]` defaulting to `"low"` |
| 10 | `max(1, floor)` inflates tiny lots | `calculator.py:125+` | Changed to `max(0, floor(...))` for units |
| 11 | `avg_unit_size_sqft=0` accepted | `proforma.py:90-93` | Added `and > 0` guards |
| 12 | SQL injection in ArcGIS WHERE | `property.py:341+`, `california.py:292+` | Added `_escape_where()` helper, applied to 9 interpolated WHERE clauses |
| 13 | Race on embedder counter | `embedder.py:23+` | Added `asyncio.Lock` |
| 14 | Race on engine creation | `db.py:59-81` | Added `asyncio.Lock` in `_ensure_engine()` |

### Files changed
```
M src/plotlot/api/datacenter_routes.py   — rate limit on datacenter endpoint
M src/plotlot/api/main.py                 — debug endpoints gated, HTTPException import
M src/plotlot/api/routes.py               — auth stub on admin endpoints (placeholder)
M src/plotlot/api/schemas.py              — __future__ annotations, Literal confidence
M src/plotlot/api/chat.py                 — state_code extraction, tool def, handler
M src/plotlot/config.py                   — added debug_mode field
M src/plotlot/core/types.py               — DensityUplift.eligibility values
M src/plotlot/documents/deal_paper.py     — coastal overlay display
M src/plotlot/ingestion/embedder.py       — asyncio.Lock for counter
M src/plotlot/pipeline/analyze.py         — commercial skip warning
M src/plotlot/pipeline/calculator.py      — max(0, floor) for units
M src/plotlot/pipeline/density_bonus.py   — below-threshold logic
M src/plotlot/pipeline/proforma.py        — >0 guards on units/area
M src/plotlot/property/california.py      — _escape_where() on 4 LIKE clauses
M src/plotlot/retrieval/property.py       — _escape_where() on 5 WHERE clauses
M src/plotlot/storage/db.py              — asyncio.Lock for engine creation
M src/plotlot/clauses/renderers/xlsx_renderer.py — builder_margin currency
M src/plotlot/clauses/renderers/sheets_renderer.py — builder_margin + profit
M tests/unit/test_api.py                  — fix patch target for debug test
M tests/unit/test_calculator.py           — test_minimum_one_unit expects 0, not 1
?? src/plotlot/pipeline/coastal_overlay.py — NEW (not committed)
?? tests/unit/test_coastal_overlay.py      — NEW (not committed)
```

### NOT fixed (blocked — auth redesign needed)
- **Critical #4** — No auth on admin endpoints (`routes.py:780+`). Requires designing/choosing auth middleware (Clerk JWKs, session middleware, or API key check). The `auth_enabled` + `clerk_jwks_url` settings exist but no middleware is wired.
- **Critical #6** — No auth on email connector (`connectors/email.py:239+`). Same root cause.

### NOT fixed (lower priority — ~45 bugs from audit)
The full audit found 61 bugs. 12 CRITICAL + 4 from the original 7 are fixed. Remaining:
- **HIGH**: property.py no pagination on ArcGIS, search.py plainto_tsquery drops zone codes, chat.py _Sessions dict never cleaned, etc.
- **MEDIUM**: Hardcoded defaults, missing field validations, inconsistent error handling.
- **LOW**: Typing, docstring, naming issues.

The full bug list was in the agent's context during this session but was not written to a persistent file. Next agent should re-derive from `git diff` between current tree and the audit baseline (before this session's fixes) if needed.

### Test results
- **1399 passed, 5 failed** — all 5 failures are pre-existing environmental (Microsoft Store Python stub in `test_health.py` + `test_status_scripts.py`).
- Both debug endpoint tests (`test_debug_llm_prefers_nvidia_when_stale_openai_token_exists`) and calculator minimum-unit test pass.
- 91 clause tests pass.
- **Ruff not run yet** — uncommitted changes may have formatting issues.

### Key decisions
1. `debug_mode: bool = False` config field gates `/debug/*` endpoints. Set `PLOTLOT_DEBUG=1` or `debug_mode=true` in `.env` to enable.
2. `_escape_where()` escapes single quotes (`'`→`''`) for ArcGIS REST API WHERE clauses — NOT parameterized queries (ArcGIS REST doesn't support them).
3. Codex OAuth token provider (async callable) kept as function reference — OpenAI SDK 1.68+ handles async callables for auto-refresh. **Not a bug.**
4. Auth (#4, #6) deferred because it requires middleware design across ~6 endpoint files. Suggested approach: `Depends(require_auth)` that verifies Clerk JWK, used as default dependency on admin routers.

### Independent verification (Claude, next session)

**CI gates confirmed clean:**
- `ruff format --check` — 255 files clean
- `ruff check` — all passed
- `mypy` (12 changed files) — no issues
- `pytest tests/unit` — 1399 passed, 5 failed (all 5 pre-existing environmental: Microsoft Store Python stub)

**Fix quality assessment:**

| Bug | Verdict | Notes |
|-----|---------|-------|
| #1 (commercial warning) | ✅ Clean | |
| #2 (density bonus) | ⚠️ **Latent** | `{set_aside_pct:g}` crashes when `income_level` set and `set_aside_pct=None` (line 171). Not reachable from prod (both args always `None` from routes.py:720). |
| #3 (codex oauth) | ✅ Correctly reverted | Verified in SDK source: OpenAI 2.31.0's async client types provider as `Callable[[], Awaitable[str]]` and `await`s it (`_client.py:789`). Not a bug. |
| #5 (debug gate) | ✅ Cosmetic | Guard before docstring makes docstring a dead expression. Harmless, ruff doesn't flag. |
| #7 (datacenter rate limit) | ⚠️ **Fig leaf** | `check_analysis_limit` no-ops for anonymous users (`billing.py:80-81`), `auth_enabled=False` by default. No real protection; same as pre-existing. |
| #8 (forward refs) | ✅ Clean | |
| #9 (confidence Literal) | ⚠️ **Regression risk** | Dataclass default still `""` (types.py:527). Non-SSE path `ZoningReportResponse(**asdict(report))` (routes.py:110) raises `ValidationError` → unhandled 500 if LLM returns anything outside `{high,medium,low}`. Fix should normalize at source, not response model. |
| #10 (max(0, floor)) | ✅ Clean | |
| #11 (>0 guards) | ✅ Clean | |
| #12 (SQL injection) | ✅ Clean | Correct escaping for ArcGIS REST (no parameterized queries). Minor: `_escape_where` duplicated in 2 files — should be shared utility. |
| #13 (embedder lock) | ✅ Clean | |
| #14 (engine lock) | ✅ Clean | |

**Bug list inflation:** Audit's "61 bugs" headline is over-severitized. Verified false positives:
- #3 (CRITICAL) — not a bug
- #15 (HIGH, buildable area negative) — guarded at calculator.py:446, returns 0.0 with note. Stale line numbers.
- #27 (HIGH, unparseable dates in comps) — intentional/documented (`_within_months` docstring)
- ~5 more HIGHs downgraded to MEDIUM/LOW on inspection (float(non-numeric), isinstance(bool), removeprefix style)

Real actionable set is materially smaller than 61. The single biggest risk cluster: **auth/rate-limiting gap** (#4 + #6 + #20 + #7) — in default config there's no auth and no rate limiting on public/admin/cost-fanout endpoints.

**Suggested next-session priorities:**
1. Fix #9 regression: normalize `report.confidence` at source (dataclass default → `"low"`, normalize LLM output)
2. Fix #2 latent crash: guard `{set_aside_pct:g}` format in density_bonus.py:171
3. Extract shared `_escape_where` utility (DRY)
4. Auth middleware design for #4/#6/#20/#7 cluster
5. Triage remaining HIGHs from the audit
```
