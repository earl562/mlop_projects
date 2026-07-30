# PlotLot Agentic Harness System Design

Date: 2026-06-29

This note turns the current Excalidraw lookup sketch into a reliability-oriented system design for PlotLot as an agentic land-use and site-feasibility harness. It now folds in the Rehab Valuator ground-up development corpus as a concept source for developer feasibility workflows while preserving the hard boundary that local parcel, zoning, market, cost, and lender facts must come from evidence.

The core product spine should stay simple:

```text
Workspace -> Project -> Site -> Analysis -> Evidence -> Report -> Document / Action
```

Behind that spine, autonomous work should run through a governed harness:

```text
Request -> Run Plan -> Skill Lane -> Agent Workers -> Deterministic Tools -> Evidence Ledger -> Reviewer -> Report / Action
Verified Facts -> Scenario Hypotheses -> Calculations -> Assumptions -> Recommendation / Repair Step
```

## Design Thesis

PlotLot should not make a single "super agent" responsible for zoning, GIS, comping, underwriting, and reporting. That creates brittle context, unclear blame, and poor retry behavior.

Instead, PlotLot should operate as a durable harness where agents are bounded workers:

- Planner Agent: turns the user goal into a typed run plan.
- Parcel Agent: resolves address, parcel, owner, geometry, jurisdiction, lot size, and base zoning.
- Zoning Agent: retrieves ordinance sections, use permissions, dimensional standards, overlays, setbacks, and max units.
- Comping Agent: gathers comparable sales/listings through approved sources, browser automation, and structured capture.
- Scenario Agent: turns verified buildability into explicit by-right, build-to-rent, build-to-sell, multifamily, lot-split, upzoning, land-flip, or fallback hypotheses.
- Market and Comps Agent: gathers comparable sales, rent support, and source captures through approved data lanes and browser evidence.
- Feasibility Agent: runs deterministic density, massing, residual land value, NOI, DSCR, yield-on-cost, cash-on-cash, and scenario calculations.
- Evidence Reviewer: checks every claim against citations, freshness, and contradiction rules.
- Report Agent: produces user-facing feasibility memos, lender packages, and next-action drafts only after evidence and review gates pass.

Agents reason and synthesize. Tools retrieve facts, mutate state, calculate, browse, and persist evidence.

## Target Architecture Layers

1. Product surfaces
   - Web workbench
   - API
   - MCP adapter
   - Background job and run views

2. Governance and run control
   - Workspace auth and tier policy
   - Run state machine
   - Queue with retries, idempotency keys, and cancellation
   - Tool approval gates
   - Rate limits and vendor budget controls

3. Skill lanes and agents
   - Zoning analysis lane
   - Site selection lane
   - Comps lane
   - Underwriting lane
   - Developer scenario lane
   - Document/report lane
   - Outreach lane

4. Deterministic tools
   - Geocode and parcel lookup
   - ArcGIS/open-data feature queries
   - Municode/local ordinance search and fetch
   - Browser comp capture
   - Listing/comparable candidate ranking
   - Density, residual land value, NOI/DSCR, yield-on-cost, and underwriting calculators
   - Report/document builders

5. Durable state and operations
   - Postgres and pgvector
   - Evidence ledger
   - Assumption register
   - Formula/input trace
   - Run/event log
   - Artifact store
   - Workspace memory
   - Verification/eval store
   - Health checks and observability

## Rehab Valuator Boundary

Rehab Valuator's Rehabbing & Ground Up Development Training should influence the shape of PlotLot's development analysis, not the factual answer for any parcel.

Use the corpus for:

- scenario templates: by-right development, build-to-rent, build-to-sell, duplex/quad, missing-middle, multifamily, mixed-use, land flip, lot split, assemblage, adaptive reuse, seller contingency, and upzoning;
- calculator prompts: product/unit mix, stabilized value, sale value, hard costs, soft costs, financing costs, maximum land basis, DSCR, cash-on-cash, yield-on-cost, and residual land value;
- report structure: verified facts, calculated outputs, underwriting assumptions, risks, mitigants, source IDs, and next verification steps;
- opportunity hypotheses: current verified condition versus proposed scenario, entitlement path, upside mechanism, fallback by-right exit, time/cost/risk assumptions, and repair steps.

Do not use the corpus for:

- parcel identity, jurisdiction, zoning district, allowed uses, density, height, setbacks, parking, overlays, subdivision rules, or entitlement approvals;
- local rents, local costs, cap rates, lender terms, loan approval likelihood, or market value;
- exact quotations unless the transcript segment has been separately checked.

