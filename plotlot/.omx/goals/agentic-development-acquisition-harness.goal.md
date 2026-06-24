/goal

You are Codex working in `earl562/plotlot-v2` on branch
`feature/deal-analysis-pipeline`.

Build PlotLot into an AI Land Developer Harness for real estate developers,
land-acquisition investors, infill builders, build-to-rent operators,
entitlement investors, land wholesalers, and small commercial developers.

PlotLot should help a user decide:

- What can this parcel support?
- Can I build the concept I have in mind?
- What is the supportable land value?
- What is the highest safe offer?
- What assumptions drive the decision?
- Which facts are sourced versus assumed?
- What risks or diligence items should stop the deal?
- What acquisition, lender, or investor memo can be generated from the run?

## Source-of-truth instruction

Do not use existing PlotLot PRDs or old branch notes as the primary design
source. Use them only as historical context after you inspect the current branch.

The primary domain methodology for this goal is Rehab Valuator's ground-up
development material:

- `https://rehabvaluator.com/rehabbing-ground-up`
- `https://rehabvaluator.com/value-vacant-land`
- `https://rehabvaluator.com/building-apartments`
- `https://rehabvaluator.com/development-feasibility-lender-proposal-rental-comps`
- `https://rehabvaluator.com/development-project-management-training`

Treat the Rehab Valuator material as an operating framework, not merely RAG
content. Convert the workflow into repeatable skills, deterministic calculators,
assumption schemas, evidence requirements, and report artifacts.

## Mandatory research and planning TODO

Before broad implementation, perform a fresh research and repo-analysis pass.
The current working goal is allowed to guide implementation, but the final
Codex `/goal` prompt must be regenerated after research is complete.

Research TODO:

1. Deep research the Rehab Valuator ground-up development workflow.
2. Decompose the workflow into developer jobs-to-be-done.
3. Inspect the current branch implementation, especially the deal-analysis,
   calculator, agent-run, evidence, frontend, and harness files.
4. Identify gaps between current PlotLot and a true AI land-developer harness.
5. Produce a refreshed `/goal` prompt after research and branch analysis.
6. Only then broaden implementation beyond the first deterministic calculator
   and market-profile slices.

## Current implementation slice to preserve

The current branch already contains a deal-analysis pipeline. This goal adds a
new deterministic foundation that should be preserved and extended:

- `plotlot/src/plotlot/pipeline/development_land_offer.py`
- `plotlot/src/plotlot/pipeline/development_market_profile.py`
- `plotlot/src/plotlot/pipeline/development_scenario_calculator.py`
- `plotlot/tests/unit/test_development_land_offer.py`
- `plotlot/tests/unit/test_development_market_profile.py`
- `plotlot/tests/unit/test_development_scenario_calculator.py`

This foundation is intentionally zero-I/O. It should become the calculation
kernel that the agent, API, and frontend call into.

## Product thesis

The core workflow is:

```text
Address / Parcel
  -> parcel + jurisdiction + zoning facts
  -> dimensional standards + max residential units or commercial GLA
  -> development concept
  -> location-specific assumptions
  -> asset-class-specific underwriting
  -> as-built value or net sellout value
  -> total development cost excluding land
  -> max supportable land price
  -> risk-adjusted offer range
  -> evidence-backed acquisition memo
```

The foundational underwriting logic should mirror the development workflow:

1. Run a density or capacity study.
2. Determine as-built value or net sellout value.
3. Back out required developer profit, sweat equity, or target margin.
4. Back out hard costs, soft costs, contingency, financing, carrying, closing,
   reserves, impact fees, and risk buffer.
5. Arrive at max supportable land purchase price.
6. Present conservative, base, and aggressive scenarios.
7. Generate a memo with sources, assumptions, calculations, risks, and next
   steps.

## Non-negotiable product rules

Always separate these categories in data models, API responses, UI, and reports:

```text
Fact:
  Source-backed parcel, zoning, jurisdiction, ordinance, comp, market, or
  physical site information.

Assumption:
  User-provided or defaulted value such as rent, sale price, cap rate, hard
  cost, soft cost, vacancy, expense ratio, contingency, financing, or impact
  fee.

Calculation:
  Deterministic formula output, with inputs and formula version recorded.

Recommendation:
  Downstream interpretation such as recommended offer range, feasibility
  conclusion, or next action.
```

