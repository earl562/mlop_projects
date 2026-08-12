"""Full single-address analysis used by batch screening.

``lookup_address`` runs geocode → property → zoning → LLM extraction → density
(and extraction verification). This wraps it with the residual pro forma so a
report can be ranked by "what it's worth."

For batch screening the residual is computed from the **regional cost-model
ADV** by default (no per-address comparable-sales network call) — fast enough to
screen a list, with full comps reserved for the shortlist. Set ``with_comps`` to
pull live sold-unit comps for a deeper pass.
"""

from __future__ import annotations

import asyncio
import logging

from plotlot.core.types import ZoningReport
from plotlot.pipeline.comps import find_comparables
from plotlot.pipeline.cost_model import get_cost_model
from plotlot.pipeline.guardrails import check_residual_plausibility
from plotlot.pipeline.lookup import lookup_address
from plotlot.pipeline.proforma import calculate_land_pro_forma

logger = logging.getLogger(__name__)


async def analyze_property_full(address: str, *, with_comps: bool = False) -> ZoningReport | None:
    """Analyze an address and attach a residual pro forma for ranking.

    Args:
        address: Street address.
        with_comps: If True, run live comparable-sales lookup; otherwise rank on
            the regional cost-model ADV (faster for batch screening).

    Returns:
        ZoningReport with ``pro_forma`` populated, or None if geocoding fails.
    """
    report: ZoningReport | None = await lookup_address(address)
    if report is None:
        return None

    density = report.density_analysis
    if density is None or density.max_units <= 0:
        if density is not None and density.max_gla_sqft:
            report.warnings = list(report.warnings or []) + [
                "Commercial pro forma not yet implemented — only residential density is calculated."
            ]
        return report

    cost_model = get_cost_model(report.state, report.county)

    comps = None
    if with_comps and report.property_record and report.property_record.lat:
        try:
            comps = await find_comparables(report.property_record, state=report.state or "FL")
            report.comp_analysis = comps
        except Exception as exc:  # non-blocking — fall back to regional ADV
            logger.warning("Comps lookup failed for %s: %s", address[:60], exc)

    report.pro_forma = calculate_land_pro_forma(density=density, comps=comps, cost_model=cost_model)

    lot_sqft = report.property_record.lot_size_sqft if report.property_record else 0.0
    report.warnings = list(report.warnings or []) + check_residual_plausibility(
        density, lot_sqft, report.pro_forma
    )
    return report