## Lookup-To-Harness Flow

1. User enters an address, target search, or deal thesis.
2. API gateway attaches workspace, role, plan tier, and policy.
3. Harness creates an analysis run with a stable run id.
4. Planner Agent selects a skill lane and builds a step plan.
5. Parcel Agent resolves address, parcel, jurisdiction, owner, geometry, and base zoning.
6. Zoning Agent fetches authoritative ordinance evidence and calculates allowed uses/units with deterministic calculators.
7. Scenario Agent compares verified by-right conditions with explicit development hypotheses from the concept corpus.
8. Market and Comps Agent gathers comparable sales, rent support, and browser/source captures when the scenario needs market evidence.
9. Feasibility Agent runs deterministic scenario calculations and stores formulas, inputs, evidence IDs, assumptions, and warnings.
10. Evidence Reviewer blocks unsupported facts, hidden assumptions, guaranteed entitlement upside, and weak lender/deal claims.
11. Report Agent generates a cited feasibility memo, lender package, or repair-step plan.

## Reliability Rules

- Every run is resumable from persisted state, not from model memory.
- Every tool call has a typed contract, timeout, retry policy, and idempotency key.
- Every claim in a report links to an evidence item or is labeled as an assumption.
- Every scenario has a current verified condition, proposed condition, fallback exit, and next verification step.
- Every calculation stores formula, inputs, source IDs, assumption IDs, warning rules, and reproducible output.
- Training concepts are tagged as concept references and never promoted to local authority.
- Browser automation is a last-mile adapter, not the system of record.
- Vendor failures degrade into partial results with explicit confidence and missing-data notes.
- Human approval is required for costly tools, external writes, emails, CRM mutation, or uncertain legal/zoning conclusions.
- Long-running work is queue-backed, observable, cancellable, and replayable.

## Blockers And Pitfalls To Resolve

| Pitfall | Why it hurts | System control |
| --- | --- | --- |
| Single giant prompt/tool catalog | Unreliable planning, hard debugging | Skill lanes with scoped toolsets |
| Browser comping as primary truth | Sites change, block automation, and produce inconsistent DOM | Structured sources first, browser capture as evidence with screenshots |
| Unsupported zoning conclusions | Trust and liability risk | Evidence ledger, citation validator, reviewer gate |
| No persisted run state | Failed runs cannot resume | Run state machine plus event log |
| Retrying non-idempotent tools | Duplicate records, charges, or messages | Idempotency keys and side-effect approval policy |
| Plan-tier ambiguity | Cost blowups and entitlement bugs | Gateway policy before routing/tools |
| Stale municipal data | Wrong feasibility answer | Source freshness metadata and revalidation rules |
| Hidden assumptions | Users overtrust outputs | Assumption register in reports |
| Rehab Valuator treated as local authority | Training concepts could become false parcel facts | Source-lane boundary: concept_reference only |
| Guaranteed upzoning or "free land" claims | Entitlement upside is speculative and approval-dependent | Current/proposed/fallback scenario model plus reviewer fail rule |
| Land-offer math without buildability proof | Residual land value can look precise while zoning is unknown | Require official buildability evidence before recommendation |
| Lender package optimism | Financing terms vary by lender/deal/market | Labeled lender assumptions, DSCR/LTC/LTV trace, no approval claims |
| Weak evals | Agents regress silently | Golden address suites, replay, mutation tests, and review checks |

## MVP Cut

The first production-worthy lane should be:

```text
Address lookup -> parcel/jurisdiction -> zoning/ordinance evidence -> scenario hypothesis -> density/residual-land-value/NOI calculations -> comp support -> evidence review -> cited feasibility memo
```

Do not start with full CRM/outreach autonomy. Start with read-only analysis plus draft artifacts. Add external writes only after evidence, approvals, and replay are stable.

## Excalidraw Companion

Import this file into Excalidraw:

```text
docs/architecture/excalidraw/plotlot-agentic-harness.excalidraw
```

Use this implementation goal to drive the work from the visual design:

```text
docs/goals/excalidraw-agentic-harness.goal.md
```

The canvas is intentionally layered so you can discuss the system visually with a cofounder:

- left to right: user request to final report/action;
- top to bottom: product/governance, bounded agents, Rehab Valuator concept lane, deterministic tools, durable state/ops;
- red risk box: reliability blockers and controls.
