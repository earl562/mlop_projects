# PlotLot Spec-Driven Work Breakdown

Date: 2026-05-11

## Purpose

This document converts the current PlotLot codebase assessment into a spec-driven execution breakdown. It focuses on four categories:

1. **What must be accomplished**
2. **What must be debugged**
3. **What must be fixed**
4. **What must be actively worked on next**

It is grounded in:

- direct codebase inspection
- repo status/plan artifacts
- existing test reports
- a live visual/frontend runtime check performed locally

## Runtime + visual evidence used for this breakdown

### What was verified live

- The frontend was started locally on `http://127.0.0.1:3002`.
- The marketing home route `/` loaded successfully and was captured with Playwright CLI.
- The `/analyze` and `/workspace` routes did **not** load successfully in the local dev session.

### What the live evidence showed

#### Home route works

The public home route is visually coherent and productized:

- strong hero section
- primary CTA: **Analyze a Lot**
- visible positioning around zoning/parcel intelligence
- polished marketing presentation

This aligns with the landing-page code in `apps/plotlot/frontend/src/app/page.tsx`.

#### Product routes are not reliably reachable in local dev

The frontend dev log shows:

- stale `.next/dev/lock` behavior before startup
- Turbopack persistence corruption / panic during later route compilation
- compilation beginning for `/workspace` and then failing inside Turbopack persistence

Evidence from the local dev log:

- `Unable to acquire lock at .../.next/dev/lock`
- `Persisting failed: Failed to deserialize AMQF ...`
- `FATAL: An unexpected Turbopack error occurred`
- `Compiling /workspace ...`
- `Persisting failed: Another write batch or compaction is already active`

See the local log captured during inspection at:

- `/var/folders/sx/_p5d2mn10q56tdsxxsp0lbsc0000gn/T/opencode/plotlot-frontend.log`

## Product reality statement

PlotLot already has substantial architecture and product code. The central issue is not lack of features in general. The central issue is that the platform now needs to be brought into a more reliable, trustable, and operationally hardened state.

The work ahead splits into two layers:

- **Layer A: runtime/product stabilization**
- **Layer B: trust/governance/memory hardening**

## Spec 1 — Local product surfaces must be reliably reachable

### Problem

The public landing page loads, but the actual product surfaces are not stable enough in local dev to serve as a dependable validation environment.

### Evidence

- `/` returns `200 OK`
- `/analyze` and `/workspace` hang/time out during inspection
- local dev log shows Turbopack persistence/database corruption behavior during route compilation

### Required outcome

A developer should be able to run the frontend locally and reliably reach:

- `/`
- `/analyze`
- `/workspace`

without stale lock interference, route compilation hangs, or persistent Turbopack panics.

### Work required

#### Debug

- determine whether the primary issue is:
  - Turbopack persistence corruption
  - route-specific compile behavior
  - Clerk/provider initialization interactions
  - workspace/analyze route dependency loading
- reproduce the route failure from a clean `.next` state
- isolate whether the failure is specific to `workspace`, `analyze`, or shared app layout/providers

#### Fix

- eliminate stale dev lock recurrence
- eliminate or route around Turbopack persistence corruption in local dev
- ensure local route compilation can complete consistently

#### Acceptance criteria

- fresh local frontend boot succeeds without manual lock cleanup
- `/analyze` loads within a normal dev-server response window
- `/workspace` loads within a normal dev-server response window
- no Turbopack persistence panic appears during first-route navigation
- Playwright visual smoke can capture all three routes successfully

### Relevant files

- `apps/plotlot/frontend/src/app/layout.tsx:1-65`
- `apps/plotlot/frontend/src/app/analyze/page.tsx:1-260`
- `apps/plotlot/frontend/src/app/workspace/page.tsx:1-260`

## Spec 2 — Lookup and Agent product lanes must match the stated contract

### Problem

The repo clearly defines two lanes:

- Lookup = fast, trust-critical, address-driven feasibility
- Agent = deeper follow-up reasoning and workflow

But the repo also explicitly says the boundary still needs sharpening.

### Evidence

- product split documented in `plotlot/README.md:19-38`
- contract documented in `apps/plotlot/docs/PLOTLOT_FLOW_CONTRACT.md:7-58`
- roadmap still calls for sharper Lookup vs Agent execution contracts in `plotlot/README.md:130-136`

### Required outcome

Users should immediately understand:

- which lane they are in
- what that lane is optimized for
- what outputs are guaranteed in that lane
- what is factual vs interpretive

