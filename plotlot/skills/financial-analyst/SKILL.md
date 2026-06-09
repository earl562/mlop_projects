---
name: financial-analyst
description: Run financial analysis on a proposed land development project. Residential (1-4 units) uses pro forma method. Commercial (5+ units) uses NOI + cap rate method. Industrial uses warehouse-specific metrics.
trust_tier: T2
verification_gate: G3
---

# Financial Analyst Skill

## When to Use
When the user asks about project valuation, ROI, cap rates, NOI, pro forma analysis, or whether a deal "pencils out." Automatically routes to the correct valuation method based on unit count and property type.

## Valuation Methods

| Units | Property Type | Method | Formula |
|-------|--------------|--------|---------|
| 1-4 | Residential | Pro forma | Hard costs + soft costs + land → NOI → cap valuation |
| 5+ | Multi-family | Commercial NOI | EGI - OpEx = NOI / Cap Rate = Value |
| Any | Industrial | Industrial | NOI + warehouse metrics (clear height, dock doors, FAR) |
| Any | Mixed-use | Component | Residential + Commercial + Retail income streams |

## How to Use
```python
from plotlot.harness.commercial_skills import route_valuation

method = route_valuation(unit_count=12, property_type="multi_family")
# Returns "commercial-noi"

# Then call the appropriate function:
from plotlot.harness.commercial_skills import calculate_noi, CommercialInputs
ci = CommercialInputs("multifamily", gross_sqft=20000, leasable_sqft=18000, avg_rent_per_sqft=24, cap_rate=0.06)
result = calculate_noi(ci)
# result.evidence["outputs"]["net_operating_income"] → NOI
# result.evidence["outputs"]["cap_rate_valuation"] → Property value
```

## Limitations
- Uses standard cap rates and vacancy assumptions. Market-specific rates may differ.
- Industrial analysis uses warehouse quality scoring (clear height, dock doors, FAR, power).
- DCF analysis available for detailed hold-period projections.
- Always verify market assumptions with local brokers or appraisers.