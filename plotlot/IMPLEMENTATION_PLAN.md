# PlotLot Agentic Harness — Implementation Plan

**Source:** the build-plan discussion (harness path, 6-month scope).
**Status:** disposable. Throw out and regenerate when stale (PLANNING mode).
**Convention:** one task per line, `[ ]` incomplete / `[x]` complete. Prioritized top-to-bottom within each phase. Ralph picks the highest-priority incomplete task each iteration.

---

## Phase 0 — Hygiene & decision lock ✅

- [x] **0.1** Branch reckoning: fresh `work/harness-build` from `origin/dev`; feature branch frozen as preservation reference; Ralph skill installed as pi builtin.
- [x] **0.2** MLflow gate fix: conftest fixture self-sets `MLFLOW_ALLOW_FILE_STORE`; verify script exports it on all 3 pytest paths; bundled 2 pre-existing tsc fixes. (merged `3d0a126`)
- [x] **0.3** jsdom localStorage polyfill in `tests/ui/setup.ts`; contract test pins it. Gate fully green on `dev`. (merged `3d79f69`)

## Phase 1 — De-risk spikes

- [x] **1.1** Dimensional-table extraction spike (Fort Lauderdale §47-5.60). PASSED: `DistrictDimensionalStandard` + `extract_dimensional_standards()` in `src/plotlot/domain/`. Verified-fact path is real. (merged `4ccbf74`)
- [ ] **1.2** Comps scraper — see dedicated task below. **BOUNDARY RULE: scraped comps are `kind=assumption, origin=unknown`, never `verified_fact`. Rendered amber, confidence ceiling. Used only when RentCast/County APIs can't cover a market. Gated behind Slice 9.1 governance before any production use.**

## Phase 2 — Domain foundation (the typed-claim spine)

- [ ] **2.1** `domain/claims.py` — `Claim`, `ClaimKind` (verified_fact/assumption/hypothesis/calculation/contradiction), `ClaimOrigin` (local_authority/rehabvaluator_concept/user_provided/derived_calc/unknown), `source_boundary_ok` invariant. Contract: `zoning.district` claim with `origin=rehabvaluator_concept` raises `SourceBoundaryViolation`.
- [ ] **2.2** `domain/steps.py` + `domain/methodology.py` — `KleymanStep` enum (1–8), step→field-key-namespace table, HTN task/method defs as data. Contract: step 5 blocked when `zoning.*` not `verified_fact`.
- [ ] **2.3** `domain/guardrails.py` — 5 rules (zoning.* must be local_authority; cost.*/cap_rate/financing.* must be assumption; entitlement hypothesis needs next_verification_step; material claim needs evidence_ids; contradictions surface as requires_human_review). Pure functions over `Claim[]`.
- [ ] **2.4** Move shared types to `domain/types.py` — `ToolContract`/`ToolContext`/`PolicyDecision`/`EvidenceItem`/`ReportClaim` from `land_use/models.py`. `land_use/` becomes thin service module. Existing `test_land_use_tool_contracts.py` must still pass.

## Phase 3 — Evidence engineering (the moat)

- [ ] **3.1** `OrdinanceSection` model + migration — `path` tuple, `section_type`, `cross_refs`, `referenced_by`. Chunker populates path + cross_refs.
- [ ] **3.2** Generalize dimensional extractor to 3 municipalities (FL + 2 more). Store `DistrictDimensionalStandard` rows with `source_section_id` provenance.
- [ ] **3.3** Wire `calculate_max_units` to read from `DistrictDimensionalStandard` (not LLM `NumericZoningParams`). Output claim `kind=calculation, origin=local_authority`.
- [ ] **3.4** Freshness as typed claim — `amended_date > scraped_at` → `freshness=stale` blocks `verified_fact` synthesis.
- [ ] **3.5** Backfill Fort Lauderdale end-to-end (every district has a standard, every section has path+cross_refs, freshness computed).
- [ ] **3.6** Ingestion eval — golden queries post-ingest; hit-rate ≥ 90%.

## Phase 4 — Tool consolidation

- [ ] **4.1** `tools/` package scaffold; every `ToolContract` has `kleyman_step`, `produces_field_keys`, `consumes_field_keys`.
- [ ] **4.2** Migrate location/ordinance tools to `tools/location/`, `tools/ordinance/`.
- [ ] **4.3** Fold `pipeline/skills/registry.py` into harness registry. Delete the second registry.
- [ ] **4.4** Decompose `run_deal_analysis` into step-3-through-8 calculator tools.
- [ ] **4.5** Residential vs commercial routing as HTN method dispatch (`step_3` branches on `product.unit_count`).
- [ ] **4.6** Migrate dataset/document/export tools.
- [ ] **4.7** Kill `chat.py`'s `_execute_tool` + `CHAT_TOOLS`; every call routes through `get_default_runtime()`.

## Phase 5 — Planner + agent loop

- [ ] **5.1** Rewrite `HarnessPlanner` as HTN/step-DAG. Step 5 blocked when `zoning.district` unknown.
- [ ] **5.2** `planner_rules.py` as Kleyman dependency rules; `SpecialistLane` = step capability scope.
- [ ] **5.3** `agent_loop.py` — ReAct over active step toolset. Mock LLM attempting step-5 tool during step 2 is blocked.
- [ ] **5.4** Tool results emit typed `Claim`s (`HandlerResult.claims`).
- [ ] **5.5** Synthesis parsing — step 8 → `recommendation.go_no_go` (calc) + `recommendation.entitlement_upside` (hypothesis).
- [ ] **5.6** `/agent-runs/{id}/events` SSE stream.