### Work required

#### Accomplish

- make Lookup the clearly structured, address-first, facts-first experience
- make Agent the clearly session-oriented, deeper reasoning workspace
- ensure the UI and backend contracts reinforce the same distinction

#### Debug

- identify where agent-like behavior is leaking into Lookup
- identify where Lookup assumptions or gating create friction for Agent
- inspect whether route/page naming and navigation make the split obvious

#### Fix

- clarify the entrypoint rules for each lane
- standardize state transitions between modes
- ensure trust-critical outputs are visually separated from optional analysis

#### Acceptance criteria

- a first-time user can explain the difference between Lookup and Agent after one use
- Lookup returns parcel/zoning/setback/max-units facts before optional extras
- Agent does not market durable recall unless the backend contract truly supports it
- mode switching does not leak stale state across lanes

### Relevant files

- `plotlot/README.md:19-38`, `130-136`
- `apps/plotlot/docs/PLOTLOT_FLOW_CONTRACT.md:12-37`, `39-98`
- `apps/plotlot/frontend/src/app/workspace/page.tsx:125-260`
- `apps/plotlot/frontend/src/app/analyze/page.tsx:71-104`, `172-203`

## Spec 3 — Durable agent memory must become a real backend capability

### Problem

The current repo has agent UX, session-oriented client behavior, and chat persistence foundations, but the product docs are explicit that durable memory is still unfinished.

### Evidence

- `plotlot/README.md:30-38`, `48-54`
- `apps/plotlot/docs/PLOTLOT_FLOW_CONTRACT.md:47-58`
- unfinished memory backlog in `plotlot/docs/harness/BACKLOG.md:30-35`

### Required outcome

Agent memory should survive beyond local UI/session illusion and behave as durable product memory tied to property/project context.

### Work required

#### Accomplish

- semantic memory objects per property/project
- confidence-bearing memory records
- durable recall across sessions and resumes

#### Debug

- audit what is currently only stored client-side or session-locally
- identify where "memory" is really just restored local UI state
- inspect chat persistence versus reusable factual memory

#### Fix

- separate transcript storage from semantic memory storage
- add contradiction detection and staleness handling
- add compaction/reinjection rules for long-running agent context

#### Acceptance criteria

- the same property/project can be resumed with stable context after restart
- memory records can distinguish facts, assumptions, confidence, and freshness
- stale or contradictory remembered information is detectable and surfaced
- session continuity no longer depends primarily on localStorage semantics

### Relevant files

- `apps/plotlot/src/plotlot/storage/chat_store.py`
- `apps/plotlot/src/plotlot/storage/models.py`
- `apps/plotlot/frontend/src/app/analyze/page.tsx:181-239`
- `apps/plotlot/frontend/src/app/workspace/page.tsx:224-260`
- `plotlot/docs/harness/BACKLOG.md:30-35`

## Spec 4 — Trust-critical evidence and governance must be hardened

### Problem

PlotLot is a trust-critical zoning/intelligence product. Several key governance and provenance items are still open.

### Evidence

The backlog still lists unfinished work for:

- admission control / action governance
- prompt-injection filtering at input + tool-output boundary
- rollback/degradation strategy
- evidence ledger schema
- required citations for key constraints

See `plotlot/docs/harness/BACKLOG.md:5-28`.

### Required outcome

The system should make it hard to produce high-confidence-looking outputs without evidence, and hard for unsafe tool or prompt behavior to slip through quietly.

### Work required

#### Accomplish

- evidence ledger for ordinance chunks, parcel/provider provenance, and source freshness
- output contracts that require citations for trust-critical facts
- stronger agent action governance and denial/escalation rules

#### Debug

- inspect which current outputs lack citation enforcement
- inspect where prompt-injection exposure exists in ordinance/web/tool surfaces
- inspect where current tool permission controls stop short of full governance

#### Fix

- add structured provenance to constraints and conclusions
- require evidence presence for setbacks/max units/overlays/variances
- add safer degradation when anomalies accumulate

#### Acceptance criteria

- trust-critical outputs cannot be produced without visible evidence references
- risky or anomalous tool behavior is logged, governed, and escalated
- prompt-injection attempts are surfaced and handled deterministically
- degraded mode is explicit rather than silent

### Relevant files

- `plotlot/docs/harness/BACKLOG.md:5-28`
- `apps/plotlot/src/plotlot/api/routes.py:35-72`
- `apps/plotlot/src/plotlot/retrieval/search.py`
- `apps/plotlot/src/plotlot/observability/prompts.py`