The LLM may interpret, explain, orchestrate, draft memos, and ask for missing
inputs. It must not freehand zoning capacity or underwriting math.

## Location is first-class

Deals are variable depending on location. The harness must not share one default
set across Miami, San Diego, the Bay Area, Charlotte, Las Vegas, or unknown
markets.

Every scenario should carry a market profile or explicit user assumptions.
Market profiles should influence starter defaults for:

- residential hard cost psf
- commercial hard cost psf
- soft cost percentage
- contingency percentage
- financing and closing cost assumptions
- impact fees
- risk buffer
- cap rate
- desired sweat equity / required margin
- recommended offer discount
- entitlement risk
- evidence requirements

Every default must be labeled as an assumption until replaced by sourced local
bids, comps, fee schedules, or user-provided values.

## Residential and commercial calculations are different

Do not force all deals through unit-count math.

Residential rental calculations:

```text
Gross Scheduled Rent = units * average_monthly_rent * 12
Vacancy Loss = Gross Scheduled Rent * vacancy_rate
Other Income = Gross Scheduled Rent * other_income_rate
Effective Revenue = Gross Scheduled Rent - Vacancy Loss + Other Income
Operating Expenses = Effective Revenue * operating_expense_ratio
NOI = Effective Revenue - Operating Expenses
As-Built Value = NOI / cap_rate
Max Land Price = As-Built Value - required_margin - costs_before_land
```

Residential for-sale calculations:

```text
Gross Sellout Value = units * average_sale_price_per_unit
Selling Costs = Gross Sellout Value * selling_cost_rate
Net Sellout Value = Gross Sellout Value - Selling Costs
Max Land Price = Net Sellout Value - required_profit - costs_before_land
```

Commercial lease calculations:

```text
Base Rent = commercial_gla_sqft * annual_rent_psf
Vacancy Loss = Base Rent * vacancy_rate
Other Income = Base Rent * other_income_rate
Effective Revenue = Base Rent - Vacancy Loss + Other Income
Operating Expenses = Effective Revenue * operating_expense_ratio
NOI = Effective Revenue - Operating Expenses
As-Built Value = NOI / commercial_cap_rate
Max Land Price = As-Built Value - required_margin - costs_before_land
Land Value PSF = Max Land Price / commercial_gla_sqft
```

Commercial outputs should show value per buildable/leasable square foot.
Residential outputs should show value per unit/door.

## Harness skills to implement

Create or extend repo-owned skill/playbook specs for:

- `quick_zoning_feasibility`
- `density_study`
- `commercial_capacity_study`
- `market_profile_selection`
- `residential_rental_underwriting`
- `residential_for_sale_underwriting`
- `commercial_lease_underwriting`
- `max_land_offer`
- `scenario_comparison`
- `acquisition_memo`
- `lender_package`
- `due_diligence_checklist`

Each skill must define:

- purpose
- required inputs
- optional inputs
- calculators used
- output schema
- risk class
- evidence requirements
- evaluation criteria

## Runtime integration

Extend the existing PlotLot harness rather than replacing current MVP behavior.

Required runtime behavior:

- Accept a project/site/scenario request.
- Use existing zoning/density output when available.
- Use deterministic underwriting calculators for scenario math.
- Record assumptions and calculations as evidence-linked run artifacts.
- Emit structured events such as `run_started`, `calculation_completed`,
  `evidence_recorded`, `approval_required`, `run_completed`, and `run_failed`.
- Preserve existing `/api/v1/analyze`, `/api/v1/analyze/stream`, `/api/v1/chat`,
  portfolio, document, geometry, and render behavior.

## Evidence requirements

Every trust-critical claim must have an evidence or assumption record.
Evidence items must capture:

- source type
- source name or tool name
- retrieved/generated timestamp
- confidence when applicable
- linked workspace/project/site/run/scenario
- claim category: fact, assumption, calculation, recommendation
- source reference or calculation formula

Reports and memos may cite recorded evidence IDs and labeled assumptions only.

## Governance requirements

Default policy:

- Read-only parcel/zoning/ordinance/property tools: auto-allow.
- Deterministic calculators: auto-allow.
- Internal memo/report draft creation: auto-allow or `WRITE_INTERNAL`.
- Google Docs/Sheets creation, CRM writes, email sends, dataset exports, calendar
  actions: approval-gated `WRITE_EXTERNAL`.
- Code execution, broad scraping, or sandbox execution: approval-gated or blocked
  unless explicitly configured.

Add tests proving external-write tools cannot execute directly from agent, chat,
or tool paths without a governance decision.

## API surface to build after calculator kernel

Add minimal backend endpoints. Names may adapt to existing route conventions, but
preserve this capability set:

```text
POST /api/v1/projects/{project_id}/development-scenarios
GET  /api/v1/projects/{project_id}/development-scenarios
GET  /api/v1/development-scenarios/{scenario_id}
POST /api/v1/development-scenarios/{scenario_id}/run
GET  /api/v1/development-scenarios/{scenario_id}/runs
GET  /api/v1/development-runs/{run_id}
GET  /api/v1/development-runs/{run_id}/evidence
POST /api/v1/development-runs/{run_id}/memo
```

If workspace/project/site persistence is incomplete, use a thin compatibility
seam and fixtures. Do not fake durable memory in the API contract.

## Frontend MVP surface

Add the smallest frontend surface that proves the workflow without redesigning
the whole app:

- scenario assumptions form/editor
- market profile selector
- residential rental / residential sale / commercial lease selector
- conservative/base/aggressive scenario selector
- development metrics summary card
- max land offer result card
- residential per-unit and commercial per-buildable-sf display
- evidence rail or evidence list
- acquisition memo preview section
- approval panel hook for external document/export actions

Keep existing home lookup/chat UI working.

## Acquisition memo generation

Implement a generated memo structure, even if the first version is Markdown/JSON
only.

Required sections:

1. Executive summary
2. Parcel and jurisdiction facts
3. Zoning capacity and governing constraint
4. Development concept and unit mix or commercial GLA
5. Rent, sale, or lease assumptions
6. Cost assumptions
7. Financing assumptions
8. Development metrics
9. Max land offer and recommended offer range
10. Risks and open diligence items
11. Evidence/source appendix

The memo must label facts, assumptions, calculations, and recommendations.

## Testing requirements

Add deterministic tests. Do not require live external API credentials for new
core tests.

Required tests:

- location market profile selection tests
- residential rental calculator tests
- residential for-sale calculator tests
- commercial lease calculator tests
- max land offer tests for positive and negative residual value
- invalid/missing assumption warning tests
- scenario model validation tests
- runtime event emission tests
- evidence item creation tests for fact, assumption, calculation, recommendation
- governance tests blocking or approval-gating external writes
- API route tests for scenario create/run/evidence/memo
- frontend fixture-backed UI tests for assumptions, result card, evidence rail,
  and memo preview

Run or document results for:

```bash
cd plotlot
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/plotlot/ --no-error-summary
uv run pytest tests/unit -q
cd frontend && npm run lint && npm run test:ui
```

If pre-existing failures exist, document them clearly with evidence that the new
feature did not cause them.

## Evaluation fixtures

Add or extend `plotlot-bench` or golden fixtures for at least five
acquisition-development cases:

1. stabilized residential rental multifamily base case
2. conservative residential rental case with high cap rate / higher costs
3. aggressive residential rental case with lower cap rate / lower costs
4. residential for-sale townhouse or duplex case
5. commercial lease case based on GLA and annual rent psf
6. infeasible case where costs exceed value and max land price is negative

Each case should include input assumptions, expected metrics, expected max land
price, expected warnings, and expected memo sections.

## Definition of done

This goal is complete when:

- Existing Lookup and Agent behavior remain intact.
- A user or test can create a location-aware development scenario for a site.
- The system can run residential rental, residential sale, and commercial lease
  underwriting through deterministic calculators.
- The system returns max supportable land price and recommended offer range.
- Residential outputs include per-unit metrics.
- Commercial outputs include per-buildable-square-foot metrics.
- Results separate facts, assumptions, calculations, and recommendations.
- Evidence and assumptions are attached to runs and memos.
- External writes are approval-gated.
- Unit tests and relevant frontend tests are added or updated.
