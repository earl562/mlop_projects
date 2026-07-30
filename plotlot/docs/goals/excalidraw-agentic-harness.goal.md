# PlotLot Excalidraw Agentic Harness Goal

Implement the Excalidraw system design as a production-shaped, reliable
agentic harness work stream.

This goal is derived from:

- `docs/architecture/agentic-harness-system-design.md`
- `docs/architecture/excalidraw/plotlot-agentic-harness.excalidraw`
- `docs/architecture/excalidraw/plotlot-agentic-harness-preview.html`

## Outcome

PlotLot can run the MVP agentic land-use analysis lane end to end:

```text
Address lookup
  -> parcel and jurisdiction resolution
  -> zoning and ordinance evidence
  -> explicit developer scenario hypothesis
  -> deterministic density, NOI, and residual-land-value calculations
  -> comp support
  -> evidence review
  -> cited feasibility memo
```

The result must behave like an autonomous harness, not a chatbot prompt:

- runs persist and resume from durable state;
- bounded agents operate through scoped skill lanes;
- all material claims are backed by evidence, deterministic calculations, or
  explicit assumptions;
- Rehab Valuator ground-up development concepts shape scenario and calculator
  workflows but never become parcel, zoning, market, cost, or lender facts;
- failures degrade into visible partial results and repair steps;
- risky, costly, or external side-effecting actions require approval;
- every surface uses shared runtime contracts instead of duplicated business logic.

## System Design Contract

Preserve the architecture layers shown in the Excalidraw canvas:

1. Product surface
   - Web workbench
   - API
   - MCP adapter
   - Background job/run views

2. Governance and run control
   - Workspace auth and role context
   - User tier and vendor budget policy
   - Approval policy
   - Run state machine
   - Queue with retries, cancellation, and idempotency

3. Skill lanes and bounded agents
   - Planner Agent
   - Parcel Agent
   - Zoning Agent
   - Scenario Agent
   - Market and Comps Agent
   - Feasibility Agent
   - Evidence Reviewer
   - Report Agent

4. Deterministic tool layer
   - Geocode and parcel lookup
   - Parcel geometry and jurisdiction lookup
   - ArcGIS/open-data queries
   - Municode/local ordinance search and fetch
   - Subdivision and entitlement-procedure fetch
   - Browser comp capture as a last-mile adapter
   - Comparable listing ranking
   - Density, NOI, DSCR, yield-on-cost, and residual-land-value calculators
   - Report/document builders

5. Durable state and operations
   - Postgres/pgvector stores
   - Evidence ledger
   - Assumption register
   - Formula/input trace
   - Run and tool event log
   - Artifact store
   - Workspace memory
   - Verification and eval store
   - Health checks and observability

## Operating Rules

- Do not build a single giant super-agent.
- Do not expose unbounded tool catalogs to model turns.
- Do not let browser comping become the system of record.
- Do not treat Rehab Valuator training as local zoning, market, cost, cap-rate,
  or lender authority.
- Do not present upzoning, subdivision, instant-equity, or free-land upside as
  guaranteed.
- Do not finalize reports with unsupported zoning, GIS, comp, or underwriting claims.
- Do not retry non-idempotent tools without idempotency keys and side-effect policy.
- Do not hide assumptions; show them in reports and run traces.
- Do not treat fixture, mock, or stale municipal data as production-grade evidence.
- Prefer read-only analysis and draft artifacts before adding external writes.

## Implementation Phases

### Phase 1: Goal and Traceability

- Keep this goal file linked from architecture docs.
- Keep the Excalidraw source and preview page checked in.
- Add or update implementation-status notes so the visual layers map to code
  modules, routes, and tests.

### Phase 2: Run Control

- Ensure `AnalysisRun` state captures planner, parcel, zoning, comping,
  feasibility, review, and report stages.
- Ensure run events persist ordered stage, tool, evidence, approval, retry,
  failure, cancellation, and report events.
- Ensure runs can be replayed through CLI and API-visible traces.

### Phase 3: Scoped Skill Lanes

- Define scoped toolsets for zoning analysis, comp support, feasibility, and
  report generation.
- Add a developer scenario lane that converts verified buildability into
  by-right, build-to-rent, build-to-sell, multifamily, lot-split, upzoning, or
  fallback hypotheses.
- Route existing chat/web lookup behavior through shared harness tools when a
  matching tool exists.
- Keep planner output typed and bounded to known lanes.

### Phase 4: Evidence And Verification

- Store every material zoning, GIS, comp, and calculator claim in the evidence
  ledger or assumption register.
- Store every calculation with formula, input values, evidence IDs, assumption
  IDs, warning rules, and reproducible output.
- Add freshness/confidence metadata to evidence used in report finalization.
- Block report finalization when evidence review fails.
- Emit repair steps when missing or contradictory evidence blocks completion.
- Fail review when a training concept is promoted to local authority or when
  entitlement upside is stated without current/proposed/fallback risk framing.

### Phase 5: MVP Surface

- Expose the MVP lane through CLI, API, and workbench surfaces.
- Show run progress, partial results, blocked states, approvals, evidence, and
  final cited memo.
- Keep MCP parity for the same core runtime/tool contracts.

## Acceptance Checks

The goal is complete only when all checks below pass against the current
worktree:

- `uv run ruff check src/ tests/`
- `uv run mypy src`
- `uv run pytest tests/unit/ -q --tb=short`
- JSON validation passes for
  `docs/architecture/excalidraw/plotlot-agentic-harness.excalidraw`.
- The local preview page renders the Excalidraw-derived diagram without a blank
  canvas.
- A fixture address run produces ordered events for planner, parcel, zoning,
  scenario, calculation, comp-support, evidence-review, and report stages.
- The generated memo separates verified facts, calculated outputs, underwriting
  assumptions, strategy hypotheses, warnings, and next verification steps.
- `plotlot runs events <run-id>` reads the persisted event timeline.
- `plotlot runs replay <run-id>` replays the persisted event timeline.
- A queued local worker path persists the same run state and event trace as the
  synchronous path.
- Report finalization is blocked when unsupported claims, mock production
  evidence, or failed verification are present.
- Existing chat/web lookup surfaces execute matching harness tools through the
  shared tool router instead of parallel source-lane logic.
- A workbench/manual QA pass shows progress, evidence, blocked states, and the
  cited memo for the MVP lane.

## First Implementation Slice

Start with the narrowest slice that proves the harness pattern:

```text
Miami Gardens or Broward fixture address
  -> parcel/jurisdiction
  -> ordinance evidence
  -> by-right or build-to-rent scenario hypothesis
  -> max-unit/density, NOI, and residual-land-value calculation
  -> comp-support evidence placeholder or fixture comp set
  -> evidence reviewer
  -> cited feasibility memo
```

This slice may use fixtures where external systems are unavailable, but fixture
evidence must be labeled preliminary and must not pass as production evidence.
