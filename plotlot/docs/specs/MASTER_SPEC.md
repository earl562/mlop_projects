# Master Spec — PlotLot South Florida AI Zoning Harness

This is the driving specification for the PlotLot South Florida AI zoning and
land-use consultant harness. It supersedes the phase ordering of the prior
prd.json (which remains as per-story progress tracking) with a spec-first,
event-driven, TDD/BDD-driven structure.

Full spec text: see the user-supplied master spec (22 sections). Key invariants:

## Non-negotiable engineering rules
1. Specification first — no major behavior until spec/event/domain/API/test written.
2. Event contract before code.
3. TDD before implementation (failing tests first).
4. BDD for product behavior.
5. One execution path — all tool calls via HarnessRuntime.
6. Evidence-backed output only — no material claim without evidence_ids.
7. Durable state — persist runs/events/tool calls/evidence/reports.
8. South Florida first (Miami-Dade, Broward, Palm Beach + incorporated cities).
9. Provider-agnostic ingestion (Municode, eCode360, American Legal, Code Publishing,
   municipal.codes, enCodePlus, official PDF/HTML, ArcGIS, manual).
10. Legal/product safety — every ordinance citation: retrieved_at, source_url,
    publisher, jurisdiction, caveat requiring municipal confirmation.
11. No hallucinated zoning — "unknown / requires verification" not guess.

## First paid feature slice
South Florida Zoning Feasibility Memo — given an address/parcel + intended use,
produce a cited zoning feasibility memo answering: jurisdiction, zoning district,
code source, use permission, dimensional standards, density/FAR/height/setback/
parking, overlays/risks, missing facts, next due-diligence actions, evidence IDs.

## Phase ordering (supersedes prd.json phases)
- PHASE 0 — Planning/spec files (specs + BDD; no production code)
- PHASE 1 — Database and domain models
- PHASE 2 — Source authority registry
- PHASE 3 — Snapshot layer
- PHASE 4 — Parsing and adapters
- PHASE 5 — Ingestion pipeline
- PHASE 6 — Harness run service
- PHASE 7 — API/MCP/PI.dev parity
- PHASE 8 — Billing/security hardening
- PHASE 9 — Frontend workbench
- PHASE 10 — Gold-set and production readiness

## Acceptance (release gate)
Existing lookup/chat not broken; all tool calls via HarnessRuntime; server-authored
ToolContext; durable workspace/project/site/analysis; South FL source authorities
queryable; ingestion stores raw snapshots before parsing + idempotent; chunks link
to source authority + snapshot; search results include evidence_id; reports reject
uncited material claims; external writes require approval; REST/MCP contract-compatible;
billing limits on harness runs; events persisted + streamable; gold-set passes for
priority South FL jurisdictions; system says "unknown / needs verification" not guess.
