# PlotLot Agentic Harness Consolidation Design

**Date:** 2026-08-20  
**Branch:** `feat/plotlot-production-agentic-harness-mvp`  
**Status:** Approved for autonomous execution by the repository owner

## 1. Objective

Consolidate PlotLot into one production-grade agentic land-intelligence product for:

- San Diego County, California
- Miami-Dade County, Florida
- Broward County, Florida
- Palm Beach County / West Palm Beach, Florida
- Mecklenburg County / Charlotte, North Carolina

The product must support three first-class workflows through one governed harness:

1. **Single-site feasibility:** resolve a property, establish parcel and zoning facts, calculate by-right yield, surface physical and entitlement risks, and return a quick verdict with evidence.
2. **Lead sourcing:** search or ingest candidate parcels, apply a buy box, rank opportunities, preserve a working dataset, and prepare evidence-backed outreach artifacts.
3. **Deep underwriting:** inspect a selected site, compare development scenarios, calculate residual land value and sensitivity, document assumptions, and produce decision-ready reports.

The harness—not a generic chat interface—is the product. The model plans and narrates; deterministic tools establish facts and perform calculations.

## 2. Current-State Diagnosis

The repository already contains most required capabilities, but they are connected through competing execution paths:

- The typed tool registry declares core zoning, feasibility, calculation, sourcing, document, and connector tools.
- The shared `HarnessRuntime` powers the REST tools surface and MCP adapter.
- The legacy chat endpoint separately defines LLM tool schemas, session memory, intent routing, tool executors, grounding rules, and dataset state.
- The legacy analysis and screening endpoints call the deterministic pipeline directly instead of creating harness runs.
- The workspace page combines product state, local persistence, address heuristics, streaming, report rendering, and mode switching in one oversized client component.
- Product copy, design documents, tests, and implementation notes make inconsistent claims about market coverage and product capabilities.

The most important concrete defect is runtime parity: `analyze_property`, `calculate`, `analyze_upzoning`, and `screen_properties` are advertised by the canonical registry but are not registered in the shared default runtime. Chat succeeds only because it bypasses that runtime with bespoke implementations.

## 3. Design Decision

Use a **runtime-first strangler migration**.

Do not rewrite the application from scratch and do not perform a UI-only facelift over the duplicate backend paths. Complete the existing harness, route legacy adapters through it, and then simplify the UI around harness runs and evidence.

### Alternatives Rejected

#### UI-first cleanup

This would improve presentation quickly but preserve conflicting state, duplicated tools, and inconsistent trust behavior. Every new UI workflow would deepen the architectural debt.

#### Full rewrite

A rewrite would discard working county providers, ordinance ingestion, deterministic feasibility logic, tests, evidence models, approvals, and release controls. It has the highest delivery risk and no near-term product advantage.

#### Runtime-first strangler migration — selected

This preserves the working domain code while creating one execution seam. Each legacy route can be converted into a thin adapter without a risky big-bang cutover.

## 4. Target Architecture

```text
Web Workbench / REST / MCP
           |
           v
    Agent Run API + Event Stream
           |
           v
      Agent Orchestrator
  intent -> plan -> tool calls
           |
           v
  HarnessRuntime + ToolRegistry
  policy | budgets | approvals
           |
           v
Domain Tools and Skills
  - parcel + zoning resolution
  - ordinance evidence retrieval
  - deterministic site feasibility
  - buy-box sourcing and ranking
  - scenario and residual analysis
  - reports, drafts, and connectors
           |
           v
Evidence Ledger + Durable Run Context
  source facts | assumptions | calculations
  artifacts | approvals | telemetry | errors
```

### 4.1 Canonical Tool Registry

`plotlot.harness.tool_registry` remains the single source of truth for:

- tool names and descriptions
- input and output schemas
- risk classes
- budget requirements
- adapter-visible LLM function schemas

Chat, REST, MCP, tests, and future SDKs must derive their tool definitions from this registry. They must not maintain separate copies.

### 4.2 Complete Shared Runtime

`build_default_runtime()` must register every production-supported registry contract. The first parity gate is the four currently disconnected core tools:

- `analyze_property`
- `calculate`
- `analyze_upzoning`
- `screen_properties`

Their handlers must call existing deterministic domain functions, return structured dictionaries, and remain independent of HTTP and chat session state.

### 4.3 Agent Orchestration

The orchestrator classifies the user request into one of three workflow families and plans a bounded sequence of tools:

- `site_feasibility`
- `lead_sourcing`
- `deep_underwriting`

The user should not have to switch between a “lookup” product and an “agent” product. Intent controls the workflow, while the interface shows what the agent is doing.

The orchestrator must:

- preserve the active market, parcel, site, dataset, scenario, and evidence identifiers
- reuse a completed analysis for follow-up questions about the same site
- ask for clarification only when the target property or sourcing scope is materially ambiguous
- use deterministic calculation tools for every new arithmetic result
- stop or downgrade claims when source coverage is missing or stale
- request approval before external writes

### 4.4 Durable Context

Replace browser-only and process-memory context as the source of truth. The durable hierarchy is:

```text
Workspace -> Project -> Site or Candidate Set -> Agent Run -> Tool Runs -> Evidence -> Artifact
```

Local browser state may cache presentation preferences and optimistic UI state, but it must not be the only record of a conversation, active dataset, approval, or analysis.

### 4.5 Evidence and Trust

Every decision-relevant claim must be one of:

- **Verified fact:** tied to a source and evidence ID.
- **Deterministic calculation:** tied to named inputs and a calculation record.
- **User assumption:** visibly labeled and editable.
- **Estimate:** visibly labeled with its basis and confidence.
- **Unknown:** not filled by model inference.

The quick verdict must never hide uncertainty. A site can be `promising`, `needs_review`, or `not_supported`; it cannot be represented as fully verified when the parcel, zoning rule, lot area, or critical constraint is provisional.

### 4.6 Market Capability Registry

Create one canonical capability registry for the target market families. Each market exposes independent status for:

- address geocoding
- parcel facts
- owner and assessment data
- zoning district lookup
- ordinance text and citation retrieval
- site constraints
- deterministic feasibility
- bulk lead search
- deep underwriting
- source freshness

Valid statuses are:

- `available`
- `conditional`
- `degraded`
- `planned`
- `unavailable`

Coverage is capability-specific, not a single “supported county” boolean. Municipality-conditional Florida coverage and city-specific San Diego ordinance coverage must be represented honestly. The UI and public copy must read from this registry and must not claim nationwide coverage.

## 5. Product Experience

### 5.1 Primary Workspace

The default authenticated surface becomes a **Deal Intelligence Workspace**, not a blank chatbot.

Desktop layout:

1. **Left rail:** projects, recent runs, saved candidate sets.
2. **Center canvas:** the current site, candidate set, comparison, or report.
3. **Agent composer:** accepts an address, sourcing goal, underwriting question, or follow-up.
4. **Right rail:** run steps, evidence, assumptions, risks, approvals, and artifacts.

Mobile collapses the rails into drawers without removing evidence or run status.

### 5.2 Entry Actions

The empty state offers three concrete starting actions:

- **Analyze a site** — enter one property address.
- **Source opportunities** — describe a market and buy box or upload addresses.
- **Compare scenarios** — select an analyzed site and adjust assumptions.

There is no lookup/agent mode toggle. The same composer continues the active workflow.

### 5.3 Quick Site Result

A completed initial site run shows:

- verdict and confidence
- parcel and zoning identity
- by-right yield
- primary dimensional driver
- critical flood, wetland, coastal, airport, and geologic flags when evaluated
- residual land value when grounded inputs exist
- top unknowns and verification tasks
- cited source list
- actions for deep underwriting, comparison, report generation, or outreach

### 5.4 Lead Sourcing Result

A sourcing run shows:

- interpreted buy box
- source datasets and coverage status
- progress and failure counts
- ranked candidates with score components
- provisional-data flags
- filters and saved candidate set
- batch analysis and export actions
- evidence-backed outreach drafts requiring approval before send

### 5.5 Deep Underwriting Result

A deep underwriting run shows:

- base scenario
- alternative entitlement or density scenarios
- user-editable assumptions
- deterministic development program and residual calculations
- sensitivity table
- risk register and open diligence tasks
- evidence-backed investment memo or report artifact

## 6. API and Adapter Strategy

### 6.1 Canonical Run Contract

Introduce or evolve a canonical run surface with these semantics:

- create run with workflow intent and context
- stream ordered run events
- retrieve run state and result
- cancel a run
- replay a run with an idempotency key
- approve or reject gated actions

The existing harness job and event models should be reused rather than replaced.

### 6.2 Compatibility Adapters

During migration:

