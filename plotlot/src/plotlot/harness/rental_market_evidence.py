from __future__ import annotations

from pydantic import Field

from plotlot.harness.contracts.base import HarnessContract, JsonObject
from plotlot.pipeline.cost_model import get_cost_model


class RentalMarketEvidenceRequest(HarnessContract):
    state: str = Field(min_length=2, max_length=32)
    county: str = Field(default="", min_length=0, max_length=128)
    municipality: str = Field(default="", min_length=0, max_length=128)
    assumptions: JsonObject = Field(default_factory=dict)


def resolve_rental_market_evidence(
    *,
    state: str,
    county: str,
    municipality: str = "",
    assumptions: JsonObject | None = None,
) -> JsonObject:
    assumption_values = assumptions or {}
    cost_model = get_cost_model(state, county)

    explicit_monthly_rent = assumption_values.get("monthlyRentPerUnit")
    explicit_vacancy = assumption_values.get("vacancyPct")
    explicit_operating_expense = assumption_values.get("operatingExpensePct")
    explicit_cap_rate = assumption_values.get("capRate")

    monthly_rent = _explicit_or_default(
        explicit_monthly_rent, cost_model.monthly_rent_per_unit_default
    )
    vacancy_pct = _explicit_or_default(explicit_vacancy, cost_model.vacancy_pct_default)
    operating_expense_pct = _explicit_or_default(
        explicit_operating_expense,
        cost_model.operating_expense_pct_default,
    )
    cap_rate = _explicit_or_default(explicit_cap_rate, cost_model.cap_rate_default)

    inferred_fields: list[str] = []
    if not isinstance(explicit_monthly_rent, int | float) and monthly_rent is not None:
        inferred_fields.append("monthly_rent_per_unit")
    if not isinstance(explicit_vacancy, int | float) and vacancy_pct is not None:
        inferred_fields.append("vacancy_pct")
    if (
        not isinstance(explicit_operating_expense, int | float)
        and operating_expense_pct is not None
    ):
        inferred_fields.append("operating_expense_pct")
    if not isinstance(explicit_cap_rate, int | float) and cap_rate is not None:
        inferred_fields.append("cap_rate")

    return {
        "market": cost_model.market,
        "source": cost_model.source,
        "state": state,
        "county": county,
        "municipality": municipality,
        "monthly_rent_per_unit": monthly_rent,
        "vacancy_pct": vacancy_pct,
        "operating_expense_pct": operating_expense_pct,
        "cap_rate": cap_rate,
        "requires_official_verification": cost_model.source == "national_default",
        "requires_income_assumption_verification": bool(inferred_fields),
        "inferred_fields": inferred_fields,
        "assumption_source": "user_assumptions" if not inferred_fields else cost_model.source,
        "assumptions_snapshot": dict(assumption_values),
    }


def _explicit_or_default(explicit: object, default: float | None) -> float | None:
    if isinstance(explicit, int | float):
        return float(explicit)
    return default
