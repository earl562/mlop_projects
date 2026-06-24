"""Development land-offer calculator for PlotLot's land developer harness.

This module encodes the land valuation workflow PlotLot should use after the
zoning lookup layer has produced a sourced density/capacity answer:

1. Use the density study result as the capacity guardrail.
2. Determine stabilized/as-built value.
3. Back out required sweat equity or developer profit.
4. Back out location-sensitive development costs before land.
5. Arrive at max land purchase price and a conservative offer.

The calculator is intentionally deterministic and zero-I/O. Upstream tools are
responsible for sourcing facts, choosing local market assumptions, and labeling
assumptions; this module only owns math and warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CostStack:
    """Development costs excluding land.

    Deals vary by location, so this class accepts already-localized dollar
    assumptions rather than pretending that a national default cost stack exists.
    Market-profile utilities can produce these values, but this calculator only
    sums and records them.
    """

    hard_costs: float = 0.0
    soft_costs: float = 0.0
    financing_costs: float = 0.0
    closing_costs: float = 0.0
    carrying_costs: float = 0.0
    reserves: float = 0.0
    contingency: float = 0.0
    developer_fee: float = 0.0
    impact_fees: float = 0.0
    risk_buffer: float = 0.0
    other_costs: float = 0.0

    @property
    def total_excluding_land(self) -> float:
        return sum(
            _positive_or_zero(value)
            for value in (
                self.hard_costs,
                self.soft_costs,
                self.financing_costs,
                self.closing_costs,
                self.carrying_costs,
                self.reserves,
                self.contingency,
                self.developer_fee,
                self.impact_fees,
                self.risk_buffer,
                self.other_costs,
            )
        )


@dataclass(frozen=True)
class AsBuiltValueInputs:
    """Inputs for stabilized/as-built value.

    `override_value` wins when supplied. Otherwise the calculator uses the
    income approach:

        as_built_value = annual_noi / (market_cap_rate_pct / 100)
    """

    annual_noi: float = 0.0
    market_cap_rate_pct: float = 0.0
    override_value: float = 0.0
    value_source: str = ""


@dataclass(frozen=True)
class DevelopmentLandOfferInputs:
    """Inputs required to calculate a residual land offer.

    Residential scenarios should provide `max_units`. Commercial scenarios
    should provide `commercial_gla_sqft`. The calculator can price either path
    while keeping per-unit and per-buildable-square-foot outputs separate.
    """

    max_units: int
    cost_stack: CostStack
    as_built_value: AsBuiltValueInputs
    commercial_gla_sqft: float = 0.0
    desired_sweat_equity_pct: float = 25.0
    recommended_offer_pct_of_max: float = 85.0
    scenario_name: str = "base"
    market_profile_key: str = ""
    location_notes: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    assumption_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DevelopmentLandOfferResult:
    """Result of the residual land-offer calculation."""

    scenario_name: str
    max_units: int
    commercial_gla_sqft: float
    as_built_value: float
    as_built_value_source: str
    desired_sweat_equity: float
    total_costs_before_land: float
    max_land_purchase_price: float
    recommended_offer: float
    max_land_purchase_price_per_unit: float
    recommended_offer_per_unit: float
    max_land_purchase_price_per_buildable_sqft: float
    recommended_offer_per_buildable_sqft: float
    confidence: str
    warnings: list[str]
    formulas: dict[str, str]
    market_profile_key: str = ""
    location_notes: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    assumption_ids: list[str] = field(default_factory=list)


def calculate_as_built_value(
    annual_noi: float,
    market_cap_rate_pct: float,
) -> float:
    """Calculate stabilized value from annual NOI and cap rate.

    Returns 0.0 when inputs are not usable rather than raising. Callers should
    use `calculate_development_land_offer` when they need warnings explaining
    why value could not be derived.
    """

    if annual_noi <= 0 or market_cap_rate_pct <= 0:
        return 0.0
    return annual_noi / (market_cap_rate_pct / 100.0)


def calculate_development_land_offer(
    inputs: DevelopmentLandOfferInputs,
) -> DevelopmentLandOfferResult:
    """Calculate max land purchase price from a sourced density and value case.

    Formula chain:

    - As-built value = override value OR annual NOI / market cap rate.
    - Desired sweat equity = as-built value × desired sweat-equity percent.
    - Max land purchase price = as-built value - desired sweat equity - costs.
    - Recommended offer = positive max land price × recommended-offer percent.

    Negative residual land value is preserved in `max_land_purchase_price` so the
    underwriting surface can explain why the deal does not pencil. The
    recommended offer is floored at 0 because a buyer should not make a negative
    purchase offer.
    """

    warnings: list[str] = []

    if not inputs.market_profile_key:
        warnings.append(
            "No market profile key supplied; location-sensitive assumptions are untracked."
        )

    has_residential_capacity = inputs.max_units > 0
    has_commercial_capacity = inputs.commercial_gla_sqft > 0
    if not has_residential_capacity and not has_commercial_capacity:
        warnings.append("No positive unit capacity or commercial GLA supplied from feasibility study.")

    total_costs = inputs.cost_stack.total_excluding_land
    if total_costs <= 0:
        warnings.append("No development costs supplied before land.")

    as_built_value, value_source = _resolve_as_built_value(inputs.as_built_value, warnings)

    sweat_equity_pct = _bounded_percent(
        inputs.desired_sweat_equity_pct,
        default=25.0,
        field_name="desired_sweat_equity_pct",
        warnings=warnings,
    )
    offer_pct = _bounded_percent(
        inputs.recommended_offer_pct_of_max,
        default=85.0,
        field_name="recommended_offer_pct_of_max",
        warnings=warnings,
    )

    desired_sweat_equity = as_built_value * (sweat_equity_pct / 100.0)
    max_land_purchase_price = as_built_value - desired_sweat_equity - total_costs

    if max_land_purchase_price < 0:
        warnings.append("Residual land value is negative at the supplied assumptions.")

    recommended_offer = max(max_land_purchase_price, 0.0) * (offer_pct / 100.0)

    confidence = _confidence(
        has_capacity=has_residential_capacity or has_commercial_capacity,
        as_built_value=as_built_value,
        total_costs=total_costs,
        evidence_count=len(inputs.evidence_ids),
        warning_count=len(warnings),
    )

    return DevelopmentLandOfferResult(
        scenario_name=inputs.scenario_name,
        max_units=inputs.max_units,
        commercial_gla_sqft=round(inputs.commercial_gla_sqft, 2),
        as_built_value=round(as_built_value, 2),
        as_built_value_source=value_source,
        desired_sweat_equity=round(desired_sweat_equity, 2),
        total_costs_before_land=round(total_costs, 2),
        max_land_purchase_price=round(max_land_purchase_price, 2),
        recommended_offer=round(recommended_offer, 2),
        max_land_purchase_price_per_unit=_safe_divide(
            max_land_purchase_price,
            inputs.max_units,
        ),
        recommended_offer_per_unit=_safe_divide(recommended_offer, inputs.max_units),
        max_land_purchase_price_per_buildable_sqft=_safe_divide(
            max_land_purchase_price,
            inputs.commercial_gla_sqft,
        ),
        recommended_offer_per_buildable_sqft=_safe_divide(
            recommended_offer,
            inputs.commercial_gla_sqft,
        ),
        confidence=confidence,
        warnings=warnings,
        formulas={
            "as_built_value": "override_value OR annual_noi / (market_cap_rate_pct / 100)",
            "desired_sweat_equity": "as_built_value * desired_sweat_equity_pct",
            "total_costs_before_land": (
                "hard + soft + financing + closing + carrying + reserves + "
                "contingency + developer_fee + impact_fees + risk_buffer + other"
            ),
            "max_land_purchase_price": (
                "as_built_value - desired_sweat_equity - total_costs_before_land"
            ),
            "recommended_offer": "max(max_land_purchase_price, 0) * recommended_offer_pct",
            "per_unit_outputs": "residential land value outputs divide by max_units",
            "per_buildable_sqft_outputs": "commercial land value outputs divide by GLA sqft",
        },
        market_profile_key=inputs.market_profile_key,
        location_notes=list(inputs.location_notes),
        evidence_ids=list(inputs.evidence_ids),
        assumption_ids=list(inputs.assumption_ids),
    )


def _resolve_as_built_value(
    inputs: AsBuiltValueInputs,
    warnings: list[str],
) -> tuple[float, str]:
    if inputs.override_value > 0:
        source = inputs.value_source or "override_value"
        return inputs.override_value, source

    if inputs.annual_noi <= 0:
        warnings.append("Annual NOI is missing or non-positive; cannot derive as-built value.")
        return 0.0, "missing_noi"

    if inputs.market_cap_rate_pct <= 0:
        warnings.append("Market cap rate is missing or non-positive; cannot derive as-built value.")
        return 0.0, "missing_cap_rate"

    return calculate_as_built_value(inputs.annual_noi, inputs.market_cap_rate_pct), "income_approach"


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


def _positive_or_zero(value: float) -> float:
    return value if value > 0 else 0.0


def _safe_divide(numerator: float, denominator: float | int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 2)


def _confidence(
    has_capacity: bool,
    as_built_value: float,
    total_costs: float,
    evidence_count: int,
    warning_count: int,
) -> str:
    if not has_capacity or as_built_value <= 0 or total_costs <= 0:
        return "low"
    if warning_count > 0:
        return "low"
    if evidence_count >= 3:
        return "high"
    return "medium"