async def analyze_property_deep(
    address: str, *, adv_per_unit: float | None = None
) -> ZoningReport | None:
    """Full grounded single-address analysis for the chat agent.

    Args:
        address: Street address or APN.
        adv_per_unit: Caller-supplied after-development value per finished unit,
            overriding both comps and the regional default. This exists because
            automated comps are genuinely unavailable in some markets — no free
            California sold-price layer exists, so a San Diego exit value is a
            labelled regional default unless a keyed provider is live. Without an
            input port, an analyst who has done the comping by hand can only
            eyeball their number against ours; with one, the residual, the offer
            and the sensitivity grid are all rebuilt from their figure. It is
            recorded as ``adv_source="override"`` and reported as user-supplied —
            never laundered into looking like a PlotLot-derived comp.

    Runs the same deterministic composition the ``/analyze`` SSE pipeline runs —
    geocode → property → zoning → LLM extraction → **verification** → density,
    then comps → residual pro forma → sensitivity → entitlement → site risk →
    California density uplift — but without streaming.

    This exists so the conversational agent can *cite grounded numbers* (units,
    land value, residual offer, impact fees, flood/coastal/wetland risk,
    entitlement path) instead of free-forming them from the model's own
    knowledge. Every value on the returned report is produced by the
    deterministic pipeline and tagged with its verification status, so the
    agent never restates a hallucinated figure as fact.

    Each enrichment step is non-blocking: a failure in comps, site risk, etc.
    leaves the verified density intact rather than failing the whole answer.

    Returns:
        Fully-populated ``ZoningReport``, or None if geocoding fails.
    """
    report: ZoningReport | None = await lookup_address(address)
    if report is None:
        return None

    density = report.density_analysis
    if density is None or density.max_units <= 0:
        # No residential unit count to build a deal on — still return the report
        # (zoning + verification) so the agent can answer truthfully about why.
        return report

    state = report.state or "FL"
    county = report.county or ""
    cost_model = get_cost_model(state, county)

    apn = report.property_record.folio if report.property_record else ""

    # Entitlement is deterministic (no network) and feeds the timeline-risk task,
    # so compute it before launching the concurrent augmentations below.
    try:
        from plotlot.pipeline.entitlement import assess_entitlement

        report.entitlement = assess_entitlement(report)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Deep entitlement failed for %s: %s", address[:60], exc)

    # ── Concurrent network augmentations ──
    # These were the dominant latency cost when run serially (~25s). They are
    # mutually independent (each writes a different report field), so run them
    # together — wall time collapses to the slowest one. Each is individually
    # bounded and self-contained; one failure never blocks the others.
    async def _aug_comps() -> None:
        if report.property_record and report.property_record.lat:
            report.comp_analysis = await asyncio.wait_for(
                find_comparables(report.property_record, state=state), timeout=20
            )

    async def _aug_site_risk() -> None:
        if report.lat and report.lng:
            from plotlot.pipeline.site_risk import fetch_site_risk

            report.site_risk = await asyncio.wait_for(
                fetch_site_risk(report.lat, report.lng), timeout=12
            )

    async def _aug_terrain() -> None:
        record = report.property_record
        if record and record.parcel_geometry:
            from plotlot.property.terrain import analyze_terrain

            report.terrain = await asyncio.wait_for(
                analyze_terrain(record.parcel_geometry), timeout=15
            )

    async def _aug_permits() -> None:
        if apn and county:
            from plotlot.pipeline.permits import fetch_development_signals

            report.development_signals = await asyncio.wait_for(
                fetch_development_signals(apn, county), timeout=12
            )

    async def _aug_timeline() -> None:
        if report.entitlement:
            import re as _re

            from plotlot.pipeline.entitlement_timeline import assess_timeline_risk

            _addr = report.formatted_address or report.address
            _zip_m = _re.search(r"\b(\d{5})(?:-\d{4})?\b", _addr or "")
            report.entitlement_timeline_risk = await asyncio.wait_for(
                assess_timeline_risk(
                    address=_addr,
                    municipality=report.municipality,
                    county=report.county,
                    state=report.state,
                    entitlement_path=report.entitlement.path,
                    entitlement_complexity=report.entitlement.complexity,
                    apn=apn,
                    lat=report.lat,
                    lng=report.lng,
                    parcel_zip=_zip_m.group(1) if _zip_m else "",
                    owner=report.property_record.owner if report.property_record else "",
                ),
                timeout=18,
            )

    _aug_names = ("comps", "site risk", "terrain", "permits", "timeline risk")
    _aug_results = await asyncio.gather(
        _aug_comps(),
        _aug_site_risk(),
        _aug_terrain(),
        _aug_permits(),
        _aug_timeline(),
        return_exceptions=True,
    )
    for _name, _res in zip(_aug_names, _aug_results):
        if isinstance(_res, Exception):
            logger.warning("Deep %s failed for %s: %s", _name, address[:60], _res)

    # Opposition risk — DETERMINISTIC only (instant, no I/O). The qualitative LLM
    # enrichment is intentionally OFF the critical path (it was ~10–25s on the slow
    # narrator); it runs lazily/on-demand via assess_opposition_risk(). The
    # deterministic risk level is the trustworthy signal and still grounds the chat.
    try:
        from plotlot.pipeline.opposition_risk import assess_opposition_risk_basic

        report.opposition_risk = assess_opposition_risk_basic(
            max_units=density.max_units,
            zoning_district=report.zoning_district,
            municipality=report.municipality,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Deep opposition risk failed for %s: %s", address[:60], exc)

    # ── Deterministic finalizers (depend on the concurrent results) ──
    # Residual pro forma + sensitivity. Use a registered itemized fee schedule
    # when one exists so the residual's impact fee matches the entitlement's
    # (else the coarse regional aggregate). Only let a schedule drive the residual
    # when it covers ALL per-unit fees — a partial schedule (e.g. SD city DIFs)
    # is itemized for display but must not lower the residual below the
    # conservative coarse all-in, else the max land price is overstated.
    from plotlot.pipeline.fee_schedule import get_fee_schedule

    fee_schedule = get_fee_schedule(report.state, report.county)
    fee_override = (
        fee_schedule.total_per_unit
        if (fee_schedule and fee_schedule.is_itemized and fee_schedule.covers_all_fees)
        else None
    )
    try:
        from plotlot.pipeline.sensitivity import build_sensitivity_table

        report.pro_forma = calculate_land_pro_forma(
            density=density,
            comps=report.comp_analysis,
            cost_model=cost_model,
            impact_fees_per_unit=fee_override,
            adv_per_unit=adv_per_unit,
        )
        # The sensitivity grid must sweep around the SAME base the residual used.
        # Centring it on a $750k regional default while the residual runs off a
        # hand-supplied comp would produce a grid that never contains the answer.
        report.sensitivity = build_sensitivity_table(
            density=density,
            comps=report.comp_analysis,
            cost_model=cost_model,
            adv_per_unit=adv_per_unit,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Deep pro forma failed for %s: %s", address[:60], exc)

    try:
        from plotlot.pipeline.entitlement import assess_entitlement

        report.entitlement = assess_entitlement(report)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Deep entitlement failed for %s: %s", address[:60], exc)

    lot_sqft = report.property_record.lot_size_sqft if report.property_record else 0.0
    if report.pro_forma is not None:
        report.warnings = list(report.warnings or []) + check_residual_plausibility(
            density, lot_sqft, report.pro_forma
        )

    # California state-program upside (ADU / SB9 / Density Bonus) — additive,
    # base stays firm; SB9 gated on the flood/wetland hazards fetched above.
    if state.upper() == "CA" and density.max_units > 0:
        try:
            from plotlot.pipeline.density_bonus import compute_density_uplift

            sr = report.site_risk
            report.density_uplift = compute_density_uplift(
                density.max_units,
                state=state,
                property_type=(
                    report.numeric_params.property_type or "" if report.numeric_params else ""
                ),
                base_is_provisional=bool(
                    report.extraction_verification
                    and report.extraction_verification.offer_is_provisional
                ),
                in_flood_hazard=bool(sr and sr.flood_zone and sr.flood_zone.in_sfha),
                has_wetlands=bool(sr and sr.has_wetlands),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Deep density uplift failed for %s: %s", address[:60], exc)

    # Development-activity signals — does the city permit system show this parcel
    # already in active development? Keeps the agent from pitching an entitled,
    # developer-owned site as raw land. Non-blocking; APN-keyed (address queries
    # on the permit layer return wrong cross-street results).
    apn = report.property_record.folio if report.property_record else ""
    if apn and county:
        try:
            from plotlot.pipeline.permits import fetch_development_signals

            report.development_signals = await asyncio.wait_for(
                fetch_development_signals(apn, county), timeout=15
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Deep development signals failed for %s: %s", address[:60], exc)

    # Entitlement timeline risk — real CEQAnet filings + permit check (CA).
    if report.entitlement:
        try:
            import re as _re

            from plotlot.pipeline.entitlement_timeline import assess_timeline_risk

            _addr = report.formatted_address or report.address
            _zip_m = _re.search(r"\b(\d{5})(?:-\d{4})?\b", _addr or "")
            report.entitlement_timeline_risk = await asyncio.wait_for(
                assess_timeline_risk(
                    address=_addr,
                    municipality=report.municipality,
                    county=report.county,
                    state=report.state,
                    entitlement_path=report.entitlement.path,
                    entitlement_complexity=report.entitlement.complexity,
                    apn=apn,
                    lat=report.lat,
                    lng=report.lng,
                    parcel_zip=_zip_m.group(1) if _zip_m else "",
                    owner=report.property_record.owner if report.property_record else "",
                ),
                timeout=25,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Deep timeline risk failed for %s: %s", address[:60], exc)

    # Neighbor / political opposition risk — qualitative LLM-based assessment.
    try:
        from plotlot.pipeline.opposition_risk import assess_opposition_risk

        density = report.density_analysis
        max_units = density.max_units if density else None
        report.opposition_risk = await asyncio.wait_for(
            assess_opposition_risk(
                address=report.formatted_address or report.address,
                municipality=report.municipality,
                county=report.county,
                state=report.state,
                max_units=max_units,
                zoning_district=report.zoning_district,
                lat=report.lat,
                lng=report.lng,
            ),
            timeout=25,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Deep opposition risk failed for %s: %s", address[:60], exc)

    return report
