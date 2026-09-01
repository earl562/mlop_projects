# PlotLot De-Slop and Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate PlotLot behind one analysis service and one governed tool executor, remove non-product scaffolding, add reliable comps, and benchmark the harness against a sanitized Drive-derived lead corpus.

**Architecture:** Use an incremental strangler migration from the current `cpt-pro` behavior. Preserve existing providers and deterministic calculations, add application seams around them, redirect transports one at a time, then delete duplicate orchestration only after parity tests pass.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy/PostgreSQL/pgvector, pytest, Ruff, mypy, Next.js 16, React 19, Playwright, GitHub Actions, Google Drive/Sheets connector.

**Spec:** `docs/superpowers/specs/2026-09-01-plotlot-deslop-evaluation-design.md`

## Global Constraints

- Work only on `feat/cpt-pro-deslop`, based on `cpt-pro@a3531aed37b6d7186addc1ef3b8ee00ec5199778`.
- Do not merge to `main`.
- Preserve known failures until their root cause is demonstrated.
- No production code change without a failing regression or architecture test first.
- No transport may bypass canonical policy, approval, evidence, or artifact handling.
- No unavailable data source may become an unlabeled model estimate.
- Comparable-sale valuation requires at least three qualified sales.
- Drive fixtures may contain property facts but no email, phone, mailing-contact, or free-text outreach data.

---

## File Structure

### New application seams

- `plotlot/src/plotlot/application/analysis/models.py` — typed request, event, result, and error contracts.
- `plotlot/src/plotlot/application/analysis/service.py` — one transport-neutral analysis orchestration service.
- `plotlot/src/plotlot/application/tools/executor.py` — one governed tool execution transaction.
- `plotlot/src/plotlot/application/tools/models.py` — executor request/result models.
- `plotlot/src/plotlot/application/market/comps.py` — deterministic comparable-sale qualification.
- `plotlot/src/plotlot/application/market/decision.py` — conservative acquisition decision packet.
- `plotlot/src/plotlot/evaluation/leads.py` — sanitized lead fixture loading and benchmark runner.

### Compatibility adapters

- `plotlot/src/plotlot/pipeline/lookup.py` — delegates `lookup_address()` to `AnalysisService` after parity.
- `plotlot/src/plotlot/api/routes.py` — JSON/SSE transport only.
- `plotlot/src/plotlot/api/tools.py` — delegates to `ToolExecutor`.
- `plotlot/src/plotlot/api/mcp.py` — delegates to `ToolExecutor`.
- `plotlot/src/plotlot/api/chat.py` — delegates model-issued tools to `ToolExecutor`.
- `plotlot/src/plotlot/harness/agents/registry.py` and `planner.py` — add market-comps and decision tasks.
- `plotlot/src/plotlot/harness/tool_registry.py` and `default_runtime.py` — register comps and decision tools.

### Tests and fixtures

- `plotlot/tests/unit/test_analysis_service.py`
- `plotlot/tests/unit/test_analysis_transport_parity.py`
- `plotlot/tests/unit/test_tool_executor.py`
- `plotlot/tests/unit/test_transport_policy_parity.py`
- `plotlot/tests/unit/test_reliable_comps.py`
- `plotlot/tests/unit/test_acquisition_decision.py`
- `plotlot/tests/unit/test_lead_fixture_sanitization.py`
- `plotlot/tests/unit/test_architecture_boundaries.py`
- `plotlot/tests/fixtures/leads/plotlot_drive_leads.json`
- `plotlot/tests/fixtures/leads/manifest.json`
- `plotlot/scripts/refresh_drive_lead_fixture.py`
- `plotlot/scripts/run_lead_benchmark.py`

---

### Task 1: Record and Reproduce the Baseline

**Files:**
- Create: `plotlot/docs/status/2026-09-01-deslop-baseline.md`
- Create: `plotlot/tests/unit/test_known_failure_contracts.py`
- Modify: `.github/workflows/nightly-health.yml`

**Interfaces:**
- Produces: documented baseline fingerprints for deployed health, provider discovery, and DB-backed lookup.

- [ ] **Step 1: Add tests for health classification**

Create unit tests for a helper that distinguishes application timeout, provider timeout, and dataset rejection. Verify the tests fail because the helper does not exist.

- [ ] **Step 2: Add bounded health-probe helper**

Create `plotlot/src/plotlot/health/probes.py` with typed probe results, three attempts, per-attempt timeout, elapsed time, HTTP status, and error category.

- [ ] **Step 3: Add provider diagnostic fields**

