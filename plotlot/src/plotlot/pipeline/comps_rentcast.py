"""RentCast comparable-sales provider.

A keyed JSON comps API used as the fallback exit-value (ADV-per-unit) source for
markets with no open arms-length-sales GIS layer — California counties (e.g. San
Diego) being the motivating case. Unlike the ArcGIS-layer sources in
``comps_sources``, RentCast returns comps directly, so this returns a fully
formed ``CompAnalysis``.

Used only when the free ArcGIS path (curated registry + Hub discovery) finds
nothing, to conserve the free tier (~50 req/mo). Every call returns a
``RentcastAttempt``: on failure it carries the reason, and the pipeline falls back
to the labeled regional default (honest, not fabricated) while still being able to
say *why* it fell back.

Docs: https://developers.rentcast.io  (GET /avm/value → value + comparables[]).
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass

import httpx

from plotlot.config import settings
from plotlot.core.types import ComparableSale, CompAnalysis, PropertyRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RentcastAttempt:
    """The outcome of a RentCast lookup, including *why* it produced nothing.

    Returning a bare ``None`` conflated four very different situations: no key
    configured, a key whose subscription is dead, a network failure, and a
    perfectly successful call that simply found no comps nearby. Only the first
    and last are benign, but all four looked identical downstream and were
    reported to the user as "no sales dataset found" — which reads as *we have no
    source for this market* when the truth may be *our source is switched off*.

    That distinction is not academic. On 2026-08-10 every San Diego comp silently
    resolved to the $750k regional default because RentCast answered
    ``403 billing/subscription-inactive`` to every request. The log carried the
    reason; nothing the user saw did.
    """

    analysis: CompAnalysis | None = None
    #: Empty when comps were found. Otherwise a user-safe explanation.
    reason: str = ""
    #: True when the provider was reachable and simply had nothing to offer, as
    #: opposed to being unconfigured or refusing us.
    provider_answered: bool = False

    @property
    def ok(self) -> bool:
        return self.analysis is not None


def _http_error_reason(exc: httpx.HTTPStatusError) -> str:
    """Turn a RentCast error response into something worth showing a user.

    RentCast returns a JSON body like ``{"error": "billing/subscription-inactive",
    "message": "..."}``. The status code alone ("403") does not tell an operator
    that the fix is a billing page rather than a code change, so surface the
    provider's own error slug.
    """
    status = exc.response.status_code
    slug = ""
    try:
        body = exc.response.json()
        slug = str(body.get("error") or "").strip()
    except Exception:  # noqa: BLE001 — a non-JSON error body is still an error
        slug = ""
    if slug:
        return f"RentCast refused the request (HTTP {status}: {slug})"
    return f"RentCast refused the request (HTTP {status})"


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
) -> RentcastAttempt:
    """Nearby finished-unit sale comps from RentCast → ADV per unit.

    Always returns a ``RentcastAttempt``. On success it carries a ``CompAnalysis``
    with ``adv_source="comps"``; otherwise it carries the reason, so the caller can
    tell an unconfigured provider from a dead one and say so in the report.
    """
    if not rentcast_configured():
        return RentcastAttempt(reason="RentCast is not configured (no RENTCAST_API_KEY set)")
    if not subject.lat or not subject.lng:
        return RentcastAttempt(reason="subject parcel has no coordinates to search around")

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
    except httpx.HTTPStatusError as exc:
        reason = _http_error_reason(exc)
        logger.warning("RentCast comps unavailable: %s", reason)
        return RentcastAttempt(reason=reason)
    except Exception as exc:  # noqa: BLE001 — comps are advisory; never fatal
        reason = f"RentCast request failed ({type(exc).__name__})"
        logger.warning("RentCast comps unavailable: %s: %s", reason, exc)
        return RentcastAttempt(reason=reason)

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
        # The provider answered; the market simply had nothing. Materially different
        # from a refusal, and the caller reports it differently.
        return RentcastAttempt(
            reason=(
                f"RentCast returned no comparable sales within {radius_miles:g} mi "
                f"in the last {months} months"
            ),
            provider_answered=True,
        )

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
    return RentcastAttempt(analysis=result, provider_answered=True)