## Phase 6 — Storage + memory

- [ ] **6.1** `ClaimLog` table + append-only writes.
- [ ] **6.2** `Conversation` + `AssumptionOverride` tables.
- [ ] **6.3** `ContextBroker` binds to `ClaimLog`.
- [ ] **6.4** Delete in-memory `SessionStore`.

## Phase 7 — Transport collapse

- [ ] **7.1** `api/chat.py` → thin wrapper over `start_agent_run` (< 250 lines).
- [ ] **7.2** `/analyze/stream` wraps agent-run events.
- [ ] **7.3** MCP + tools REST consistency.

## Phase 8 — AgenticRAG retrieval

- [ ] **8.1** `search_index`/`open_section`/`follow_cross_ref`/`read_dimensional_table` tools.
- [ ] **8.2** Typed dimensional table as fast path (no LLM).
- [ ] **8.3** Retrieval misalignment guard.
- [ ] **8.4** Memory-poisoning guard (`source_boundary_ok=false` excluded from verified_fact).

## Phase 9 — Autonomous ingestion skill

- [ ] **9.1** Runtime governance layer (Paper 23): admission, policy guard, execution watcher, rollback, environment profiles, audit.
- [ ] **9.2** Ingestion as governed `Skill = (C,π,T,R)`.
- [ ] **9.3** Source discovery sub-skill (long tail: web_search + fetch_url + validate_authority).
- [ ] **9.4** `validate_authority` — non-`.gov` can never produce `verified_fact`.
- [ ] **9.5** Ingestion verification gate (hit-rate < 90% rolls back).
- [ ] **9.6** Re-answer loop — ship-gate scenario on one never-seen town.
- [ ] **9.7** (v2) AutoHarness adapter synthesis for novel structures.

## Phase 10 — Market parameterization

- [ ] **10.1** `MarketParameterSet` as typed claims. South FL costs = `kind=assumption, origin=local_authority` (CBRE source) or `user_provided`.
- [ ] **10.2** Region + asset-class parameterization (resi vs commercial sub-tables).
- [ ] **10.3** Comps as evidenced claims (RentCast/County = `local_authority`; scraped = `unknown` with confidence ceiling).

## Phase 11 — Opportunity skills

- [ ] **11.1** `lot_split_feasibility` (proof of concept; validated against golden case).
- [ ] **11.2** `assemblage_feasibility`.
- [ ] **11.3** `by_right_upzoning_scan`.
- [ ] **11.4** `missing_middle_eligibility`.
- [ ] **11.5** `adaptive_reuse_eligibility`.
- [ ] **11.6** `entitlement_upzoning`.
- [ ] **11.7** `build_to_rent_feasibility`.
- [ ] **11.8** `free_land_thesis` (composite meta-skill).

## Phase 12 — Eval + report

- [ ] **12.1** Report as ClaimLog projection (verified neutral / assumption amber / hypothesis distinct).
- [ ] **12.2** Report validator = Kleyman guardrails over ClaimLog.
- [ ] **12.3** Golden cases per step (≥5 each).
- [ ] **12.4** CI-enforced eval regression (`make eval`).

## Phase 13 — Frontend

- [ ] **13.1** `<AgentRunView>` event consumer.
- [ ] **13.2** Step rail (Kleyman 8 steps).
- [ ] **13.3** Claim stream rendering (verified/assumption/hypothesis treatments).
- [ ] **13.4** Replace 1,351-line workspace page (< 400 lines).

## Phase 14 — Operational + market readiness

- [ ] **14.1** Auth + ingestion authorization.
- [ ] **14.2** Cost control + budget enforcement.
- [ ] **14.3** Latency UX (async jobs).
- [ ] **14.4** Observability (structured logs, cost accounting, rollback-rate alerting).
- [ ] **14.5** Data freshness ops (re-ingest scheduler, diff detection).
- [ ] **14.6** Security review (SSRF allowlist, content sanitization, sandboxing).
- [ ] **14.7** Market surfaces (pricing, rate limits, MCP publication, docs).

## Ship gate

The end-to-end scenario, live: never-ingested small town → agent discovers source → governs ingestion → produces typed claims → runs 8 steps → emits report with evidence IDs + next-verification-steps OR escalates honestly. Plus: continuous eval green, security review signed, ops dashboard live.

---

## Slice 1.2 — Comps scraper (CURRENT)

**Task:** Build a listings scraper that returns comps data for South FL addresses.

**Boundary rule (non-negotiable, encoded in claim types):**
- Scraped comps → `Claim(kind=assumption, origin=unknown, confidence≤0.5)`.
- Rendered as **amber assumption**, never neutral verified fact.
- Used only when RentCast (already on `dev` via `394be70`) or County APIs can't cover a market.
- Gated behind Slice 9.1 governance before any production/ingestion use.

**Scope for this slice:**
1. Verify what RentCast on `dev` already covers (don't build redundant scraping).
2. Build the scraper module behind a tool contract: `fetch_scraped_comps(address, max_results)`.
3. Emit results as `kind=assumption, origin=unknown` claims with `source_url` + `extracted_at`.
4. Anti-bot resilience: retry with backoff, fail-closed to "no comps" (never fabricate).
5. Contract test: scraped comp has `kind=assumption`, `origin=unknown`, `confidence ≤ 0.5`, `source_url` populated, no `verified_fact` claim produced.

**Explicitly NOT in this slice:** wiring into the deal-analysis pipeline as a primary comp source, bypassing governance, presenting scraped ARV as authoritative. Those come (or are blocked) in later slices.