Expose discovery candidate URL, validation score, and rejection reasons in the nightly log without changing pass/fail semantics.

- [ ] **Step 4: Record exact baseline**

Document:

```text
cpt-pro head: a3531aed37b6d7186addc1ef3b8ee00ec5199778
Nightly run: 33522002201
DB-backed PR run: 32423852874
DB-backed failing test: lookup.db.spec.ts:24
Browser symptom: unexpected 503
```

- [ ] **Step 5: Verify and commit**

Run focused tests, Ruff, and mypy; commit as `test(plotlot): record cleanup baseline`.

---

### Task 2: Remove Non-Product Scaffolding

**Files:**
- Delete: `.claude/`
- Delete: `.omo/`
- Delete: `plotlot/.omx/`
- Delete: `CLAUDE.md`
- Delete: `GEMINI.md`
- Delete: `plotlot/CLAUDE.md`
- Modify: `.gitignore`
- Modify: `plotlot/scripts/check_repo_hygiene.py`
- Modify: `plotlot/tests/unit/test_repo_hygiene.py`
- Modify: `AGENTS.md`

**Interfaces:**
- Produces: one neutral repository contract and enforceable hygiene policy.

- [ ] **Step 1: Add failing hygiene tests**

Assert that tracked paths may not begin with `.claude/`, `.omo/`, or `plotlot/.omx/`, and may not equal `CLAUDE.md`, `GEMINI.md`, or `plotlot/CLAUDE.md`.

- [ ] **Step 2: Expand the hygiene script**

Make the script inspect `git ls-files`, report every forbidden path, and fail with one actionable message.

- [ ] **Step 3: Replace root instructions**

Reduce `AGENTS.md` to current architecture, security, test commands, supported branch workflow, and no personal prospect or identity context.

- [ ] **Step 4: Delete scaffolding and update ignores**

Ignore `.claude/`, `.omo/`, `.omx/`, `.worktrees/`, credential files, local DBs, and generated evaluation output.

- [ ] **Step 5: Verify and commit**

Run repo hygiene and its tests; commit as `chore(repo): remove non-product agent scaffolding`.

---

### Task 3: Add Characterization and Architecture Boundaries

**Files:**
- Create: `plotlot/tests/unit/test_analysis_transport_parity.py`
- Create: `plotlot/tests/unit/test_transport_policy_parity.py`
- Create: `plotlot/tests/unit/test_architecture_boundaries.py`

**Interfaces:**
- Produces: executable constraints used by Tasks 4 and 5.

- [ ] **Step 1: Characterize final report parity**

Inject the same deterministic analysis runner into JSON and SSE adapters and assert the final serialized report is identical.

- [ ] **Step 2: Characterize policy parity**

For one read-only, expensive-read, internal-write, and external-write tool, assert REST/chat/MCP adapters expose the same runtime decision.

- [ ] **Step 3: Add failing architecture tests**

Use Python AST/import inspection to fail when:

```text
api/routes.py imports underscore-prefixed pipeline symbols
api/chat.py invokes canonical handlers directly
api/mcp.py duplicates approval persistence
new transport modules import provider implementations
```

- [ ] **Step 4: Run red tests and commit**

Capture intended failures in CI; commit as `test(architecture): lock canonical analysis and tool boundaries`.

---

### Task 4: Introduce One Analysis Service

**Files:**
- Create: `plotlot/src/plotlot/application/__init__.py`
- Create: `plotlot/src/plotlot/application/analysis/__init__.py`
- Create: `plotlot/src/plotlot/application/analysis/models.py`
- Create: `plotlot/src/plotlot/application/analysis/service.py`
- Modify: `plotlot/src/plotlot/api/routes.py`
- Modify: `plotlot/src/plotlot/pipeline/lookup.py`
- Test: `plotlot/tests/unit/test_analysis_service.py`
- Test: `plotlot/tests/unit/test_analysis_transport_parity.py`

**Interfaces:**
- Produces:

```python
class AnalysisService:
    async def analyze(
        self,
        request: AnalysisRequest,
        *,
        emit: AnalysisEventSink | None = None,
    ) -> AnalysisResult: ...
```

- [ ] **Step 1: Write failing service tests**

Test event ordering, final result, timeout classification, partial property coverage, and deterministic fallback labeling.

- [ ] **Step 2: Implement typed models**

Define `AnalysisRequest`, `AnalysisEvent`, `AnalysisResult`, `AnalysisIssue`, and `AnalysisFailure`.

- [ ] **Step 3: Implement service over existing pipeline components**

Move orchestration without rewriting providers or calculations. Emit structured events after each stage.

