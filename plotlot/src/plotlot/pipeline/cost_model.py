"""Regional development cost assumptions for the residual land pro forma.

The residual land valuation needs three cost levers (hard cost per square
foot, soft cost percentage, builder margin) plus a fallback after-development
value (ADV) per unit. These vary enormously by market: South Florida
multifamily runs ~$225/sf while the Bay Area runs ~$400/sf. Applying a single
hardcoded South Florida number nationwide produces materially wrong offers now
that coverage spans CA, NV, and NC.

This module maps a property's state + county to a coarse but regionally
grounded ``RegionalCostModel``. The numbers are market defaults meant to be
overridden by real comp data (ADV) where available — they are deliberately
conservative starting points, not appraisals.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------


@dataclass
class RegionalCostModel:
    """Development cost assumptions for one market.

    Attributes:
        market: Human-readable market label (e.g. "South Florida").
        construction_cost_psf: Hard construction cost per square foot (multifamily).
        soft_cost_pct: Soft costs as a percentage of hard costs.
        builder_margin_pct: Builder profit margin as a percentage of GDV.
        adv_per_unit_default: Fallback after-development value per finished unit,
            used only when comparable sold-unit data is unavailable.
        avg_unit_size_sqft: Typical finished unit size for the market.
        impact_fee_per_unit: Typical government development/impact fees per unit
            (school, park, traffic, water/sewer connection) — a real soft cost.
        source: Provenance tag for observability.
    """

    market: str
    construction_cost_psf: float
    soft_cost_pct: float
    builder_margin_pct: float
    adv_per_unit_default: float
    avg_unit_size_sqft: float = 1000.0
    impact_fee_per_unit: float = 25_000.0
    source: str = "regional_default"


# National fallback — used when state/county are unknown or unmapped.
NATIONAL_DEFAULT = RegionalCostModel(
    market="National (default)",
    construction_cost_psf=200.0,
    soft_cost_pct=20.0,
    builder_margin_pct=25.0,
    adv_per_unit_default=400_000.0,
    avg_unit_size_sqft=1000.0,
    impact_fee_per_unit=25_000.0,
    source="national_default",
)


# Per-market models keyed by an internal market id.
_MARKETS: dict[str, RegionalCostModel] = {
    "south_florida": RegionalCostModel(
        market="South Florida",
        construction_cost_psf=225.0,
        soft_cost_pct=20.0,
        builder_margin_pct=25.0,
        adv_per_unit_default=450_000.0,
        avg_unit_size_sqft=1000.0,
        impact_fee_per_unit=25_000.0,
        source="market:south_florida",
    ),
    "bay_area": RegionalCostModel(
        market="SF Bay Area",
        construction_cost_psf=400.0,
        soft_cost_pct=22.0,
        builder_margin_pct=25.0,
        adv_per_unit_default=900_000.0,
        avg_unit_size_sqft=1100.0,
        impact_fee_per_unit=50_000.0,
        source="market:bay_area",
    ),
    "san_diego": RegionalCostModel(
        market="San Diego",
        construction_cost_psf=350.0,
        soft_cost_pct=22.0,
        builder_margin_pct=25.0,
        adv_per_unit_default=750_000.0,
        avg_unit_size_sqft=1050.0,
        impact_fee_per_unit=40_000.0,
        source="market:san_diego",
    ),
    "sacramento": RegionalCostModel(
        market="Greater Sacramento",
        construction_cost_psf=260.0,
        soft_cost_pct=20.0,
        builder_margin_pct=25.0,
        adv_per_unit_default=500_000.0,
        avg_unit_size_sqft=1050.0,
        impact_fee_per_unit=35_000.0,
        source="market:sacramento",
    ),
    "charlotte": RegionalCostModel(
        market="Charlotte Metro",
        construction_cost_psf=185.0,
        soft_cost_pct=18.0,
        builder_margin_pct=25.0,
        adv_per_unit_default=375_000.0,
        avg_unit_size_sqft=1050.0,
        impact_fee_per_unit=12_000.0,
        source="market:charlotte",
    ),
    "las_vegas": RegionalCostModel(
        market="Las Vegas",
        construction_cost_psf=215.0,
        soft_cost_pct=20.0,
        builder_margin_pct=25.0,
        adv_per_unit_default=420_000.0,
        avg_unit_size_sqft=1050.0,
        impact_fee_per_unit=20_000.0,
        source="market:las_vegas",
    ),
}


# (state, county) → market id. County names are normalized (lowercased, with
# any trailing " county" stripped) before lookup.
_COUNTY_MARKETS: dict[tuple[str, str], str] = {
    # South Florida
    ("FL", "miami-dade"): "south_florida",
    ("FL", "miami dade"): "south_florida",
    ("FL", "broward"): "south_florida",
    ("FL", "palm beach"): "south_florida",
    # SF Bay Area
    ("CA", "alameda"): "bay_area",
    ("CA", "santa clara"): "bay_area",
    ("CA", "san mateo"): "bay_area",
    ("CA", "contra costa"): "bay_area",
    ("CA", "san francisco"): "bay_area",
    ("CA", "marin"): "bay_area",
    # San Diego
    ("CA", "san diego"): "san_diego",
    # Greater Sacramento
    ("CA", "sacramento"): "sacramento",
    ("CA", "placer"): "sacramento",
    # Charlotte metro (NC)
    ("NC", "mecklenburg"): "charlotte",
    ("NC", "cabarrus"): "charlotte",
    ("NC", "iredell"): "charlotte",
    ("NC", "union"): "charlotte",
    ("NC", "gaston"): "charlotte",
    # Las Vegas (NV)
    ("NV", "clark"): "las_vegas",
}


# State-level fallback when the county is unknown but the state is covered.
_STATE_MARKETS: dict[str, str] = {
    "FL": "south_florida",
}


def _normalize_county(county: str) -> str:
    """Lowercase and strip a trailing ' county' for table lookups."""
    c = (county or "").strip().lower()
    if c.endswith(" county"):
        c = c[: -len(" county")]
    return c.strip()


def get_cost_model(state: str, county: str = "") -> RegionalCostModel:
    """Return the best-matching regional cost model.

    Resolution order: (state, county) exact match → state-level default →
    national default.

    Args:
        state: Two-letter state code (e.g. "CA").
        county: County name (with or without a trailing "County").

    Returns:
        The matching ``RegionalCostModel`` (never None).
    """
    st = (state or "").strip().upper()
    county_norm = _normalize_county(county)

    market_id = _COUNTY_MARKETS.get((st, county_norm))
    if market_id is None:
        market_id = _STATE_MARKETS.get(st)
    if market_id is None:
        return NATIONAL_DEFAULT
    return _MARKETS[market_id]
