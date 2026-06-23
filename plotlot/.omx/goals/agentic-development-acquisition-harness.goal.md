/goal

You are Codex working in the `earl562/plotlot-v2` repository on branch `feature/deal-analysis-pipeline`. Implement the next PlotLot product slice: an agentic development-acquisition harness for real estate developers and land-acquisition investors.

This is not a generic chatbot feature. PlotLot must become a governed, evidence-backed, workspace-native feasibility and underwriting harness that helps a user decide:

- What can this parcel support?
- Should I buy it?
- What is the highest safe land offer?
- What assumptions drive the answer?
- What evidence supports the recommendation?
- What report or lender/investor package can be generated from the run?

## Existing repo context to respect

Read and follow these existing product/contracts before editing code:

- `plotlot/docs/PLOTLOT_FLOW_CONTRACT.md`
- `plotlot/.omx/plans/prd-plotlot-workspace-harness.md`
- `plotlot/.omx/plans/prd-agentic-land-use-harness.md`
- `.claude/rules/plotlot-pipeline.md`
- `.claude/rules/plotlot-data-models.md`
- `.claude/rules/plotlot-chat.md`

Preserve the current product split:

- `Lookup` = fast address-driven feasibility answer.
- `Agent` = persistent, higher-capability decision-support workspace.

Do not turn `Lookup` into free-form chat. Do not bury trust-critical facts under optional downstream analysis. Do not market durable memory unless the data layer is actually durable.

## Product thesis

Implement the first durable slice of this workflow:

```text
Address / Parcel
  -> parcel + jurisdiction + zoning facts
  -> dimensional standards + max unit capacity
  -> development concept / unit mix
  -> rent or sales assumptions
  -> hard costs + soft costs + contingency
  -> financing assumptions
  -> as-built value
  -> total development cost
  -> max supportable land price
  -> risk-adjusted offer range
  -> evidence-backed acquisition memo
```

The foundational underwriting logic should mirror the real estate development workflow:

1. Run a density study.
2. Determine as-built value.
3. Back out desired developer profit / sweat equity / required margin.
4. Back out hard costs, soft costs, contingency, financing, carrying, closing, and reserves.
5. Arrive at max supportable land purchase price.
6. Present conservative/base/aggressive scenarios.
7. Generate a memo with sources, assumptions, calculations, risks, and next steps.

## Non-negotiable product rules

Always separate these categories in data models, API responses, UI, and reports:

```text
Fact:
  Source-backed parcel, zoning, jurisdiction, ordinance, comp, or market information.

Assumption:
  User-provided or defaulted value such as rent, cap rate, hard cost, soft cost, vacancy, expense ratio, contingency, or financing terms.

Calculation:
  Deterministic formula output, with inputs and formula version recorded.

Recommendation:
  Downstream interpretation such as recommended offer range, feasibility conclusion, or next action.
```

The LLM may interpret, explain, and orchestrate. It must not freehand financial math. All zoning-capacity and underwriting math must run through deterministic, tested calculators.

## Implementation scope

Deliver a practical MVP slice, not a broad rewrite.

### 1. Domain contracts

Add or extend typed contracts for development-acquisition analysis. Prefer Pydantic models on the backend and matching frontend TypeScript types where applicable.

Required domain objects:

- `DevelopmentAssumptionSet`
- `DevelopmentScenario`
- `UnitMixItem`
- `RentAssumption`
- `SalesValueAssumption`
- `CostAssumptionSet`
- `FinancingAssumptionSet`
- `OperatingAssumptionSet`
- `DevelopmentMetrics`
- `MaxLandOfferResult`
- `DevelopmentFeasibilityRun`
- `AcquisitionMemoSection`

At minimum, support these scenario fields:

- scenario name: conservative/base/aggressive/custom
- parcel/site reference
- max units / selected units
- unit mix
- average rent or sales value
- vacancy
- operating expense ratio
- cap rate
- hard cost per square foot or per unit
- soft cost percentage
- contingency percentage
- financing terms
- target developer profit / required margin
- acquisition closing costs
- carrying costs
- risk buffer

### 2. Deterministic calculators

Create a calculator module for real estate development underwriting. Keep it isolated, tested, and free of external API calls.

Required calculations:

```text
Gross Scheduled Rent = units * average_monthly_rent * 12
Effective Gross Income = Gross Scheduled Rent - vacancy_loss + other_income
NOI = Effective Gross Income - operating_expenses
As-Built Value = NOI / cap_rate
Total Development Cost Excluding Land = hard_costs + soft_costs + contingency + financing_costs + carrying_costs + closing_costs + reserves
Max Land Price = As-Built Value - Total Development Cost Excluding Land - required_profit - risk_buffer
Loan-to-Cost = loan_amount / total_development_cost
Loan-to-Value = loan_amount / as_built_value
DSCR = NOI / annual_debt_service
Yield on Cost = NOI / total_development_cost
Cash-on-Cash = annual_cash_flow / cash_invested
```

Also support sale-oriented scenarios where value comes from sellout rather than stabilized NOI:

```text
Gross Sellout Value = units * average_sale_price
Net Sellout Value = Gross Sellout Value - selling_costs
Max Land Price = Net Sellout Value - development_costs_excluding_land - required_profit - risk_buffer
```

Every calculation result must include:

- input values
- output value
- formula name
- formula version
- warnings for missing, zero, or suspicious assumptions

### 3. Harness skill manifests

Add repo-owned skill/playbook specs for:

- `development_feasibility`
- `max_land_offer`
- `scenario_comparison`
- `acquisition_memo`
- `lender_package`
- `due_diligence_checklist`

These can be YAML or Markdown, but they must define:

- purpose
- required inputs
- optional inputs
- tools/calculators used
- output schema
- risk class
- evidence requirements
- evaluation criteria

The initial `max_land_offer` skill should run without live external APIs when given mocked parcel/zoning/assumption inputs.

### 4. Runtime integration

Extend the existing harness direction rather than replacing the current MVP.

Add a runtime path that can execute development-feasibility analysis through a `HarnessRuntime` or equivalent facade.

Required behavior:

- Accept a project/site/scenario request.
- Use existing zoning/density output when available.
- Use deterministic underwriting calculators for scenario math.
- Record assumptions and calculations as evidence-linked run artifacts.
- Emit structured events such as:
  - `run_started`
  - `tool_started`
  - `tool_completed`
  - `calculation_completed`
  - `evidence_recorded`
  - `approval_required`
  - `run_completed`
  - `run_failed`

Do not break existing `/api/v1/analyze`, `/api/v1/analyze/stream`, `/api/v1/chat`, portfolio, document, geometry, or render behavior.

### 5. Evidence ledger integration

Where the repo already has or is planning evidence/run records, integrate with that structure. Where it does not exist yet, add the smallest useful persistence/service seam.

Evidence items for this feature must capture:

- source type
- source name or tool name
- retrieved/generated timestamp
- confidence when applicable
- linked workspace/project/site/run/scenario
- claim category: fact, assumption, calculation, recommendation
- source reference or calculation formula

Examples:

```text
Fact evidence:
  "Zoning district is T6-80-O."

Assumption evidence:
  "Base scenario rent assumed at $2,400/month/unit."

Calculation evidence:
  "As-built value calculated as NOI / cap rate using formula v1."

Recommendation evidence:
  "Recommended offer range is 80% to 90% of max supportable land price due to entitlement risk."
```

### 6. Governance

Respect the existing governance direction.

Default policy:

- Read-only parcel/zoning/ordinance/property tools: auto-allow.
- Deterministic calculators: auto-allow.
- Internal memo/report draft creation: auto-allow or `WRITE_INTERNAL`.
- Google Docs/Sheets creation, CRM writes, email sends, dataset exports, calendar actions: approval-gated `WRITE_EXTERNAL`.
- Code execution, broad scraping, or sandbox execution: approval-gated or blocked unless explicitly configured.

Add or update tests proving external-write tools cannot execute directly from agent/chat/tool paths without a governance decision.

### 7. API endpoints

Add minimal backend endpoints for the MVP slice. Names may be adapted to existing routing conventions, but preserve this capability set:

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

If workspace/project/site persistence is not complete, use a thin compatibility seam and fixtures, but do not fake durability in the API contract. Make limitations explicit in code comments and docs.

### 8. Frontend MVP surface

Add the smallest frontend surface that proves the workflow without redesigning the whole app.

Required UI components or fixtures:

- scenario assumptions form/editor
- conservative/base/aggressive scenario selector
- development metrics summary card
- max land offer result card
- evidence rail or evidence list
- acquisition memo preview section
- approval panel hook for external document/export actions

Keep existing home lookup/chat UI working.

### 9. Acquisition memo generation

Implement a generated memo structure, even if the first version is Markdown/JSON only.

Required sections:

1. Executive summary
2. Parcel and jurisdiction facts
3. Zoning capacity and governing constraint
4. Development concept and unit mix
5. Rent/sales assumptions
6. Cost assumptions
7. Financing assumptions
8. Development metrics
9. Max land offer and recommended offer range
10. Risks and open diligence items
11. Evidence/source appendix

The memo must label facts, assumptions, calculations, and recommendations distinctly.

### 10. Due diligence checklist

Generate a basic due diligence checklist from the run context.

Minimum categories:

- zoning confirmation
- survey and title
- setbacks/dimensional standards
- parking/loading
- utilities and capacity
- flood/wetlands/environmental
- impact fees
- entitlement/permitting path
- neighborhood/political risk
- construction cost validation
- rent/sales comp validation
- financing/lender requirements

## Testing requirements

Add deterministic tests. Do not require live external API credentials for new core tests.

Required tests:

- calculator unit tests for NOI, as-built value, total development cost, max land price, LTC, LTV, DSCR, yield on cost, and sale scenario math
- invalid/missing assumption warning tests
- scenario model validation tests
- runtime event emission tests
- evidence item creation tests for fact/assumption/calculation/recommendation categories
- governance tests blocking or approval-gating external writes
- API route tests for scenario create/run/evidence/memo
- frontend component tests or fixture-backed UI tests for assumptions, result card, evidence rail, and memo preview

Run or document results for:

```bash
uv run pytest tests/unit -q
uv run pytest tests/integration -q
cd frontend && npm run lint
cd frontend && npm run test:ui
```

If pre-existing failures exist, document them clearly with evidence that the new feature did not cause them.

## Evaluation fixtures

Add or extend `plotlot-bench` / golden fixtures for at least five development-acquisition cases.

Each case should include:

- parcel/site input
- zoning capacity input or mocked zoning output
- assumptions
- expected metrics
- expected max land price
- expected warnings
- expected memo section presence

Include at least:

1. stabilized rental multifamily base case
2. conservative rental case with high cap rate / higher costs
3. aggressive rental case with lower cap rate / lower costs
4. sale-oriented townhouse or duplex case
5. infeasible case where costs exceed value and max land price is negative

## Documentation updates

Update or create docs explaining:

- development-acquisition harness workflow
- formulas and formula versions
- assumptions schema
- scenario comparison behavior
- evidence categories
- governance behavior for external writes
- how to run the new tests/evals

## Definition of done

This goal is complete when:

- Current Lookup and Agent behavior remain intact.
- A user or test can create a development scenario for a site/project.
- The system can run deterministic underwriting calculations.
- The system returns max supportable land price and recommended offer range.
- The system emits or records run/evidence/calculation events.
- The system can generate an acquisition memo with facts, assumptions, calculations, recommendations, and evidence appendix.
- External writes are approval-gated.
- New unit/integration/frontend tests pass or failures are documented as pre-existing.
- The implementation is incremental, reviewable, and does not perform a broad rewrite of the app.

## Suggested implementation order

1. Read existing contracts and current backend/frontend structure.
2. Add backend contracts and calculator tests first.
3. Implement deterministic calculators.
4. Add scenario/run/evidence service layer.
5. Add API routes with tests.
6. Add skill manifests/docs.
7. Add runtime facade integration and event emission.
8. Add frontend MVP components with fixture support.
9. Add memo/checklist generation.
10. Run tests and update documentation.

## Hard constraints

- Do not remove existing routes or break current MVP behavior.
- Do not put financial math in prompts.
- Do not use live external APIs in deterministic tests.
- Do not execute external writes without governance approval.
- Do not hide assumptions inside prose.
- Do not make unsupported legal, zoning, or investment guarantees.
- Do not claim official zoning/legal conclusions without source/freshness caveats.
- Prefer small typed seams over monolithic rewrites.

Proceed with implementation using the smallest coherent feature branch that satisfies the definition of done.