- [ ] **Step 4: Convert JSON and SSE routes into adapters**

JSON returns `AnalysisResult.report`; SSE serializes `AnalysisEvent` and the same final report.

- [ ] **Step 5: Keep compatibility adapter**

`lookup_address(address)` constructs an `AnalysisRequest` and returns the service report.

- [ ] **Step 6: Remove private pipeline imports from API**

Make the architecture test pass.

- [ ] **Step 7: Verify and commit**

Run analysis, API, SSE, lookup, and architecture tests; commit as `refactor(analysis): unify JSON and SSE execution`.

---

### Task 5: Introduce One Governed Tool Executor

**Files:**
- Create: `plotlot/src/plotlot/application/tools/__init__.py`
- Create: `plotlot/src/plotlot/application/tools/models.py`
- Create: `plotlot/src/plotlot/application/tools/executor.py`
- Modify: `plotlot/src/plotlot/api/tools.py`
- Modify: `plotlot/src/plotlot/api/mcp.py`
- Modify: `plotlot/src/plotlot/api/chat.py`
- Modify: `plotlot/src/plotlot/harness/agents/coordinator.py`
- Test: `plotlot/tests/unit/test_tool_executor.py`
- Test: `plotlot/tests/unit/test_transport_policy_parity.py`

**Interfaces:**
- Produces:

```python
class ToolExecutor:
    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult: ...
```

- [ ] **Step 1: Write failing executor tests**

Test read-only success, approval required, approved external write, budget denial, handler error rollback, evidence persistence, and artifact persistence.

- [ ] **Step 2: Implement request/result contracts**

Include tool name, arguments, `ToolContext`, approval ID, transport, and idempotency key.

- [ ] **Step 3: Implement one transaction**

Validate the durable approval once, invoke `HarnessRuntime`, persist the tool run/evidence/artifacts, and return a canonical result.

- [ ] **Step 4: Redirect REST and MCP**

Remove their duplicate approval and persistence logic.

- [ ] **Step 5: Redirect chat and multi-agent coordinator**

Model-issued and specialist-issued tool calls use the executor. The model never supplies an approval token as a business argument.

- [ ] **Step 6: Verify and commit**

Run executor, policy, chat, MCP, tools API, and agent tests; commit as `refactor(harness): centralize governed tool execution`.

---

### Task 6: Repair Provider and DB-Backed Health Failures

**Files:**
- Modify: `plotlot/src/plotlot/property/hub_discovery.py`
- Modify: `plotlot/src/plotlot/property/universal.py`
- Modify: `plotlot/src/plotlot/retrieval/property.py`
- Modify: `plotlot/frontend/tests/lookup.db.spec.ts`
- Modify only the production cause identified by diagnostics.
- Test: provider discovery unit tests and DB-backed regression.

**Interfaces:**
- Produces: actionable provider diagnostics and a green canonical lookup scenario.

- [ ] **Step 1: Add diagnostic instrumentation only**

Log candidate service URL, geometry support, field coverage, score, rejection reason, and elapsed time.

- [ ] **Step 2: Re-run nightly provider tests**

Form one root-cause hypothesis from the new evidence.

- [ ] **Step 3: Add a failing regression test**

Use a saved ArcGIS response or transport fixture reproducing the discovered failure.

- [ ] **Step 4: Apply one provider fix**

Do not weaken validation globally or increase timeouts without evidence.

- [ ] **Step 5: Diagnose the browser 503**

Trace the failing request from browser console to backend route and first causal exception.

- [ ] **Step 6: Add a failing DB-backed regression and fix the source**

No test skipping or console-error allowlisting.

- [ ] **Step 7: Verify and commit**

Run provider unit/integration tests and DB-backed Playwright; commit as `fix(plotlot): restore provider and lookup health`.

---

### Task 7: Add Reliable Comps and Conservative Deal Decisions

**Files:**
- Create: `plotlot/src/plotlot/application/market/__init__.py`
- Create: `plotlot/src/plotlot/application/market/models.py`
- Create: `plotlot/src/plotlot/application/market/comps.py`
- Create: `plotlot/src/plotlot/application/market/decision.py`
- Modify: `plotlot/src/plotlot/harness/tool_registry.py`
- Modify: `plotlot/src/plotlot/harness/default_runtime.py`
- Modify: `plotlot/src/plotlot/harness/agents/models.py`
- Modify: `plotlot/src/plotlot/harness/agents/registry.py`
- Modify: `plotlot/src/plotlot/harness/agents/planner.py`
- Test: `plotlot/tests/unit/test_reliable_comps.py`
- Test: `plotlot/tests/unit/test_acquisition_decision.py`

