# Brief — PlotLot Agentic Zoning & Land-Acquisition Harness

## Job to be Done
A land developer/acquirer asks PlotLot a zoning/underwriting question about any
parcel (including jurisdictions never ingested) and gets a typed, evidence-backed
answer — verified facts distinct from assumptions distinct from hypotheses — with
sources, calculations, and next-verification-steps. The agent discovers missing
data, ingests it under governance, and never blurs the verified-fact/assumption
boundary (Kleyman boundary).

## Source of truth
- Spec: `specs/agentic-zoning-harness.md` (8 behavioral acceptance criteria + 6 required tests).
- Task decomposition: `prd.json` (63 stories, phases 1-14, each with acceptanceCriteria + passes flag).
- Operational rules: `AGENTS.md` (never `git add -A`; explicit paths only; Earl Perry commits; never assert from training data; ship tests with every change).
- Backpressure gate: `make verify-local` (ruff + pytest + frontend lint/tsc/build). MUST be green before any checkpoint.
- Progress log: `progress.txt` (append-only; `## Codebase Patterns` curated at top).

## Completion gate (the aggregate objective)
ALL 63 stories in prd.json reach `passes: true` AND the spec's 8 acceptance
criteria are proven by the 6 required tests (boundary invariants, planner
ordering, step-3 branch, comps provenance, report validator, live ship-gate).
A module that compiles + passes its own tests but isn't wired to its consumer is
NOT done (connection criteria are not optional).

## Durable constraints
- Verified-fact vs assumption boundary enforced in CODE, not prompts: a `zoning.*`
  claim with non-local-authority origin, or a `cost.*` claim with kind=verified_fact,
  is a validation FAILURE.
- Kleyman 8-step ordering enforced: step 5 (residual land value) blocked unless
  required zoning.*/parcel.* claims are kind=verified_fact.
- Residential vs commercial: step 3 routes income approach (≥5 units) vs comp
  approach (≤4 units) via typed method dispatch.
- Comps evidenced: every comp carries source_url + origin; scraped = unknown,
  confidence ≤ 0.5, amber, never verified.
- Opportunity skills emit kind=hypothesis with next_verification_step; never
  presented as guaranteed.
- Report is a ClaimLog projection; validator fails on missing evidence_ids,
  hidden contradictions, or blurred boundaries.
- Rehab Valuator corpus is authoritative for CONCEPTS only (origin=
  rehabvaluator_concept), never for parcel/zoning/local facts.

## Execution model
ulw-loop aggregate goal. pi is single-context (no spawn_agent), so the agent
conducts + implements + QAs directly in one context. One story per cycle
(ralph discipline: fresh context per story is emulated by strict one-story
scope). Real evidence required for every criterion — tests alone never prove
done; for features with live behavior, a live/integration test pins it.
Durable across sessions via `.omo/ulw-loop/{goals.json,ledger.jsonl}`.
