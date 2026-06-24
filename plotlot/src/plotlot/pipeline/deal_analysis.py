"""Deal analysis orchestration — Steps 2-10 of Dani Kleyman's framework.

Consumes a ZoningReport (Step 1 — zoning analysis already complete) and
executes the downstream underwriting pipeline:

    Step 2:  Fetch rental comps (HUD FMR → RentalCompSet)
    Step 3:  Determine property type → residential vs commercial routing
    Step 4:  Generate unit mix / GLA allocation
    Step 5:  Build stabilized ProformaNOI (annual NOI projection)
    Step 6:  Calculate capital stack (senior debt + sponsor equity)
    Step 7:  Calculate deal metrics (CoC, DSCR, sweat equity)
    Step 8:  Determine go / no-go decision
    Step 9:  Assemble DealAnalysis with investment thesis
    Step 10: Price recommendation + deal-breaker identification

Handles missing data gracefully — falls back to sensible defaults and
flags gaps as low-confidence or deal-breakers. Never fails outright.
"""

from __future__ import annotations

import logging
from typing import Literal

from plotlot.core.types import (
    CapitalStack,
    CompAnalysis,
    DealAnalysis,
    DealMetrics,
    FinancingTerms,
    DensityAnalysis,
    LandProForma,
    ProformaNOI,
    PropertyRecord,
    RentalComp,
    RentalCompSet,
    UnitMixEntry,
    ZoningReport,
)
from plotlot.pipeline.cost_model import get_cost_model
from plotlot.pipeline.county_costs import get_construction_cost_psf
from plotlot.pipeline.deal_metrics import calculate_deal_metrics, determine_go_no_go
from plotlot.pipeline.financing import calculate_capital_stack, calculate_monthly_payment
from plotlot.pipeline.rental_comps import _build_comp_set, default_unit_mix
from plotlot.pipeline.rental_market_comps import (
    MarketCompTarget,
    discover_market_comps,
    market_listings_to_rental_comp_set,
)
from plotlot.observability.tracing import trace

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default assumptions
# ---------------------------------------------------------------------------

_DEFAULT_VACANCY_RATE_PCT = 5.0
_DEFAULT_OPEX_RATIO = 0.38  # fraction of EGI
_DEFAULT_OTHER_INCOME_PCT = 2.0  # % of GPI
_DEFAULT_SOFT_COST_PCT = 20.0  # % of hard costs
_DEFAULT_AVG_UNIT_SIZE_SQFT = 1000.0
_DEFAULT_CONSTRUCTION_COST_PSF = 175.0
_DEFAULT_COMMERCIAL_RENT_PSF_YEAR = 18.0  # low-confidence fallback
_MARKET_COMP_AREA_TOLERANCE = 0.25

# Standard conventional financing terms (non-quoted defaults)
_DEFAULT_FINANCING_TERMS = FinancingTerms(
    loan_type="permanent",
    lender="Conventional Agency (default)",
    loan_to_cost=70.0,
    interest_rate=7.25,
    rate_type="fixed",
    amortization_years=30,
    min_dscr=1.25,
    origination_fee_pct=1.0,
    notes=["Default financing terms — not market-quoted"],
)

# ---------------------------------------------------------------------------
# Property-type routing
# ---------------------------------------------------------------------------

_RESIDENTIAL_TYPES = frozenset({"multifamily", "commercial_mf", "single_family", "land", None})
_COMMERCIAL_TYPES = frozenset({"commercial", "industrial", "retail", "office"})

_SMALL_MF_TYPES = frozenset({"multifamily", "commercial_mf"})

_NOI_MIN_UNITS = 5


