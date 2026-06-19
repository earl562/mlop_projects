"""RentCast comparable-sales provider.

A keyed JSON comps API used as the fallback exit-value (ADV-per-unit) source for
markets with no open arms-length-sales GIS layer — California counties (e.g. San
Diego) being the motivating case. Unlike the ArcGIS-layer sources in
``comps_sources``, RentCast returns comps directly, so this returns a fully
formed ``CompAnalysis``.

Used only when the free ArcGIS path (curated registry + Hub discovery) finds
nothing, to conserve the free tier (~50 req/mo). No key configured → returns
None and the pipeline falls back to the labeled regional default (honest, not
fabricated).

Docs: https://developers.rentcast.io  (GET /avm/value → value + comparables[]).
"""

from __future__ import annotations

import logging
import statistics

import httpx

from plotlot.config import settings
from plotlot.core.types import ComparableSale, CompAnalysis, PropertyRecord

logger = logging.getLogger(__name__)

_RENTCAST_AVM_URL = "https://api.rentcast.io/v1/avm/value"

# New multifamily units exit as condos/townhomes — query that segment so the
# returned comps reflect finished-unit sale prices, not large SFR lots.
_DEFAULT_PROPERTY_TYPE = "Condo"
_DEFAULT_UNIT_SQFT = 1000  # representative finished-unit size for the AVM


def rentcast_configured() -> bool:
    """True when a RentCast API key is available."""
    return bool(getattr(settings, "rentcast_api_key", "") or "")


def _percentiles(values: list[float]) -> tuple[float, float, float]:
    """(p25, median, p75) of positive values; zeros when empty."""
    vals = sorted(v for v in values if v > 0)
    if not vals:
        return 0.0, 0.0, 0.0
    n = len(vals)
    median = statistics.median(vals)
    p25 = vals[max(0, (n - 1) // 4)]
    p75 = vals[min(n - 1, (3 * (n - 1)) // 4)]
    return p25, median, p75


async def fetch_rentcast_comps(
    subject: PropertyRecord,
    radius_miles: float = 5.0,
    months: int = 12,
    *,
    comp_count: int = 12,
    timeout: float = 20.0,
) -> CompAnalysis | None:
    """Nearby finished-unit sale comps from RentCast → ADV per unit.

    Returns a ``CompAnalysis`` with ``adv_source="comps"`` when comps are found,
    or None (no key, missing lat/lng, API error, or no comps) so the caller falls
    back to the labeled regional default.
    """
    if not rentcast_configured() or not subject.lat or not subject.lng:
        return None

    params: dict[str, str | int | float] = {
        "latitude": subject.lat,
        "longitude": subject.lng,
        "propertyType": _DEFAULT_PROPERTY_TYPE,
        "squareFootage": _DEFAULT_UNIT_SQFT,
        "maxRadius": radius_miles,
        "daysOld": months * 31,
        "compCount": comp_count,
    }
    headers = {"X-Api-Key": settings.rentcast_api_key, "Accept": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(_RENTCAST_AVM_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001 — comps are advisory; never fatal
        logger.warning("RentCast comps unavailable: %s", exc)
        return None

    raw = data.get("comparables") or []
    unit_comps: list[ComparableSale] = []
    for c in raw:
        price = float(c.get("price") or 0)
        if price <= 0:
            continue
        unit_comps.append(
            ComparableSale(
                address=str(c.get("formattedAddress") or ""),
                sale_price=round(price, 2),
                sale_date=str(c.get("removedDate") or c.get("lastSeenDate") or ""),
                lot_size_sqft=float(c.get("lotSize") or 0) or 0.0,
                distance_miles=round(float(c.get("distance") or 0), 2),
                price_per_unit=round(price, 2),  # one finished unit per comp
            )
        )

    if not unit_comps:
        return None

    unit_comps.sort(key=lambda x: x.distance_miles)
    low, median, high = _percentiles([c.price_per_unit or 0 for c in unit_comps])

    result = CompAnalysis()
    result.adv_per_unit = round(median, 2)
    result.adv_per_unit_low = round(low, 2)
    result.adv_per_unit_high = round(high, 2)
    result.adv_source = "comps"
    result.unit_comparables = unit_comps[:8]
    # Confidence scales with comp count (RentCast comps are real sales, but
    # condo/townhome resales, not new-construction-specific — medium at best).
    result.confidence = min(0.8, 0.4 + 0.05 * len(unit_comps))
    result.notes = [
        f"Exit value from {len(unit_comps)} RentCast residential sale comps within "
        f"{radius_miles:g} mi (last {months} mo). Market comps for finished units — "
        "not new-construction-specific; treat as a data-grounded estimate."
    ]
    return result