**Interfaces:**
- Produces:

```python
def qualify_comps(subject: SubjectProperty, sales: list[ComparableSale], policy: CompPolicy) -> CompSetResult: ...
def build_acquisition_decision(inputs: AcquisitionDecisionInputs) -> AcquisitionDecision: ...
```

- [ ] **Step 1: Write exclusion tests**

Cover subject sale, duplicate sale, missing provenance, stale sale, distant sale, property-type mismatch, size mismatch, and price outlier.

- [ ] **Step 2: Write abstention/confidence tests**

Fewer than three qualified sales returns `insufficient_evidence`; confidence improves with count, freshness, distance, similarity, and source diversity.

- [ ] **Step 3: Implement deterministic qualification**

Return included and excluded sales with reason codes and evidence IDs.

- [ ] **Step 4: Write decision tests**

Use the lower of comp floor and residual ceiling; missing price/residual/comps must not advance a deal.

- [ ] **Step 5: Register tools and specialist**

Add `find_reliable_comps`, `build_acquisition_decision`, and a `market_comps` specialist to deep underwriting.

- [ ] **Step 6: Verify and commit**

Run market, tool registry, runtime, planner, coordinator, and report tests; commit as `feat(market): add reliable comps and deal decisions`.

---

### Task 8: Build the Drive-Derived Lead Evaluation Corpus

**Files:**
- Create: `plotlot/src/plotlot/evaluation/__init__.py`
- Create: `plotlot/src/plotlot/evaluation/leads.py`
- Create: `plotlot/scripts/refresh_drive_lead_fixture.py`
- Create: `plotlot/scripts/run_lead_benchmark.py`
- Create: `plotlot/tests/fixtures/leads/plotlot_drive_leads.json`
- Create: `plotlot/tests/fixtures/leads/manifest.json`
- Create: `plotlot/tests/unit/test_lead_fixture_sanitization.py`
- Create: `plotlot/tests/eval/test_drive_lead_benchmark.py`

**Interfaces:**
- Produces a versioned `LeadEvaluationCase` fixture and benchmark JSON.

- [ ] **Step 1: Discover and materialize selected Drive sheets**

Use the authenticated Drive/Sheets connector, not public web search.

- [ ] **Step 2: Sanitize before writing fixtures**

Keep address, city, county, state, parcel ID, asking/purchase price, lot size, zoning hints, and expected workflow. Remove contact data and free-text outreach notes.

- [ ] **Step 3: Add failing privacy tests**

Reject keys matching email, phone, mailing address, owner contact, or notes; reject values matching email and phone patterns.

- [ ] **Step 4: Add stable case IDs and manifest**

Hash normalized property identity, record extraction timestamp, connector file ID, row count, and schema version.

- [ ] **Step 5: Implement benchmark runner**

Run site feasibility, reliable comps, and acquisition decision workflows and emit success, abstention, evidence, latency, and confidence metrics.

- [ ] **Step 6: Verify and commit**

Run sanitization, fixture, benchmark-plan, and multi-agent tests; commit as `test(eval): add Drive-derived lead benchmark`.

---

### Task 9: Final Verification and Delivery

**Files:**
- Modify: `docs/superpowers/plans/2026-09-01-plotlot-deslop-evaluation.md` checkboxes.
- Update: draft PR description with exact results.

- [ ] **Step 1: Run backend gates**

```bash
cd plotlot
uv sync --frozen --extra dev --extra eval
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/plotlot/ --no-error-summary
uv run pytest tests/unit/ -q
```

- [ ] **Step 2: Run frontend gates**

```bash
cd plotlot/frontend
npm ci
npm run lint
npm run build
npm run test:ui
npm run test:e2e:no-db
npm run test:e2e:db
```

- [ ] **Step 3: Run live and evaluation gates**

```bash
cd plotlot
uv run pytest tests/integration/test_hub_live.py tests/integration/test_universal_validation.py -m live -v --tb=short
uv run pytest tests/eval/test_drive_lead_benchmark.py -v
```

- [ ] **Step 4: Inspect complete GitHub Actions matrix**

Record every job conclusion and exact unresolved external blocker. Do not infer success from partial jobs.

- [ ] **Step 5: Review diff and commits**

Confirm no credentials, contact data, generated artifacts, or unrelated UI changes are present.

- [ ] **Step 6: Open a draft PR to `cpt-pro`**

Do not target `main`. Include migration order, known behavior changes, test evidence, and any remaining abstentions or provider outages.
