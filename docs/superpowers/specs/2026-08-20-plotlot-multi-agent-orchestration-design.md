# PlotLot Multi-Agent Orchestration Design

**Date:** 2026-08-20  
**Branch:** `cpt-pro`  
**Status:** Approved for implementation by the repository owner

## Objective

Make PlotLot multi-agent without creating another disconnected execution engine. One coordinator decomposes a user objective into specialist tasks, while every specialist remains constrained to deterministic tools executed through the canonical `HarnessRuntime`.

The first supported workflow intents are:

- `site_feasibility`
- `lead_sourcing`
- `deep_underwriting`

## Design Decision

Use a coordinator-and-specialists architecture.

Specialists are typed capability manifests, not independent chatbots or unrestricted LLM loops. They do not own credentials, network clients, policy, durable state, or calculation logic. The coordinator owns dependency scheduling, argument binding, concurrency, status aggregation, and evidence handoff. `HarnessRuntime` continues to own tool authorization, budgets, approvals, and tool events.

```text
Workflow request
      |
      v
MultiAgentPlanner
      |
      v
AgentPlan (DAG)
      |
      v
MultiAgentCoordinator
  - dependency scheduling
  - bounded parallel waves
  - output bindings
  - evidence aggregation
  - run/agent/task status
      |
      v
HarnessRuntime
  - canonical tool contract
  - static risk class
  - budget / approval policy
  - deterministic handler
  - tool/evidence/artifact events
```

## Specialist Agents

### `site_identity`

Purpose: establish the target site and authoritative parcel identity.

Allowed tools:

- `geocode_address`
- `lookup_property_info`

### `zoning_research`

Purpose: retrieve governing ordinance and public-data evidence.

Allowed tools:

- indexed ordinance search/fetch
- live code-provider discovery/search
- open-data layer discovery
- last-resort web research

### `feasibility`

Purpose: produce the deterministic site-feasibility decision.

Allowed tools:

- `analyze_property`
- `calculate`

### `underwriting`

Purpose: evaluate user-supplied entitlement and financial scenarios.

Allowed tools:

- `analyze_upzoning`
- `calculate`

### `sourcing`

Purpose: search, filter, summarize, and screen acquisition candidates.

Allowed tools:

- `search_properties`
- `filter_dataset`
- `get_dataset_info`
- `screen_properties`

### `reporting`

Purpose: create evidence-backed internal artifacts and approval-gated exports.

Allowed tools are explicitly declared by static risk class. The first workflow templates invoke only `generate_document`; external creation and sending remain approval-gated runtime capabilities.

## Workflow Plans

### Site Feasibility

```text
identity.geocode
      |
      +----------------------+
      v                      v
identity.parcel       feasibility.analyze
      |                      |
      v                      |
zoning.research              |
      +----------------------+
                 |
                 v
        report.generate (optional)
```

`identity.parcel` and `feasibility.analyze` run concurrently after successful geocoding. Zoning research waits for the parcel district. Reporting waits for the research chain to terminate but requires the primary feasibility analysis to succeed.

### Lead Sourcing

A market search and a supplied-address screen are independent and may run concurrently. Dataset inspection waits for market search completion. The coordinator never silently expands a supplied list beyond the runtime screening cap.

### Deep Underwriting

The site-feasibility plan is extended with `underwriting.upzoning`. Verified lot area and by-right yield are bound from the feasibility result unless the user explicitly supplies overrides. The planner does not invent a target yield or finished-lot value; missing decision inputs become open questions.

## Output Binding

Tasks may bind arguments from prior structured results by an explicit source task and dot path. A binding source must be a declared dependency. Missing required values skip the dependent task and surface an actionable review item; they never become model guesses.

Examples:

- parcel county ← `identity.geocode.result.county`
- ordinance query ← `identity.parcel.result.zoning_code` + controlled suffix
- upzoning lot area ← `feasibility.analyze.lot_size_sqft`
- baseline yield ← `feasibility.analyze.by_right.max_units`

## Concurrency

The coordinator executes dependency-ready tasks in bounded parallel waves. Concurrency is deterministic at the plan level and never bypasses runtime policy. Stateful dataset operations remain sequenced by dependencies and share the same `run_id`.

## Evidence and Artifacts

Every task result is inspected for canonical evidence identifiers. The reporting agent receives the complete completed research chain, including transitive geocode and parcel evidence—not only direct dependencies.

An evidence-backed report is skipped when no evidence IDs exist. A report may wait for optional research to finish, but it cannot run if the primary analysis failed.

## Status Semantics

Task status:

- `completed`
- `failed`
- `blocked`
- `pending_approval`
- `skipped`

Run status:

- `completed` — all required work completed and no review item remains
- `needs_review` — a useful result exists but a dependency, optional research task, or required assumption needs attention
- `pending_approval` — at least one governed action requires durable approval
- `failed` — no required decision path completed

A handler payload that reports `error`, `not_found`, `no_results`, `not_configured`, `empty`, `unsupported`, or `unavailable` is not treated as successful merely because the runtime call itself completed.

## API Surface

The first compatibility surface is mounted below the authenticated harness-job router:

- `GET /api/v1/harness/jobs/agent-runs/specialists`
- `POST /api/v1/harness/jobs/agent-runs/plan`
- `POST /api/v1/harness/jobs/agent-runs`

The plan endpoint is side-effect free. The execution endpoint creates one shared `ToolContext`, validates claimed approvals against durable records, and fails closed if approval storage is unavailable.

This synchronous surface is an executable vertical slice. Durable queue execution, replay, SSE streaming, and workbench integration build on the same request, plan, result, and event contracts rather than introducing another orchestrator.

## Security and Trust Invariants

- An agent cannot call a tool outside its allowlist.
- Tool risk class comes only from the canonical registry.
- All tool calls go through `HarnessRuntime`.
- Claimed approval IDs are never trusted without durable validation.
- Missing evidence or assumptions become explicit review items.
- Deterministic calculations remain tools, not model reasoning.
- External writes remain approval-gated.
- The coordinator never fabricates market coverage or parcel facts.

## Non-Goals of This Slice

- Independent long-running LLM processes per specialist.
- Agent-to-agent free-form conversation.
- Automatic external outreach or document publication.
- Replacing the durable harness job queue.
- Rebuilding the existing county adapters.
- Redesigning the workspace UI in the same commit.
- Reactivating the legacy combined LOI/PSA/pro-forma chat dispatcher.

## Definition of Done

1. Six specialist agents have explicit workflow and tool boundaries.
2. The planner produces validated acyclic plans for all three workflows.
3. Independent specialist tasks execute concurrently with a hard concurrency bound.
4. Output bindings and missing-input behavior are deterministic.
5. Policy and approvals remain owned by `HarnessRuntime`.
6. Evidence flows across the complete research chain into optional reporting.
7. The authenticated REST surface exposes specialist discovery, planning, and execution.
8. Focused tests, full backend gates, frontend gates, and end-to-end CI are verified on `cpt-pro`.
