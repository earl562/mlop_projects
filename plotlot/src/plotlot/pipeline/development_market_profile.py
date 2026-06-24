"""Location-specific market profiles for development underwriting.

A land deal is local. Construction costs, cap rates, contingency, impact fees,
entitlement risk, insurance, and offer buffers vary by jurisdiction. This module
provides a deterministic seam for converting a parcel location into labeled
starter assumptions.

The profiles in this file are not live market quotes. They are conservative
starter assumptions that must be shown to the user as assumptions until replaced
by user inputs, local bids, lender quotes, or sourced comps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from plotlot.pipeline.development_land_offer import CostStack


@dataclass(frozen=True)
class DevelopmentMarketProfile:
    """Starter underwriting assumptions for a local development market."""

    key: str
    label: str
    state: str
    county: str = ""
    municipality: str = ""
    residential_hard_cost_psf: float = 0.0
    commercial_hard_cost_psf: float = 0.0
    soft_cost_pct_of_hard: float = 20.0
    contingency_pct_of_hard: float = 8.0
    financing_cost_pct_of_hard_soft: float = 5.0
    closing_cost_pct_of_hard_soft: float = 1.0
    impact_fee_per_residential_unit: float = 0.0
    impact_fee_per_1000_commercial_gla: float = 0.0
    risk_buffer_pct_of_value: float = 0.0
    residential_cap_rate_pct: float = 6.0
    commercial_cap_rate_pct: float = 7.0
    desired_sweat_equity_pct: float = 25.0
    recommended_offer_pct_of_max: float = 85.0
    entitlement_risk: str = "medium"
    notes: list[str] = field(default_factory=list)
    evidence_requirements: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MarketCostEstimate:
    """Cost stack plus notes produced from a market profile."""

    market_profile_key: str
    cost_stack: CostStack
    gross_building_area_sqft: float
    cost_basis: str
    assumption_notes: list[str]


_MARKET_PROFILES: dict[str, DevelopmentMarketProfile] = {
    "miami_dade_fl": DevelopmentMarketProfile(
        key="miami_dade_fl",
        label="Miami-Dade County, FL",
        state="FL",
        county="Miami-Dade",
        residential_hard_cost_psf=225.0,
        commercial_hard_cost_psf=245.0,
        soft_cost_pct_of_hard=22.0,
        contingency_pct_of_hard=8.0,
        financing_cost_pct_of_hard_soft=5.0,
        closing_cost_pct_of_hard_soft=1.0,
        impact_fee_per_residential_unit=18_000.0,
        impact_fee_per_1000_commercial_gla=4_500.0,
        risk_buffer_pct_of_value=3.0,
        residential_cap_rate_pct=5.75,
        commercial_cap_rate_pct=6.75,
        desired_sweat_equity_pct=25.0,
        recommended_offer_pct_of_max=85.0,
        entitlement_risk="medium",
        notes=["Starter assumptions for South Florida infill development."],
        evidence_requirements=[
            "municipal zoning confirmation",
            "impact-fee schedule",
            "recent local construction bid",
            "rent or sale comps within competitive submarket",
        ],
    ),
    "broward_fl": DevelopmentMarketProfile(
        key="broward_fl",
        label="Broward County, FL",
        state="FL",
        county="Broward",
        residential_hard_cost_psf=215.0,
        commercial_hard_cost_psf=235.0,
        soft_cost_pct_of_hard=21.0,
        contingency_pct_of_hard=8.0,
        financing_cost_pct_of_hard_soft=5.0,
        closing_cost_pct_of_hard_soft=1.0,
        impact_fee_per_residential_unit=16_000.0,
        impact_fee_per_1000_commercial_gla=4_000.0,
        risk_buffer_pct_of_value=3.0,
        residential_cap_rate_pct=5.9,
        commercial_cap_rate_pct=6.9,
        desired_sweat_equity_pct=25.0,
        recommended_offer_pct_of_max=85.0,
        entitlement_risk="medium",
        notes=["Starter assumptions for Broward small multifamily and infill."],
        evidence_requirements=["city zoning confirmation", "utility availability letter"],
    ),
    "palm_beach_fl": DevelopmentMarketProfile(
        key="palm_beach_fl",
        label="Palm Beach County, FL",
        state="FL",
        county="Palm Beach",
        residential_hard_cost_psf=230.0,
        commercial_hard_cost_psf=250.0,
        soft_cost_pct_of_hard=22.0,
        contingency_pct_of_hard=8.5,
        financing_cost_pct_of_hard_soft=5.0,
        closing_cost_pct_of_hard_soft=1.0,
        impact_fee_per_residential_unit=19_000.0,
        impact_fee_per_1000_commercial_gla=4_800.0,
        risk_buffer_pct_of_value=3.0,
        residential_cap_rate_pct=5.8,
        commercial_cap_rate_pct=6.8,
        desired_sweat_equity_pct=25.0,
        recommended_offer_pct_of_max=84.0,
        entitlement_risk="medium",
    ),
    "san_diego_ca": DevelopmentMarketProfile(
        key="san_diego_ca",
        label="San Diego, CA",
        state="CA",
        county="San Diego",
        municipality="San Diego",
        residential_hard_cost_psf=320.0,
        commercial_hard_cost_psf=345.0,
        soft_cost_pct_of_hard=28.0,
        contingency_pct_of_hard=10.0,
        financing_cost_pct_of_hard_soft=6.0,
        closing_cost_pct_of_hard_soft=1.5,
        impact_fee_per_residential_unit=35_000.0,
        impact_fee_per_1000_commercial_gla=8_000.0,
        risk_buffer_pct_of_value=5.0,
        residential_cap_rate_pct=4.75,
        commercial_cap_rate_pct=6.25,
        desired_sweat_equity_pct=30.0,
        recommended_offer_pct_of_max=82.0,
        entitlement_risk="high",
        notes=["Starter assumptions for entitlement-sensitive coastal California infill."],
        evidence_requirements=[
            "San Diego zoning and overlay confirmation",
            "development impact fee estimate",
            "local GC budget or RSMeans replacement",
            "coastal, airport, historic, parking, and density-bonus review",
        ],
    ),
    "bay_area_ca": DevelopmentMarketProfile(
        key="bay_area_ca",
        label="Bay Area, CA",
        state="CA",
        residential_hard_cost_psf=360.0,
        commercial_hard_cost_psf=390.0,
        soft_cost_pct_of_hard=30.0,
        contingency_pct_of_hard=10.0,
        financing_cost_pct_of_hard_soft=6.0,
        closing_cost_pct_of_hard_soft=1.5,
        impact_fee_per_residential_unit=40_000.0,
        impact_fee_per_1000_commercial_gla=9_000.0,
        risk_buffer_pct_of_value=6.0,
        residential_cap_rate_pct=4.5,
        commercial_cap_rate_pct=6.0,
        desired_sweat_equity_pct=30.0,
        recommended_offer_pct_of_max=80.0,
        entitlement_risk="high",
    ),
    "mecklenburg_nc": DevelopmentMarketProfile(
        key="mecklenburg_nc",
        label="Mecklenburg County, NC",
        state="NC",
        county="Mecklenburg",
        residential_hard_cost_psf=190.0,
        commercial_hard_cost_psf=215.0,
        soft_cost_pct_of_hard=20.0,
        contingency_pct_of_hard=7.0,
        financing_cost_pct_of_hard_soft=4.5,
        closing_cost_pct_of_hard_soft=1.0,
        impact_fee_per_residential_unit=10_000.0,
        impact_fee_per_1000_commercial_gla=3_000.0,
        risk_buffer_pct_of_value=2.0,
        residential_cap_rate_pct=6.0,
        commercial_cap_rate_pct=7.25,
        desired_sweat_equity_pct=25.0,
        recommended_offer_pct_of_max=87.0,
        entitlement_risk="medium",
    ),
    "clark_nv": DevelopmentMarketProfile(
        key="clark_nv",
        label="Clark County, NV",
        state="NV",
        county="Clark",
        residential_hard_cost_psf=205.0,
        commercial_hard_cost_psf=230.0,
        soft_cost_pct_of_hard=20.0,
        contingency_pct_of_hard=8.0,
        financing_cost_pct_of_hard_soft=5.0,
        closing_cost_pct_of_hard_soft=1.0,
        impact_fee_per_residential_unit=12_000.0,
        impact_fee_per_1000_commercial_gla=3_500.0,
        risk_buffer_pct_of_value=2.5,
        residential_cap_rate_pct=5.9,
        commercial_cap_rate_pct=7.0,
        desired_sweat_equity_pct=25.0,
        recommended_offer_pct_of_max=86.0,
        entitlement_risk="medium",
    ),
    "national_default": DevelopmentMarketProfile(
        key="national_default",
        label="National fallback",
        state="",
        residential_hard_cost_psf=220.0,
        commercial_hard_cost_psf=240.0,
        soft_cost_pct_of_hard=22.0,
        contingency_pct_of_hard=8.0,
        financing_cost_pct_of_hard_soft=5.0,
        closing_cost_pct_of_hard_soft=1.0,
        impact_fee_per_residential_unit=12_000.0,
        impact_fee_per_1000_commercial_gla=3_500.0,
        risk_buffer_pct_of_value=3.0,
        residential_cap_rate_pct=6.0,
        commercial_cap_rate_pct=7.0,
        desired_sweat_equity_pct=25.0,
        recommended_offer_pct_of_max=85.0,
        entitlement_risk="unknown",
        notes=["Fallback only. Replace with local bids, comps, and fee schedules."],
    ),
}

_CITY_PROFILE_ALIASES: dict[str, str] = {
    "san_diego_ca": "san_diego_ca",
}

_COUNTY_PROFILE_ALIASES: dict[str, str] = {
    "miami_dade_fl": "miami_dade_fl",
    "broward_fl": "broward_fl",
    "palm_beach_fl": "palm_beach_fl",
    "san_diego_ca": "san_diego_ca",
    "alameda_ca": "bay_area_ca",
    "contra_costa_ca": "bay_area_ca",
    "san_francisco_ca": "bay_area_ca",
    "san_mateo_ca": "bay_area_ca",
    "santa_clara_ca": "bay_area_ca",
    "mecklenburg_nc": "mecklenburg_nc",
    "clark_nv": "clark_nv",
}


def get_development_market_profile(
    *,
    state: str,
    county: str = "",
    municipality: str = "",
) -> DevelopmentMarketProfile:
    """Return the best available local market profile.

    Lookup order:

    1. municipality + state alias
    2. county + state alias
    3. direct generated municipality key
    4. direct generated county key
    5. national fallback
    """

    state_code = state.strip().upper()
    city_key = normalize_market_key(municipality, state_code) if municipality else ""
    county_key = normalize_market_key(county, state_code) if county else ""

    for candidate in (
        _CITY_PROFILE_ALIASES.get(city_key, ""),
        _COUNTY_PROFILE_ALIASES.get(county_key, ""),
        city_key,
        county_key,
    ):
        if candidate and candidate in _MARKET_PROFILES:
            return _MARKET_PROFILES[candidate]

    return _MARKET_PROFILES["national_default"]


def normalize_market_key(location: str, state: str) -> str:
    """Normalize a city/county + state pair into a stable market key."""

    location_slug = re.sub(r"[^a-z0-9]+", "_", location.lower()).strip("_")
    state_slug = re.sub(r"[^a-z0-9]+", "_", state.lower()).strip("_")
    if location_slug.endswith("_county"):
        location_slug = location_slug[: -len("_county")]
    return f"{location_slug}_{state_slug}" if state_slug else location_slug


def estimate_residential_cost_stack(
    *,
    profile: DevelopmentMarketProfile,
    units: int,
    average_unit_size_sqft: float,
    as_built_value: float = 0.0,
    hard_cost_psf_override: float | None = None,
    impact_fee_per_unit_override: float | None = None,
) -> MarketCostEstimate:
    """Estimate a residential cost stack from local market assumptions."""

    gross_area = units * average_unit_size_sqft if units > 0 else 0.0
    cost_psf = hard_cost_psf_override or profile.residential_hard_cost_psf
    impact_fee = impact_fee_per_unit_override or profile.impact_fee_per_residential_unit
    cost_stack = _build_cost_stack(
        hard_costs=gross_area * cost_psf,
        soft_cost_pct=profile.soft_cost_pct_of_hard,
        contingency_pct=profile.contingency_pct_of_hard,
        financing_pct=profile.financing_cost_pct_of_hard_soft,
        closing_pct=profile.closing_cost_pct_of_hard_soft,
        impact_fees=max(units, 0) * impact_fee,
        as_built_value=as_built_value,
        risk_buffer_pct=profile.risk_buffer_pct_of_value,
    )
    notes = [
        f"market_profile={profile.key}",
        "asset_class=residential",
        f"gross_area={gross_area:,.0f} sqft",
        f"hard_cost_psf=${cost_psf:.2f}",
        "Starter assumptions; replace with local bids and fee schedules.",
    ]
    if as_built_value <= 0 and profile.risk_buffer_pct_of_value > 0:
        notes.append("Risk buffer not applied because as-built value was not supplied.")

    return MarketCostEstimate(
        market_profile_key=profile.key,
        cost_stack=cost_stack,
        gross_building_area_sqft=round(gross_area, 2),
        cost_basis="residential_units_x_average_unit_size",
        assumption_notes=notes,
    )


def estimate_commercial_cost_stack(
    *,
    profile: DevelopmentMarketProfile,
    gla_sqft: float,
    as_built_value: float = 0.0,
    hard_cost_psf_override: float | None = None,
    impact_fee_per_1000_gla_override: float | None = None,
) -> MarketCostEstimate:
    """Estimate a commercial cost stack from GLA, not dwelling-unit count."""

    cost_psf = hard_cost_psf_override or profile.commercial_hard_cost_psf
    impact_fee = impact_fee_per_1000_gla_override or profile.impact_fee_per_1000_commercial_gla
    impact_fees = max(gla_sqft, 0.0) / 1000.0 * impact_fee
    cost_stack = _build_cost_stack(
        hard_costs=max(gla_sqft, 0.0) * cost_psf,
        soft_cost_pct=profile.soft_cost_pct_of_hard,
        contingency_pct=profile.contingency_pct_of_hard,
        financing_pct=profile.financing_cost_pct_of_hard_soft,
        closing_pct=profile.closing_cost_pct_of_hard_soft,
        impact_fees=impact_fees,
        as_built_value=as_built_value,
        risk_buffer_pct=profile.risk_buffer_pct_of_value,
    )
    notes = [
        f"market_profile={profile.key}",
        "asset_class=commercial",
        f"gla={gla_sqft:,.0f} sqft",
        f"hard_cost_psf=${cost_psf:.2f}",
        "Commercial costs are based on leasable/buildable area, not units.",
    ]
    if as_built_value <= 0 and profile.risk_buffer_pct_of_value > 0:
        notes.append("Risk buffer not applied because as-built value was not supplied.")

    return MarketCostEstimate(
        market_profile_key=profile.key,
        cost_stack=cost_stack,
        gross_building_area_sqft=round(max(gla_sqft, 0.0), 2),
        cost_basis="commercial_gla_sqft",
        assumption_notes=notes,
    )


def _build_cost_stack(
    *,
    hard_costs: float,
    soft_cost_pct: float,
    contingency_pct: float,
    financing_pct: float,
    closing_pct: float,
    impact_fees: float,
    as_built_value: float,
    risk_buffer_pct: float,
) -> CostStack:
    hard = max(hard_costs, 0.0)
    soft = hard * (soft_cost_pct / 100.0)
    contingency = hard * (contingency_pct / 100.0)
    hard_soft = hard + soft
    financing = hard_soft * (financing_pct / 100.0)
    closing = hard_soft * (closing_pct / 100.0)
    risk_buffer = max(as_built_value, 0.0) * (risk_buffer_pct / 100.0)

    return CostStack(
        hard_costs=round(hard, 2),
        soft_costs=round(soft, 2),
        financing_costs=round(financing, 2),
        closing_costs=round(closing, 2),
        contingency=round(contingency, 2),
        impact_fees=round(max(impact_fees, 0.0), 2),
        risk_buffer=round(risk_buffer, 2),
    )
