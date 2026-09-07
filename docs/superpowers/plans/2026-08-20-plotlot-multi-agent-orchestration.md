# PlotLot Multi-Agent Orchestration Implementation Plan

> Execute with test-driven development and verification-before-completion. Do not merge to `main` from this plan.

**Goal:** Ship the first governed multi-agent vertical slice for site feasibility, lead sourcing, and deep underwriting on `cpt-pro`.

**Architecture:** Declarative specialist registry + deterministic DAG planner + bounded-concurrency coordinator over the existing `HarnessRuntime`.

## Task 1 — Branch Foundation

- [x] Confirm `cpt-pro` has no divergent commits.
- [x] Confirm `feat/plotlot-production-agentic-harness-mvp` is a clean fast-forward target.
- [ ] Fast-forward `cpt-pro` to `3059256d54e4ef30446dfbf18493c7e69145c9d8` before publishing implementation commits.

## Task 2 — Lock Specialist Boundaries

**Files:**

- Create `plotlot/src/plotlot/harness/agents/models.py`
- Create `plotlot/src/plotlot/harness/agents/registry.py`
- Create `plotlot/tests/unit/test_multi_agent_registry.py`

- [x] Add failing imports/tests.
- [x] Define workflow, role, task, plan, result, and run status contracts.
- [x] Define six specialists with least-privilege tool allowlists.
- [x] Reject cross-agent tool escalation and unknown canonical tools.

## Task 3 — Build Deterministic Plans

**Files:**

- Create `plotlot/src/plotlot/harness/agents/planner.py`
- Create `plotlot/tests/unit/test_multi_agent_planner.py`

- [x] Build site-feasibility plan.
- [x] Build lead-sourcing plan.
- [x] Build deep-underwriting plan.
- [x] Bind parcel/geocode/analysis outputs by explicit paths.
- [x] Refuse to invent underwriting targets or finished-lot values.
- [x] Validate task IDs, dependencies, binding sources, and DAG acyclicity.

## Task 4 — Execute Through HarnessRuntime

**Files:**

- Create `plotlot/src/plotlot/harness/agents/coordinator.py`
- Create `plotlot/src/plotlot/harness/agents/__init__.py`
- Modify `plotlot/src/plotlot/harness/events.py`
- Create `plotlot/tests/unit/test_multi_agent_coordinator.py`

- [x] Execute dependency-ready tasks in bounded parallel waves.
- [x] Prove independent site-identity and feasibility agents overlap.
- [x] Route every tool through the injected runtime.
- [x] Propagate blocked and approval-required results.
- [x] Stop dependent work after failed required dependencies.
- [x] Aggregate transitive evidence IDs.
- [x] Require primary analysis success before reporting.
- [x] Produce stable agent/task/run summaries and events.

## Task 5 — Expose Authenticated REST Surface

**Files:**

- Create `plotlot/src/plotlot/api/agent_runs.py`
- Modify `plotlot/src/plotlot/api/harness_jobs.py`
- Create `plotlot/tests/unit/test_multi_agent_api.py`

- [x] Add specialist discovery endpoint.
- [x] Add side-effect-free plan endpoint.
- [x] Add execution endpoint.
- [x] Build one shared `ToolContext` per run.
- [x] Validate approvals against durable records.
- [x] Fail closed when approval storage is unavailable.
- [x] Mount routes under the authenticated harness-job boundary.

## Task 6 — Focused Verification

- [x] Run focused pytest red phase and confirm missing-module failures.
- [x] Run focused pytest green phase: 20 tests passing.
- [x] Compile source and tests with `compileall`.
- [x] Check changed Python files for lines above the repository 100-character limit.
- [ ] Run Ruff lint and format in repository CI.
- [ ] Run mypy in repository CI.

## Task 7 — Publish and Repository Verification

- [ ] Create a focused implementation commit on `cpt-pro` under Earl Perry only.
- [ ] Dispatch the existing full CI workflow on `cpt-pro`.
- [ ] Verify repo hygiene.
- [ ] Verify Ruff and format checks.
- [ ] Verify mypy.
- [ ] Verify all backend unit tests against Postgres.
- [ ] Verify frontend lint, build, and UI tests.
- [ ] Verify Playwright no-DB and DB-backed suites.
- [ ] Verify repository-pair release gate or report the exact environmental blocker.
- [ ] Inspect final diff and branch head.

## Next Slice After Green CI

1. Route chat tool schemas and execution through the canonical runtime.
2. Add durable persistence/replay for `MultiAgentRunResult` and coordinator events.
3. Add the five-market capability registry.
4. Replace lookup/agent mode with one run-centered workbench.
5. Add measured specialist expansion only where evaluation shows a quality or latency gain.