def _zillow_comp_to_rental_comp(raw: dict, listing_type: str) -> RentalComp:
    """Convert a Zillow comp dict to a RentalComp dataclass.

    For rental listings, price = monthly rent.
    For sold listings, price = sale price — stored in monthly_rent field
    so _build_comp_set computes median/avg sale price (used as ARV for
    ≤4 unit comp-based valuation per Kleyman Path 1/2).
    """
    sqft = float(raw.get("sqft") or 0)
    price = float(raw.get("price") or 0)
    price_per_sqft = round(price / sqft, 2) if sqft > 0 and price > 0 else 0.0

    return RentalComp(
        address=raw.get("address", ""),
        bedrooms=int(raw.get("bedrooms") or 0),
        bathrooms=float(raw.get("bathrooms") or 0),
        sqft=sqft,
        monthly_rent=price,
        rent_per_sqft=price_per_sqft,
        source="zillow",
    )


def _is_residential(property_type: str | None) -> bool:
    """Determine whether the property type routes through the residential
    (unit-based) or commercial (GLA-based) analysis path.

    ``None`` defaults to residential — most zoning analyses target
    residential land.
    """
    if property_type is None:
        return True
    pt = property_type.lower().strip()
    if pt in _COMMERCIAL_TYPES:
        return False
    return True


async def _fetch_market_fallback_comps(
    zoning_report: ZoningReport,
    property_type: str | None,
    state: str,
    zip_code: str,
    lot_sqft: float,
    density: DensityAnalysis | None,
    property_record: PropertyRecord | None,
) -> RentalCompSet:
    """Resolve Zillow/Redfin comps when HUD results are missing.

    For non-land deals this uses rental listings. For land deals it targets
    sold/new-construction-style listings first, which are useful for land
    development and early-stage value discovery.
    """
    listing_type = _select_market_listing_type(property_type)
    max_gla_sqft = float(density.max_gla_sqft) if density and density.max_gla_sqft else 0.0
    target = _market_comp_target(
        zoning_report=zoning_report,
        property_type=property_type,
        state=state,
        zip_code=zip_code,
        lot_sqft=lot_sqft,
        density_gla_sqft=max_gla_sqft,
        property_record=property_record,
    )

    market_listings = await discover_market_comps(target=target, listing_type=listing_type)
    if not market_listings:
        return RentalCompSet(source=f"Market comps ({listing_type}) - no matches")

    market_comps = market_listings_to_rental_comp_set(
        listings=market_listings,
        source_label="Market comps",
    )
    return _build_comp_set(market_comps, source=f"Market comps ({listing_type})")


def _select_market_listing_type(property_type: str | None) -> Literal["rentals", "sold"]:
    """Return the market listing type for rental-comp fallback."""
    return "sold" if (property_type or "").strip().lower() == "land" else "rentals"


def _derive_city_from_report(zoning_report: ZoningReport) -> str:
    """Best-effort city extraction from municipality or address."""
    if zoning_report.municipality:
        return zoning_report.municipality.strip()

    parts = [part.strip() for part in zoning_report.address.split(",")]
    if len(parts) >= 2 and parts[1]:
        return parts[1]

    return ""


def _market_comp_target(
    zoning_report: ZoningReport,
    property_type: str | None,
    state: str,
    zip_code: str,
    lot_sqft: float,
    density_gla_sqft: float,
    property_record: PropertyRecord | None,
) -> MarketCompTarget:
    """Build a typed `MarketCompTarget` from report context."""
    building_size_sqft = 0.0
    if property_record is not None:
        building_size_sqft = property_record.building_area_sqft or property_record.living_area_sqft

    if building_size_sqft <= 0:
        building_size_sqft = density_gla_sqft

    return MarketCompTarget(
        address=zoning_report.address,
        city=_derive_city_from_report(zoning_report),
        state=state,
        zip_code=zip_code,
        building_size_sqft=building_size_sqft,
        lot_size_sqft=lot_sqft,
        land_deal=(property_type or "").strip().lower() == "land",
        area_tolerance_pct=_MARKET_COMP_AREA_TOLERANCE,
    )


# ---------------------------------------------------------------------------
# Unit mix rent population
# ---------------------------------------------------------------------------