## Spec 5 — db-backed flows must become routinely testable, not conditionally hopeful

### Problem

The codebase has good test breadth, but the reports show that db-backed and fully live flows are still more fragile than the no-db/demo lanes.

### Evidence

- VC readiness report notes no-db and stub lanes passing, but db-backed readiness degraded when local DB was unavailable: `apps/plotlot/frontend/tests/VC_READINESS_E2E_REPORT.md:8-12`, `61-66`
- distinguished walkthrough report says full local E2E was blocked by degraded backend environment: `apps/plotlot/frontend/tests/DISTINGUISHED_E2E_REPORT.md:22-28`, `60-75`
- runtime status/history docs also call out operational ambiguity around local processes and continuity

### Required outcome

The core product should be verifiable end-to-end in a stable, repeatable db-backed environment, not only through reduced or mocked lanes.

### Work required

#### Accomplish

- stable local DB-backed developer path
- healthy backend/MLflow/db status as a routine dev baseline
- reliable end-to-end verification path for report generation and persistence

#### Debug

- determine why the local environment slips into degraded mode
- determine whether the main friction is DB startup, provider/API dependencies, auth, or quota constraints
- identify which tests are useful smoke tests versus environment-noise generators

#### Fix

- tighten local startup instructions and health validation
- ensure one documented healthy path for full-stack verification
- reduce false confidence from tests that only prove no-db UI behavior

#### Acceptance criteria

- one command path exists for healthy local db-backed verification
- health endpoint reports healthy in the canonical dev stack
- at least one db-backed frontend E2E lane passes on the documented local stack
- a developer can reproduce a known-good full report flow without ad hoc environment recovery

### Relevant files

- `apps/plotlot/docker-compose.yml:1-76`
- `apps/plotlot/Makefile:1-34`
- `apps/plotlot/docs/status/CURRENT_STATE.md:20-45`
- `apps/plotlot/docs/status/runtime-status.json:1-31`
- `apps/plotlot/frontend/tests/VC_READINESS_E2E_REPORT.md:8-12`, `61-66`
- `apps/plotlot/frontend/tests/DISTINGUISHED_E2E_REPORT.md:22-28`, `60-83`

## Spec 6 — Operational continuity must become part of the product engineering discipline

### Problem

The repo already contains a continuity plan and status artifacts, but the status files themselves still describe important missing supervision/heartbeat/handoff discipline.

### Evidence

- missing watchdog/heartbeat/handoff discipline in `apps/plotlot/docs/status/CURRENT_STATE.md:26-37`
- open issues still present in `apps/plotlot/docs/status/runtime-status.json:26-30`
- explicit planned work in `apps/plotlot/docs/plans/2026-04-09-autonomy-continuity-plan.md:119-199`

### Required outcome

Long-running PlotLot work should leave behind reliable, machine-readable and human-readable state that any new session can resume from.

### Work required

#### Accomplish

- enforce `CURRENT_STATE.md` and runtime status discipline
- add watchdog/heartbeat automation
- turn continuity from plan into operating reality

#### Debug

- determine which parts of the continuity plan are already implemented versus only documented
- inspect where process health and useful work diverge

#### Fix

- ensure active runtime status stays up to date
- reduce ambiguity from multiple stray local processes
- make health + next action observable without opening chat history

#### Acceptance criteria

- state docs are updated as part of normal work completion
- watchdog/heartbeat signals reflect actual progress, not just process existence
- resume instructions are reliable after interruption or context loss

## Spec 7 — Public positioning is good, but product proof and transition clarity should improve

### Problem

The public landing page is polished, but the visual pass suggests the marketing surface currently outperforms the product-surface accessibility and proof surface.

### Evidence

From the Playwright-captured home view:

- hero and CTAs are polished
- value proposition is present but somewhat abstract at first glance
- trust/proof signals are not prominent in the immediately visible viewport
- the main CTA is strong, but the transition from marketing promise to product experience depends on routes that were not locally reachable during inspection

### Required outcome

The public site should not just look polished; it should lead cleanly into a reliably reachable product experience with clear proof and outcome framing.

### Work required

#### Accomplish

- strengthen proof cues near the top of the public funnel
- clarify what happens after clicking the primary CTA
- align marketing promise with actual reachable product flow

#### Debug

- inspect whether users are routed into auth/product surfaces with avoidable confusion
- inspect whether the home-page CTA paths map cleanly to Lookup vs Agent entrypoints

