from __future__ import annotations

from pydantic import Field

from plotlot.harness.contracts.base import HarnessContract, JsonObject
from plotlot.harness.rental_market_evidence import resolve_rental_market_evidence
from plotlot.pipeline.cost_model import get_cost_model


class UnderwritingMarketProfileRequest(HarnessContract):
    state: str = Field(min_length=2, max_length=32)
    county: str = Field(default="", min_length=0, max_length=128)
    municipality: str = Field(default="", min_length=0, max_length=128)
    assumptions: JsonObject = Field(default_factory=dict)


def resolve_underwriting_market_profile(
    *,
    state: str,
    county: str,
    municipality: str = "",
    assumptions: JsonObject | None = None,
) -> JsonObject:
    assumption_values = assumptions or {}
    cost_model = get_cost_model(state, county)
    rental_evidence = resolve_rental_market_evidence(
        state=state,
        county=county,
        municipality=municipality,
        assumptions=assumption_values,
    )

    overridden_fields: list[str] = []
    if isinstance(assumption_values.get("constructionCostPsf"), int | float):
        overridden_fields.append("construction_cost_psf")
    if isinstance(assumption_values.get("avgUnitSizeSf"), int | float):
        overridden_fields.append("avg_unit_size_sqft")
    if isinstance(assumption_values.get("softCostPct"), int | float):
        overridden_fields.append("soft_cost_pct")
    if isinstance(assumption_values.get("builderMarginPct"), int | float):
        overridden_fields.append("builder_margin_pct")
    if isinstance(assumption_values.get("impactFeesPerUnit"), int | float):
        overridden_fields.append("impact_fees_per_unit")
    if isinstance(assumption_values.get("advPerUnit"), int | float):
        overridden_fields.append("adv_per_unit")
    if isinstance(assumption_values.get("monthlyRentPerUnit"), int | float):
        overridden_fields.append("monthly_rent_per_unit")
    if isinstance(assumption_values.get("vacancyPct"), int | float):
        overridden_fields.append("vacancy_pct")
    if isinstance(assumption_values.get("operatingExpensePct"), int | float):
        overridden_fields.append("operating_expense_pct")
    if isinstance(assumption_values.get("capRate"), int | float):
        overridden_fields.append("cap_rate")

    return {
        "market": cost_model.market,
        "source": cost_model.source,
        "state": state,
        "county": county,
        "municipality": municipality,
        "construction_cost_psf": cost_model.construction_cost_psf,
        "avg_unit_size_sqft": cost_model.avg_unit_size_sqft,
        "soft_cost_pct": cost_model.soft_cost_pct,
        "builder_margin_pct": cost_model.builder_margin_pct,
        "impact_fees_per_unit": cost_model.impact_fee_per_unit,
        "adv_per_unit": cost_model.adv_per_unit_default,
        "monthly_rent_per_unit": rental_evidence.get("monthly_rent_per_unit"),
        "vacancy_pct": rental_evidence.get("vacancy_pct"),
        "operating_expense_pct": rental_evidence.get("operating_expense_pct"),
        "cap_rate": rental_evidence.get("cap_rate"),
        "requires_official_verification": bool(rental_evidence.get("requires_official_verification")),
        "requires_income_assumption_verification": bool(
            rental_evidence.get("requires_income_assumption_verification")
        ),
        "income_inferred_fields": list(rental_evidence.get("inferred_fields") or []),
        "income_assumption_source": rental_evidence.get("assumption_source", ""),
        "overridden_fields": overridden_fields,
        "assumptions_snapshot": dict(assumption_values),
        "rental_market_evidence": rental_evidence,
    }