def _populate_unit_mix_rents(
    unit_mix: list[UnitMixEntry],
    rental_comps: RentalCompSet,
) -> list[UnitMixEntry]:
    """Match rental comps to unit-mix entries by unit type.

    For each unit type in the mix (studio, 1BR, 2BR, ...), collects all
    matching RentalComp entries from the comp set, computes the median
    rent, and stamps it onto the UnitMixEntry.

    When no comps match a unit type, falls back to a bedroom-count match
    (e.g., 2BR comps for a "2BR" entry). If still nothing matches, uses
    the comp-set median rent as a universal fallback.
    """
    # Index comps by unit_type
    by_type: dict[str, list[float]] = {}
    for comp in rental_comps.comps:
        if comp.monthly_rent > 0:
            key = comp.unit_type.lower().strip()
            by_type.setdefault(key, []).append(comp.monthly_rent)

    # Also index by bedroom count for fallback matching
    by_beds: dict[int, list[float]] = {}
    for comp in rental_comps.comps:
        if comp.monthly_rent > 0:
            by_beds.setdefault(comp.bedrooms, []).append(comp.monthly_rent)

    universal_median = rental_comps.median_rent

    populated: list[UnitMixEntry] = []
    for entry in unit_mix:
        rents: list[float] = []

        # Exact unit-type match (case-insensitive)
        unit_key = entry.unit_type.lower().strip()
        if unit_key in by_type:
            rents = by_type[unit_key]

        # Fallback: bedroom-count match
        if not rents and entry.bedrooms in by_beds:
            rents = by_beds[entry.bedrooms]

        median = _median_sorted(sorted(rents)) if rents else universal_median

        monthly_rent = round(median, 2)
        rent_psf = round(monthly_rent / entry.sqft, 2) if entry.sqft > 0 else 0.0
        populated.append(
            UnitMixEntry(
                unit_type=entry.unit_type,
                bedrooms=entry.bedrooms,
                bathrooms=entry.bathrooms,
                sqft=entry.sqft,
                unit_count=entry.unit_count,
                percentage_of_total=entry.percentage_of_total,
                monthly_rent=monthly_rent,
                rent_per_sqft=rent_psf,
            )
        )

    return populated


