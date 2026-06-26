# Spec — Agentic Zoning & Land-Acquisition Harness

**Job to be Done:** A land developer/acquirer asks PlotLot a zoning or underwriting
question about any parcel (including jurisdictions never ingested), and gets a
typed, evidence-backed answer — verified facts distinct from assumptions distinct
from hypotheses — with sources, calculations, and next-verification-steps. The
agent discovers missing data, ingests it under governance, and never blurs the
verified-fact/assumption boundary (Kleyman boundary).

## Acceptance Criteria (behavioral outcomes — the WHAT, not the HOW)

1. **Never-ingested jurisdiction:** Given an address in a small town PlotLot has
   never ingested, the agent discovers the authoritative ordinance source,
   ingests it, and produces typed `zoning.*` claims with `origin=local_authority`
   and `source_url` — OR escalates honestly with a documented next step. It must
   never fabricate zoning values or present an assumption as a verified fact.

2. **Verified-fact vs assumption boundary:** Every claim the agent produces
   carries a `kind` (verified_fact / assumption / hypothesis / calculation /
   contradiction) and an `origin`. A `zoning.*` claim with `origin=rehabvaluator_concept`
   or a `cost.*` claim with `kind=verified_fact` is a validation failure, not a
   warning.

3. **Kleyman 8-step ordering:** The planner refuses to activate step 5 (residual
   land value) when any `zoning.*`/`parcel.*` claim required by step 2 is not
   `kind=verified_fact`. Density study precedes land valuation, enforced by code.

4. **Residential vs commercial divergence:** Step 3 (stabilized value) routes to
   the income approach (NOI/cap) for ≥5 units and the comp approach (ARV) for
   ≤4 units — a typed method dispatch, not a prompt hope.

5. **Comps are evidenced:** Comps claims carry `source_url` + `origin`. ArcGIS
   county sales = `local_authority`. Scraped comps (if any) = `unknown` with
   confidence ≤ 0.5, rendered amber, never as verified facts.

6. **Overlooked-value hypotheses:** Opportunity skills (lot_split_feasibility, etc.)
   produce `kind=hypothesis` claims with `next_verification_step` populated.
   Entitlement upside is never presented as guaranteed.

7. **Report as claim projection:** The report renders verified facts (neutral),
   assumptions (amber per DESIGN.md), and hypotheses (distinct treatment) from the
   ClaimLog. It fails validation if it omits evidence_ids for material claims,
   hides contradictions, or presents a missing zoning fact as known.

8. **Ship-gate scenario:** A never-ingested small town → agent discovers source →
   governs ingestion → produces typed claims → runs 8 steps → emits report with
   evidence IDs + next-verification-steps OR escalates honestly. End-to-end, live.

## Source boundary (Kleyman / Rehab Valuator corpus)

Rehab Valuator transcripts are authoritative for: developer underwriting concepts,
the 8-step workflow, financing logic, land valuation patterns, lender-package
structure. They are NOT authoritative for: parcel facts, local zoning, ordinances,
entitlement outcomes, local costs, local rents, cap rates, lender terms, municipal
rules. The `origin` field enforces this: a concept from the corpus must be
`origin=rehabvaluator_concept`, never `origin=local_authority`.

## Required tests (derived — build mode cannot claim passes:true without these)

- Boundary invariant tests: zoning.*+non-local-authority raises; cost.*+verified_fact raises.
- Planner ordering test: step 5 blocked when zoning.* not verified.
- Step-3 branch test: income vs comp approach on unit_count.
- Comps provenance test: every comp has source_url + origin.
- Report validator test: fails on missing evidence_ids / blurred boundaries.
- Live end-to-end ship-gate test (PLOTLOT_LIVE_TESTS=1): never-ingested town → typed claims.