- `/api/v1/analyze` creates a site-feasibility run and translates the final result into the existing response stream.
- `/api/v1/chat` invokes the same registry and runtime while preserving its legacy SSE envelope.
- `/api/v1/screen` creates a lead-sourcing run and translates candidate events.
- `/api/v1/tools` and MCP continue to call the shared runtime directly.

After clients migrate, duplicate private executors and schemas are deleted.

## 7. Error Handling

Errors must be typed and actionable:

- `bad_input`
- `unsupported_market`
- `coverage_gap`
- `source_unavailable`
- `source_stale`
- `not_found`
- `policy_denied`
- `approval_required`
- `budget_exceeded`
- `timeout`
- `internal_error`

A failed source should not silently become an LLM estimate. The run may continue with an explicit degraded status when non-critical evidence is unavailable; it must stop when a missing source invalidates the requested decision.

Long-running tools emit heartbeats and step status. Cancellation and replay use the existing durable job controls.

## 8. Testing Strategy

### 8.1 Contract Tests

- Every registry tool marked production-supported has exactly one runtime handler.
- REST and MCP expose the same tool schemas.
- Chat tool schemas are generated from the registry.
- Risk classes and approval behavior remain identical across adapters.

### 8.2 Domain Tests

- Core runtime handlers return the same grounded results as the existing deterministic functions.
- Calculation rejects code execution and non-arithmetic input.
- Screening caps batch size and preserves deterministic ranking.
- Upzoning never invents a per-lot value.

### 8.3 Market Golden Tests

Maintain representative fixtures for each target market family. Tests assert parcel resolution, zoning identity, ordinance provenance, and expected confidence—not only HTTP success.

### 8.4 UI Tests

- one intent-led composer, no mode toggle
- coverage claims come from the capability registry
- evidence and provisional flags remain visible at decision points
- sourcing, feasibility, and underwriting flows work on desktop and mobile
- unsupported markets degrade honestly

### 8.5 Regression and Release Gates

Required gates:

- Python unit and integration tests
- Ruff and mypy
- frontend typecheck, lint, and unit tests
- Playwright smoke and workflow tests
- OpenAPI contract export
- release-manifest validation
- no unsupported marketing or nationwide coverage claims

## 9. Incremental Delivery

### Slice 1 — Runtime parity

- Add failing tests proving the four core contracts lack runtime handlers.
- Implement transport-neutral handlers for analysis, calculation, upzoning, and screening.
- Register them in the default runtime.
- Verify REST tool and MCP discovery now expose them.

### Slice 2 — Chat consolidation

- Generate LLM function definitions from the canonical registry.
- Replace bespoke core executors with calls to `HarnessRuntime`.
- Preserve the current SSE contract while emitting canonical harness events.
- Keep legacy session behavior only as a temporary compatibility cache.

### Slice 3 — Market truth

- Add the capability registry and API surface.
- Validate the five market families against existing providers and golden tests.
- Remove nationwide and unsupported capability claims from product copy.

### Slice 4 — Workbench consolidation

- Decompose the oversized workspace page into run, composer, canvas, evidence, and persistence modules.
- Remove lookup/agent mode switching.
- Surface the three intent-led entry actions and canonical run telemetry.

### Slice 5 — Durable workflows

- Persist active site and candidate-set context.
- Route `/analyze`, `/chat`, and `/screen` through canonical runs.
- Add scenario comparison and evidence-backed sourcing artifacts.
- Delete obsolete duplicate code after parity tests pass.

## 10. Non-Goals for the First Consolidation Cycle

- Replacing all existing county and municipality source adapters.
- Claiming uniform county-wide zoning coverage where regulations are municipal.
- Fully autonomous outbound communication without approval.
- Generative 3D massing as a substitute for verified zoning feasibility.
- A nationwide product claim.
- A new framework or rewrite solely for architectural novelty.

## 11. Definition of Done

The consolidation is complete when:

1. Chat, REST tools, MCP, site analysis, and lead screening use the same canonical tool contracts and runtime.
2. The three user workflows share durable context, evidence, policy, telemetry, and artifacts.
3. The UI presents one agentic workbench without a lookup/agent product split.
4. Market claims are generated from a tested capability registry for the five target market families.
5. All decision-relevant outputs distinguish verified facts, calculations, assumptions, estimates, and unknowns.
6. Duplicate tool schemas and core executors are removed.
7. CI and end-to-end workflow gates pass on the production harness branch.
