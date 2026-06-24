"""Residential and commercial development scenario calculators.

Residential and commercial deals must not share one underwriting path:

- Residential rental deals are unit-count and monthly-rent driven.
- Residential sale deals are unit-count and sellout driven.
- Commercial lease deals are GLA and annual rent-per-square-foot driven.

All functions are deterministic and zero-I/O. External tools should source facts,
local comps, and assumptions before calling these calculators.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from plotlot.pipeline.development_land_offer import (
    AsBuiltValueInputs,
    CostStack,
    DevelopmentLandOfferInputs,
    DevelopmentLandOfferResult,
    calculate_development_land_offer,
)


@dataclass(frozen=True)
class ResidentialRentalScenarioInputs:
    """Inputs for a residential rental development scenario."""

    units: int
    average_monthly_rent: float
    market_cap_rate_pct: float
    cost_stack: CostStack
    vacancy_rate_pct: float = 5.0
    operating_expense_ratio_pct: float = 38.0
    other_income_pct_of_gsr: float = 0.0
    desired_sweat_equity_pct: float = 25.0
    recommended_offer_pct_of_max: float = 85.0
    scenario_name: str = "residential_rental_base"
    market_profile_key: str = ""
    location_notes: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    assumption_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResidentialSaleScenarioInputs:
    """Inputs for a residential for-sale development scenario."""

    units: int
    average_sale_price_per_unit: float
    cost_stack: CostStack
    selling_cost_pct_of_gross_sellout: float = 6.0
    required_profit_pct_of_net_sellout: float = 20.0
    recommended_offer_pct_of_max: float = 85.0
    scenario_name: str = "residential_sale_base"
    market_profile_key: str = ""
    location_notes: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    assumption_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CommercialLeaseScenarioInputs:
    """Inputs for a commercial lease development scenario."""

    gla_sqft: float
    annual_rent_psf: float
    market_cap_rate_pct: float
    cost_stack: CostStack
    vacancy_rate_pct: float = 8.0
    operating_expense_ratio_pct: float = 35.0
    other_income_pct_of_base_rent: float = 0.0
    desired_sweat_equity_pct: float = 25.0
    recommended_offer_pct_of_max: float = 85.0
    scenario_name: str = "commercial_lease_base"
    market_profile_key: str = ""
    location_notes: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    assumption_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DevelopmentScenarioResult:
    """Common result envelope for all scenario calculators."""

    scenario_name: str
    asset_class: str
    valuation_method: str
    capacity_units: int
    commercial_gla_sqft: float
    gross_revenue: float
    vacancy_loss: float
    other_income: float
    effective_revenue: float
    operating_expenses: float
    net_operating_income: float
    selling_costs: float
    as_built_value: float
    land_offer: DevelopmentLandOfferResult
    warnings: list[str]
    formulas: dict[str, str]


def calculate_residential_rental_scenario(
    inputs: ResidentialRentalScenarioInputs,
) -> DevelopmentScenarioResult:
    """Calculate a residential rental scenario from units and monthly rent."""

    warnings: list[str] = []
    if inputs.units <= 0:
        warnings.append("Residential rental scenario requires positive unit count.")
    if inputs.average_monthly_rent <= 0:
        warnings.append("Residential rental scenario requires positive average monthly rent.")

    vacancy_pct = _bounded_percent(
        inputs.vacancy_rate_pct,
        5.0,
        "vacancy_rate_pct",
        warnings,
    )
    opex_pct = _bounded_percent(
        inputs.operating_expense_ratio_pct,
        38.0,
        "operating_expense_ratio_pct",
        warnings,
    )
    other_income_pct = _bounded_percent(
        inputs.other_income_pct_of_gsr,
        0.0,
        "other_income_pct_of_gsr",
        warnings,
    )

    units = max(inputs.units, 0)
    monthly_rent = max(inputs.average_monthly_rent, 0.0)
    gross_scheduled_rent = units * monthly_rent * 12.0
    vacancy_loss = gross_scheduled_rent * (vacancy_pct / 100.0)
    other_income = gross_scheduled_rent * (other_income_pct / 100.0)
    effective_revenue = gross_scheduled_rent - vacancy_loss + other_income
    operating_expenses = effective_revenue * (opex_pct / 100.0)
    noi = effective_revenue - operating_expenses

    land_offer = calculate_development_land_offer(
        DevelopmentLandOfferInputs(
            max_units=inputs.units,
            commercial_gla_sqft=0.0,
            as_built_value=AsBuiltValueInputs(
                annual_noi=noi,
                market_cap_rate_pct=inputs.market_cap_rate_pct,
            ),
            cost_stack=inputs.cost_stack,
            desired_sweat_equity_pct=inputs.desired_sweat_equity_pct,
            recommended_offer_pct_of_max=inputs.recommended_offer_pct_of_max,
            scenario_name=inputs.scenario_name,
            market_profile_key=inputs.market_profile_key,
            location_notes=inputs.location_notes,
            evidence_ids=inputs.evidence_ids,
            assumption_ids=inputs.assumption_ids,
        )
    )

    return DevelopmentScenarioResult(
        scenario_name=inputs.scenario_name,
        asset_class="residential",
        valuation_method="rental_income_cap_rate",
        capacity_units=inputs.units,
        commercial_gla_sqft=0.0,
        gross_revenue=round(gross_scheduled_rent, 2),
        vacancy_loss=round(vacancy_loss, 2),
        other_income=round(other_income, 2),
        effective_revenue=round(effective_revenue, 2),
        operating_expenses=round(operating_expenses, 2),
        net_operating_income=round(noi, 2),
        selling_costs=0.0,
        as_built_value=land_offer.as_built_value,
        land_offer=land_offer,
        warnings=warnings + land_offer.warnings,
        formulas={
            "gross_scheduled_rent": "units * average_monthly_rent * 12",
            "effective_revenue": "gross_scheduled_rent - vacancy_loss + other_income",
            "noi": "effective_revenue - operating_expenses",
            "as_built_value": "noi / market_cap_rate",
        },
    )


def calculate_residential_sale_scenario(
    inputs: ResidentialSaleScenarioInputs,
) -> DevelopmentScenarioResult:
    """Calculate a residential for-sale scenario from unit sellout value."""

    warnings: list[str] = []
    if inputs.units <= 0:
        warnings.append("Residential sale scenario requires positive unit count.")
    if inputs.average_sale_price_per_unit <= 0:
        warnings.append("Residential sale scenario requires positive average sale price.")

    selling_cost_pct = _bounded_percent(
        inputs.selling_cost_pct_of_gross_sellout,
        6.0,
        "selling_cost_pct_of_gross_sellout",
        warnings,
    )

    units = max(inputs.units, 0)
    gross_sellout = units * max(inputs.average_sale_price_per_unit, 0.0)
    selling_costs = gross_sellout * (selling_cost_pct / 100.0)
    net_sellout_value = gross_sellout - selling_costs

    land_offer = calculate_development_land_offer(
        DevelopmentLandOfferInputs(
            max_units=inputs.units,
            commercial_gla_sqft=0.0,
            as_built_value=AsBuiltValueInputs(
                override_value=net_sellout_value,
                value_source="net_residential_sellout",
            ),
            cost_stack=inputs.cost_stack,
            desired_sweat_equity_pct=inputs.required_profit_pct_of_net_sellout,
            recommended_offer_pct_of_max=inputs.recommended_offer_pct_of_max,
            scenario_name=inputs.scenario_name,
            market_profile_key=inputs.market_profile_key,
            location_notes=inputs.location_notes,
            evidence_ids=inputs.evidence_ids,
            assumption_ids=inputs.assumption_ids,
        )
    )

    return DevelopmentScenarioResult(
        scenario_name=inputs.scenario_name,
        asset_class="residential",
        valuation_method="for_sale_net_sellout",
        capacity_units=inputs.units,
        commercial_gla_sqft=0.0,
        gross_revenue=round(gross_sellout, 2),
        vacancy_loss=0.0,
        other_income=0.0,
        effective_revenue=round(net_sellout_value, 2),
        operating_expenses=0.0,
        net_operating_income=0.0,
        selling_costs=round(selling_costs, 2),
        as_built_value=land_offer.as_built_value,
        land_offer=land_offer,
        warnings=warnings + land_offer.warnings,
        formulas={
            "gross_sellout": "units * average_sale_price_per_unit",
            "net_sellout_value": "gross_sellout - selling_costs",
            "selling_costs": "gross_sellout * selling_cost_pct",
            "max_land_price": "net_sellout_value - required_profit - costs",
        },
    )


def calculate_commercial_lease_scenario(
    inputs: CommercialLeaseScenarioInputs,
) -> DevelopmentScenarioResult:
    """Calculate a commercial lease scenario from GLA and annual rent psf."""

    warnings: list[str] = []
    if inputs.gla_sqft <= 0:
        warnings.append("Commercial lease scenario requires positive GLA square footage.")
    if inputs.annual_rent_psf <= 0:
        warnings.append("Commercial lease scenario requires positive annual rent psf.")

    vacancy_pct = _bounded_percent(
        inputs.vacancy_rate_pct,
        8.0,
        "vacancy_rate_pct",
        warnings,
    )
    opex_pct = _bounded_percent(
        inputs.operating_expense_ratio_pct,
        35.0,
        "operating_expense_ratio_pct",
        warnings,
    )
    other_income_pct = _bounded_percent(
        inputs.other_income_pct_of_base_rent,
        0.0,
        "other_income_pct_of_base_rent",
        warnings,
    )

    gla = max(inputs.gla_sqft, 0.0)
    base_rent = gla * max(inputs.annual_rent_psf, 0.0)
    vacancy_loss = base_rent * (vacancy_pct / 100.0)
    other_income = base_rent * (other_income_pct / 100.0)
    effective_revenue = base_rent - vacancy_loss + other_income
    operating_expenses = effective_revenue * (opex_pct / 100.0)
    noi = effective_revenue - operating_expenses

    land_offer = calculate_development_land_offer(
        DevelopmentLandOfferInputs(
            max_units=0,
            commercial_gla_sqft=inputs.gla_sqft,
            as_built_value=AsBuiltValueInputs(
                annual_noi=noi,
                market_cap_rate_pct=inputs.market_cap_rate_pct,
            ),
            cost_stack=inputs.cost_stack,
            desired_sweat_equity_pct=inputs.desired_sweat_equity_pct,
            recommended_offer_pct_of_max=inputs.recommended_offer_pct_of_max,
            scenario_name=inputs.scenario_name,
            market_profile_key=inputs.market_profile_key,
            location_notes=inputs.location_notes,
            evidence_ids=inputs.evidence_ids,
            assumption_ids=inputs.assumption_ids,
        )
    )

    return DevelopmentScenarioResult(
        scenario_name=inputs.scenario_name,
        asset_class="commercial",
        valuation_method="commercial_gla_income_cap_rate",
        capacity_units=0,
        commercial_gla_sqft=round(inputs.gla_sqft, 2),
        gross_revenue=round(base_rent, 2),
        vacancy_loss=round(vacancy_loss, 2),
        other_income=round(other_income, 2),
        effective_revenue=round(effective_revenue, 2),
        operating_expenses=round(operating_expenses, 2),
        net_operating_income=round(noi, 2),
        selling_costs=0.0,
        as_built_value=land_offer.as_built_value,
        land_offer=land_offer,
        warnings=warnings + land_offer.warnings,
        formulas={
            "base_rent": "gla_sqft * annual_rent_psf",
            "effective_revenue": "base_rent - vacancy_loss + other_income",
            "noi": "effective_revenue - operating_expenses",
            "as_built_value": "noi / market_cap_rate",
            "land_value_per_buildable_sqft": "max_land_price / commercial_gla_sqft",
        },
    )


def _bounded_percent(
    value: float,
    default: float,
    field_name: str,
    warnings: list[str],
) -> float:
    if value < 0 or value > 100:
        warnings.append(f"{field_name}={value} is outside 0-100%; using {default}.")
        return default
    return value