def _median_sorted(sorted_vals: list[float]) -> float:
    """Median from an already-sorted list."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0
    return sorted_vals[mid]


# ---------------------------------------------------------------------------
# Step 5: build_proforma_noi — stabilized NOI projection
# ---------------------------------------------------------------------------


def build_proforma_noi(
    unit_mix: list[UnitMixEntry],
    vacancy_rate_pct: float = _DEFAULT_VACANCY_RATE_PCT,
    opex_ratio: float = _DEFAULT_OPEX_RATIO,
    other_income_pct: float = _DEFAULT_OTHER_INCOME_PCT,
) -> ProformaNOI:
    """Build a stabilized annual ProformaNOI from a populated unit mix.

    Each **UnitMixEntry** must have ``monthly_rent`` and ``unit_count``
    populated (see :func:`_populate_unit_mix_rents`).  The function sums
    total monthly gross potential rent, annualizes it, applies vacancy,
    adds other income, and subtracts modelled operating expenses.

    Returns a fully-populated ``ProformaNOI``.  When ``unit_mix`` is
    empty, returns a zeroed NOI.
    """
    if not unit_mix:
        return ProformaNOI(notes=["Empty unit mix — zero NOI"])

    total_monthly_gpr = sum(entry.monthly_rent * entry.unit_count for entry in unit_mix)
    total_unit_count = sum(e.unit_count for e in unit_mix)

    gross_potential_rent = total_monthly_gpr * 12.0
    other_income = gross_potential_rent * (other_income_pct / 100.0)
    vacancy_loss = gross_potential_rent * (vacancy_rate_pct / 100.0)
    effective_gross_income = gross_potential_rent + other_income - vacancy_loss

    total_operating_expenses = effective_gross_income * opex_ratio
    noi = effective_gross_income - total_operating_expenses

    expense_ratio = (
        (total_operating_expenses / effective_gross_income) * 100.0
        if effective_gross_income > 0
        else 0.0
    )

    return ProformaNOI(
        unit_mix=unit_mix,
        total_units=total_unit_count,
        gross_monthly_income=round(total_monthly_gpr, 2),
        gross_annual_income=round(gross_potential_rent, 2),
        vacancy_rate_pct=vacancy_rate_pct,
        operating_expense_ratio_pct=round(opex_ratio * 100.0, 2),
        operating_expenses=round(total_operating_expenses, 2),
        effective_gross_income=round(effective_gross_income, 2),
        net_operating_income=round(noi, 2),
        monthly_noi=round(noi / 12.0, 2),
        expense_items={
            "other_income": round(other_income, 2),
            "vacancy_loss": round(vacancy_loss, 2),
            "expense_ratio_pct": round(expense_ratio, 2),
        },
        notes=[
            f"opex_ratio={opex_ratio:.2f}",
            f"units={total_unit_count}",
            f"monthly_gpr={total_monthly_gpr:,.0f}",
        ],
    )


# ---------------------------------------------------------------------------
# Commercial NOI — GLA-based (no unit mix)
# ---------------------------------------------------------------------------


def _build_commercial_noi(
    max_gla_sqft: float,
    rent_psf_year: float = _DEFAULT_COMMERCIAL_RENT_PSF_YEAR,
    vacancy_rate_pct: float = _DEFAULT_VACANCY_RATE_PCT,
    opex_ratio: float = _DEFAULT_OPEX_RATIO,
) -> ProformaNOI:
    """Build a stabilized NOI for a commercial property from GLA.

    Commercial properties don't use unit counts — income is driven by
    leasable square footage and a per-square-foot annual rent.
    """
    if max_gla_sqft <= 0:
        return ProformaNOI(notes=["Zero GLA — cannot build commercial NOI"])

    gross_potential_rent = max_gla_sqft * rent_psf_year
    vacancy_loss = gross_potential_rent * (vacancy_rate_pct / 100.0)
    effective_gross_income = gross_potential_rent - vacancy_loss
    total_operating_expenses = effective_gross_income * opex_ratio
    noi = effective_gross_income - total_operating_expenses

    expense_ratio = (
        (total_operating_expenses / effective_gross_income) * 100.0
        if effective_gross_income > 0
        else 0.0
    )

    return ProformaNOI(
        unit_mix=[],
        total_units=0,
        gross_monthly_income=0.0,
        gross_annual_income=round(gross_potential_rent, 2),
        vacancy_rate_pct=vacancy_rate_pct,
        operating_expense_ratio_pct=round(opex_ratio * 100.0, 2),
        operating_expenses=round(total_operating_expenses, 2),
        effective_gross_income=round(effective_gross_income, 2),
        net_operating_income=round(noi, 2),
        monthly_noi=round(noi / 12.0, 2),
        expense_items={
            "vacancy_loss": round(vacancy_loss, 2),
            "expense_ratio_pct": round(expense_ratio, 2),
        },
        notes=[
            f"commercial_gla={max_gla_sqft:,.0f}sqft",
            f"rent_psf_year=${rent_psf_year:.2f}",
        ],
    )


# ---------------------------------------------------------------------------
# Cost extraction helpers
# ---------------------------------------------------------------------------


def _extract_hard_soft_costs(
    units: int,
    pro_forma: LandProForma | None,
    construction_cost_psf: float,
    avg_unit_size_sqft: float,
    soft_cost_pct: float,
) -> tuple[float, float]:
    """Return (hard_costs, soft_costs) preferring pro_forma values."""
    if pro_forma is not None and pro_forma.hard_costs > 0:
        hard = pro_forma.hard_costs
        soft = pro_forma.soft_costs if pro_forma.soft_costs > 0 else hard * (soft_cost_pct / 100.0)
        return hard, soft

    if units <= 0:
        return 0.0, 0.0

    hard = units * construction_cost_psf * avg_unit_size_sqft
    soft = hard * (soft_cost_pct / 100.0)
    return hard, soft


def _extract_land_and_value(
    land_purchase_price: float,
    units: int,
    pro_forma: LandProForma | None,
    comp_analysis: "CompAnalysis | None",
    lot_size_sqft: float,
) -> tuple[float, float, float, float]:
    """Return (land_value, land_value_per_unit, land_value_per_acre, as_built_value).

    Precedence: land_purchase_price > pro_forma.max_land_price >
    comp_analysis.estimated_land_value > cost-based fallback.
    """
    land_value = land_purchase_price

    if land_value <= 0 and pro_forma is not None and pro_forma.max_land_price > 0:
        land_value = pro_forma.max_land_price

    if land_value <= 0 and comp_analysis is not None and comp_analysis.estimated_land_value > 0:
        land_value = comp_analysis.estimated_land_value

    lv_per_unit = land_value / units if units > 0 else 0.0

    acres = lot_size_sqft / 43560.0 if lot_size_sqft > 0 else 0.0
    lv_per_acre = land_value / acres if acres > 0 else 0.0

    as_built = 0.0
    if pro_forma is not None and pro_forma.gross_development_value > 0:
        as_built = pro_forma.gross_development_value

    return land_value, lv_per_unit, lv_per_acre, as_built


# ---------------------------------------------------------------------------
# Investment rating mapper
# ---------------------------------------------------------------------------

_VERDICT_TO_RATING: dict[str, str] = {
    "strong_go": "Strong Buy",
    "go": "Buy",
    "no_go": "Pass",
}


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


@trace(name="run_deal_analysis", span_type="TOOL")
async def run_deal_analysis(
    zoning_report: ZoningReport,
    county: str,
    state: str,
    land_purchase_price: float,
    zip_code: str = "",
) -> DealAnalysis:
    """Orchestrate Steps 2-10 of the deal underwriting pipeline.

    Consumes a complete **ZoningReport** (Step 1 already done) and
    runs the downstream steps:

    1. Fetch rental comps (HUD FMR)
    2. Route residential vs commercial
    3. Generate unit mix / commercial GLA allocation
    4. Match rents to unit types
    5. Build stabilized ProformaNOI
    6. Calculate capital stack
    7. Calculate deal metrics
    8. Determine go / no-go
    9. Assemble DealAnalysis with recommendation

    Every step degrades gracefully — missing data produces a partial
    **DealAnalysis** with ``deal_breakers`` and low ``confidence``.

    Args:
        zoning_report: Completed ZoningReport from Step 1.
        county: County name (e.g., ``"miami_dade"``, ``"Mecklenburg"``).
        state: Two-letter state code (e.g., ``"FL"``, ``"NC"``).
        land_purchase_price: Asking or contract price for the land ($).
        zip_code: Optional ZIP code for rental-comp resolution
                  (HUD FMR is county-level; ZIP is retained for
                  future granularity).

    Returns:
        A fully assembled **DealAnalysis**.
    """
    # ── Bootstrap ──────────────────────────────────────────────────────────
    density = zoning_report.density_analysis
    comps = zoning_report.comp_analysis
    pro_forma = zoning_report.pro_forma
    numeric = zoning_report.numeric_params
    prop_record = zoning_report.property_record

    property_type = numeric.property_type if numeric and numeric.property_type else "multifamily"
    max_units = density.max_units if density else 0
    max_gla = density.max_gla_sqft if density else 0.0
    lot_sqft = (
        density.lot_size_sqft
        if density and density.lot_size_sqft > 0
        else (prop_record.lot_size_sqft if prop_record else 0.0)
    )

    notes: list[str] = []
    deal_breakers: list[str] = []
    confidence = "medium"

    # ── Residential / commercial routing ───────────────────────────────────
    is_res = _is_residential(property_type)

    # ── Step 2: Fetch comps via Zillow skill (primary) ─────────────────────
    rental_comp_set: RentalCompSet
    try:
        from plotlot.pipeline.skills.playwright_comps import handle_fetch_zillow_comps

        if property_type == "land":
            zillow_listing_type = "land"
        elif max_units >= _NOI_MIN_UNITS:
            zillow_listing_type = "rental"
        elif property_type in _SMALL_MF_TYPES and max_units >= 2:
            zillow_listing_type = "small_mf"
        else:
            zillow_listing_type = "new_build"
        # "renovated" scenario is opt-in only (manual listing_type override) — no auto-routing
        comp_result = await handle_fetch_zillow_comps({
            "address": zoning_report.formatted_address or zoning_report.address,
            "listing_type": zillow_listing_type,
            "max_results": 25,
        })
        zillow_comps_raw = comp_result.output_json.get("comparables", [])
        if zillow_comps_raw:
            zillow_comps = [
                _zillow_comp_to_rental_comp(c, zillow_listing_type)
                for c in zillow_comps_raw
            ]
            rental_comp_set = _build_comp_set(zillow_comps, source=f"Zillow ({zillow_listing_type})")
            notes.append(f"Comps from Zillow skill: {len(zillow_comps)} {zillow_listing_type} listings")
        else:
            rental_comp_set = RentalCompSet(
                source="Zillow skill — no results",
                comps=[],
                comp_count=0,
            )
            notes.append("Zillow comps skill returned no listings")
    except Exception as exc:
        logger.warning("Zillow comp fetch failed: %s", exc)
        rental_comp_set = RentalCompSet(
            source="fetch error",
            comps=[],
            comp_count=0,
        )
        notes.append(f"Comps unavailable: {exc}")
        if confidence == "medium":
            confidence = "low"

    if is_res and rental_comp_set.comp_count == 0:
        try:
            market_comps = await _fetch_market_fallback_comps(
                zoning_report=zoning_report,
                property_type=property_type,
                state=state,
                zip_code=zip_code,
                lot_sqft=lot_sqft,
                density=density,
                property_record=prop_record,
            )
            if market_comps.comp_count > 0:
                rental_comp_set = market_comps
                notes.append("HUD rental comps unavailable — using market fallback (Zillow/Redfin)")
            else:
                notes.append("Market comp fallback returned no usable units")
        except Exception as exc:
            logger.warning("Market comp fallback failed: %s", exc)
            notes.append(f"Market comp fallback unavailable: {exc}")

    if rental_comp_set.comp_count == 0:
        notes.append("No rental comparables — NOI will be zero or imputed")
        confidence = "low"

    # ── Steps 3-4: Unit mix / commercial allocation ────────────────────────
    unit_mix: list[UnitMixEntry] = []

    if is_res and max_units >= _NOI_MIN_UNITS:
        raw_mix = default_unit_mix(property_type=property_type, max_units=max_units)
        unit_mix = _populate_unit_mix_rents(raw_mix, rental_comp_set)
    elif is_res and 0 < max_units < _NOI_MIN_UNITS:
        notes.append(
            f"≤4 units ({max_units}) — comp-based valuation "
            "(NOI approach reserved for ≥5 unit multifamily per Dani Kleyman)"
        )
    elif not is_res:
        notes.append(f"Commercial routing (property_type={property_type})")
    else:
        deal_breakers.append("No max units available — density analysis is empty")
        confidence = "low"

    # ── Step 5: Build ProformaNOI (only for ≥5-unit residential or commercial) ─
    proforma_noi: ProformaNOI
    if is_res and max_units >= _NOI_MIN_UNITS:
        proforma_noi = build_proforma_noi(unit_mix)
    elif not is_res:
        # Commercial: GLA-based NOI
        if max_gla and max_gla > 0:
            proforma_noi = _build_commercial_noi(max_gla_sqft=max_gla)
        else:
            proforma_noi = ProformaNOI(
                notes=["Commercial property with no GLA — cannot compute NOI"]
            )
            deal_breakers.append("Commercial property has no GLA data — NOI cannot be computed")
            confidence = "low"
    else:
        # Residential ≤4 units — comp-based, skip NOI
        proforma_noi = ProformaNOI(
            notes=[f"≤4 units ({max_units}) — comp-based valuation, NOI not computed"]
        )

    if proforma_noi.net_operating_income <= 0:
        logger.warning("ProformaNOI is zero or negative — deal may not pencil")
        notes.append("Stabilized NOI is zero — check rent comps and unit mix")
        if confidence == "medium":
            confidence = "low"

    # ── Construction costs ─────────────────────────────────────────────────
    construction_psf = get_construction_cost_psf(county, state)
    avg_unit_sqft = (
        sum(e.sqft * e.unit_count for e in unit_mix) / sum(e.unit_count for e in unit_mix)
        if unit_mix and sum(e.unit_count for e in unit_mix) > 0
        else _DEFAULT_AVG_UNIT_SIZE_SQFT
    )
    hard_costs, soft_costs = _extract_hard_soft_costs(
        units=max_units if is_res else 0,
        pro_forma=pro_forma,
        construction_cost_psf=construction_psf,
        avg_unit_size_sqft=avg_unit_sqft,
        soft_cost_pct=_DEFAULT_SOFT_COST_PCT,
    )

    # ── Step 6: Capital stack ───────────────────────────────────────────────
    monthly_noi = proforma_noi.net_operating_income / 12.0
    financing_terms = _DEFAULT_FINANCING_TERMS

    capital_stack: CapitalStack
    try:
        capital_stack = calculate_capital_stack(
            land_cost=land_purchase_price if land_purchase_price > 0 else 0.0,
            hard_costs=hard_costs,
            soft_costs=soft_costs,
            monthly_noi=monthly_noi,
            financing_terms=financing_terms,
        )
    except Exception as exc:
        logger.warning("Capital stack calculation failed: %s", exc)
        capital_stack = CapitalStack(
            total_project_cost=land_purchase_price + hard_costs + soft_costs,
            notes=[f"Calculation error: {exc}"],
        )
        notes.append(f"Capital stack error: {exc}")
        confidence = "low"

    if capital_stack.sponsor_equity < 0:
        deal_breakers.append(
            f"Negative sponsor equity (${capital_stack.sponsor_equity:,.0f}) — "
            "project cost exceeds debt capacity"
        )

    # ── Step 7: Deal metrics ───────────────────────────────────────────────
    monthly_debt_service = 0.0
    if capital_stack.senior_debt > 0 and financing_terms.interest_rate > 0:
        monthly_debt_service = calculate_monthly_payment(
            principal=capital_stack.senior_debt,
            annual_rate_pct=financing_terms.interest_rate,
            term_years=financing_terms.amortization_years,
        )

    land_val, lv_per_unit, lv_per_acre, as_built = _extract_land_and_value(
        land_purchase_price=land_purchase_price,
        units=max_units,
        pro_forma=pro_forma,
        comp_analysis=comps,
        lot_size_sqft=lot_sqft,
    )

    cash_invested = capital_stack.sponsor_equity if capital_stack.sponsor_equity > 0 else 0.0
    total_cost = capital_stack.total_project_cost

    metrics: DealMetrics
    try:
        metrics = calculate_deal_metrics(
            monthly_noi=monthly_noi,
            monthly_debt_service=monthly_debt_service,
            cash_invested=cash_invested,
            as_built_value=as_built,
            total_cost=total_cost,
        )
    except Exception as exc:
        logger.warning("Deal metrics calculation failed: %s", exc)
        metrics = DealMetrics(notes=[f"Calculation error: {exc}"])
        notes.append(f"Deal metrics error: {exc}")
        confidence = "low"

    # ── Step 8: Go / no-go ─────────────────────────────────────────────────
    coc_verdict, se_verdict, overall_verdict = determine_go_no_go(metrics)
    investment_rating = _VERDICT_TO_RATING.get(overall_verdict, "Hold")

    # ── Step 9: Price recommendation ───────────────────────────────────────
    max_offer = 0.0
    arv = 0.0

    if pro_forma is not None and pro_forma.max_land_price > 0:
        max_offer = pro_forma.max_land_price
    elif land_val > 0:
        max_offer = land_val

    if max_offer <= 0 and is_res and max_units < _NOI_MIN_UNITS:
        arv = rental_comp_set.median_rent if rental_comp_set.comp_count > 0 else 0.0
        if arv > 0:
            max_offer = arv * 0.70 - hard_costs - soft_costs
            notes.append(
                f"ARV-based valuation: ARV=${arv:,.0f} (median of "
                f"{rental_comp_set.comp_count} sold comps), max offer=${max_offer:,.0f} "
                f"(70% ARV - ${hard_costs + soft_costs:,.0f} construction)"
            )

    if max_offer <= 0 and not is_res and proforma_noi.net_operating_income > 0:
        cost_model = get_cost_model(state, county)
        cap_rate = cost_model.cap_rate if cost_model.cap_rate > 0 else 5.5
        arv = proforma_noi.net_operating_income / (cap_rate / 100.0)
        if arv > 0:
            max_offer = arv * 0.80 - hard_costs - soft_costs
            notes.append(
                f"NOI-based valuation (income approach): "
                f"Annual NOI=${proforma_noi.net_operating_income:,.0f}, "
                f"cap rate={cap_rate}%, ARV=${arv:,.0f}, "
                f"max offer=${max_offer:,.0f} (80% ARV - ${hard_costs + soft_costs:,.0f} construction)"
            )

    if max_offer <= 0 and not is_res and rental_comp_set.comp_count > 0:
        arv = rental_comp_set.median_rent
        if arv > 0:
            max_offer = arv * 0.70 - hard_costs - soft_costs
            notes.append(
                f"ARV-based valuation (commercial comp fallback): "
                f"ARV=${arv:,.0f} (median of {rental_comp_set.comp_count} sold comps), "
                f"max offer=${max_offer:,.0f} (70% ARV - ${hard_costs + soft_costs:,.0f} construction)"
            )

    # Recommended offer: 85% of max for conservative underwriting
    recommended_offer = round(max_offer * 0.85, 2) if max_offer > 0 else 0.0

    # ── Deal-breaker checks ────────────────────────────────────────────────
    if overall_verdict == "no_go":
        deal_breakers.append(
            f"Go/no-go returned '{overall_verdict}' (CoC={coc_verdict}, SE={se_verdict})"
        )

    if max_offer <= 0 and land_purchase_price <= 0:
        deal_breakers.append("No land price data — cannot price the deal")

    if monthly_noi <= 0:
        deal_breakers.append("Stabilized NOI is zero — check rental comps and unit assumptions")

    if investment_rating == "Pass":
        deal_breakers.append("Investment thesis does not support purchase")

    # ── Step 10: Assemble DealAnalysis ─────────────────────────────────────
    notes.append("pipeline=deal_analysis v2")
    notes.append(f"property_type={property_type}")
    notes.append(f"routing={'residential' if is_res else 'commercial'}")

    return DealAnalysis(
        address=zoning_report.address,
        municipality=zoning_report.municipality,
        county=county,
        property_type=property_type,
        max_units=max_units,
        # Value
        estimated_land_value=round(land_val, 2),
        estimated_land_value_per_unit=round(lv_per_unit, 2),
        estimated_land_value_per_acre=round(lv_per_acre, 2),
        # Sub-components
        comp_analysis=comps,
        pro_forma=pro_forma,
        proforma_noi=proforma_noi,
        rental_comp_set=rental_comp_set,
        unit_mix=unit_mix,
        # Financing
        financing_terms=financing_terms,
        capital_stack=capital_stack,
        # Metrics + decision
        metrics=metrics,
        max_offer_price=max_offer,
        recommended_offer=recommended_offer,
        investment_rating=investment_rating,
        deal_breakers=deal_breakers,
        # Meta
        summary=(
            f"{investment_rating}: {max_units} units on {lot_sqft:,.0f} sqft in "
            f"{zoning_report.municipality}, {state}. "
            f"Max offer: ${max_offer:,.0f} "
            f"(recommended: ${recommended_offer:,.0f}). "
            f"CoC: {metrics.levered_cash_on_cash:.1f}%, "
            f"DSCR: {metrics.dscr:.2f}."
            if max_units > 0
            else f"Incomplete analysis — {len(deal_breakers)} deal-breaker(s)"
        ),
        notes=notes,
        confidence=confidence,
    )