#### Fix

- tighten transition from marketing page to actual product route
- surface trust/proof earlier
- reduce mismatch between public polish and product-route fragility

#### Acceptance criteria

- the main CTA lands in a stable, fast-loading product surface
- first-time users can predict the next step after the landing page
- proof/trust signals are visible before deep scrolling

## Prioritized execution order

### P0 — Immediate

1. Stabilize frontend local runtime for `/analyze` and `/workspace`
2. Establish one reliable db-backed local verification path
3. Prevent silent dev/runtime corruption from masquerading as product issues

### 2026-05-12 P0 progress

- Repaired the immediate truthful-quality-gate failures that were directly reproducible from the plan:
  - backend mypy errors fixed
  - stale workspace UI shell test replaced with current address-first shell assertions
  - no-db e2e lane rerun successfully
  - backend `/health` startup path validated and documented as HTTP 200 / `degraded` when the DB is unavailable
- Folded in the new platform constraint that hosted Google products/APIs are unavailable:
  - removed active Google product/API code from backend/frontend/tests/scripts/config
  - replaced Workspace-style document generation with local `.docx` artifacts
  - replaced Workspace-style spreadsheet generation/export with local `.xlsx` artifacts
  - replaced cloud property cache with a local JSON cache
  - replaced hosted concept/building render calls with deterministic local PNG schematics
- Proof collected:
  - `git grep -n -i "google" -- apps/plotlot/src apps/plotlot/frontend/src apps/plotlot/tests apps/plotlot/scripts apps/plotlot/pyproject.toml apps/plotlot/.env.example` returned no matches
  - `uv run pytest tests/unit/test_local_artifacts.py tests/unit/test_render.py tests/unit/test_api.py -q` passed (`42 passed`)

### 2026-05-12 LLM/provider + production readiness progress

- Reworked agent chat LLM provider selection away from Google-hosted assumptions:
  - `GROQ_API_KEY` is now the first mainline provider
  - `NVIDIA_API_KEY` remains the second mainline provider
  - OpenAI API key/access-token/Codex OAuth remains supported after Groq/NVIDIA
  - OpenRouter remains an optional fallback
- Updated local and deployment env templates so Render/Railway/local runs expose the same non-Google provider names.
- Removed stale `NEXT_PUBLIC_GOOGLE_MAPS_KEY` from the Vercel `plotlot-v2` production environment.
- Production verification:
  - `https://plotlot-api.onrender.com/health` returned HTTP 200, `status=healthy`, and `agent_chat_ready=true`
  - `https://plotlot-api.onrender.com/debug/llm` returned NVIDIA provider status `ok`
  - Vercel `plotlot-v2` production env now contains `NEXT_PUBLIC_API_URL=https://plotlot-api.onrender.com` and no Google env var
- Local verification:
  - `GROQ_API_KEY=local-smoke-key uv run uvicorn ...` plus `/health` returned `agent_chat_ready=true`
  - `uv run pytest tests/unit/test_health.py tests/unit/test_llm.py tests/unit/test_api.py -q` passed (`53 passed`)
  - `uv run ruff check src/ tests/` passed
  - `bash -n scripts/run_backend_with_codex_oauth.sh scripts/setup_phase2.sh` passed
  - `uv run mypy src/plotlot/ --no-error-summary` passed
  - `npm run lint` passed
  - `npm run build` passed

### Remaining immediate work

The remaining P0 gap is DB-backed routine verification. Start local Postgres with `make db-up`, rerun `bash scripts/status/healthcheck.sh`, then run the db-backed frontend lane once `/health` reports `db_backed_analysis_ready=true`. Production DB-backed capabilities are currently healthy, but production MLflow reports an out-of-date schema and needs a planned migration window.

### P1 — Core product hardening

4. Complete durable memory as a backend contract
5. Harden evidence, citations, provenance, and governance
6. Sharpen Lookup vs Agent execution boundaries in both UI and backend behavior

### P2 — Operational + scale readiness

7. Finish continuity/watchdog/heartbeat discipline
8. Expand provider/municipality reliability and freshness governance
9. Add red-team and governance-focused eval coverage

## Bottom line

The right reading of PlotLot is:

- **not** "needs a product from scratch"
- **yes** "needs stabilization, trust hardening, and execution discipline"

The codebase already proves that the product exists. The next phase should be treated as a **reliability + trust + continuity program** with clear specs and acceptance criteria, not a vague feature brainstorm.
