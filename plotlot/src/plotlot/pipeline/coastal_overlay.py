"""San Diego Coastal Height Limit Overlay (Proposition D) detection.

Proposition D (1972) caps structure height at 30 ft generally west of Interstate
5 in the City of San Diego. This is a *deterministic geographic* constraint — a
parcel is either inside the voter-mapped overlay polygon or it isn't — so it
carries **no LLM / hallucination surface**. Membership is resolved by a
point-in-polygon query against the City's authoritative DSD Zoning_Overlay layer.

The result degrades safely. If the City service is unreachable we return an
``unverified`` determination that the pipeline surfaces as a warning rather than
silently cutting the unit count (fail loud, not silently wrong). Only a
*confirmed* in-overlay result feeds the 30 ft cap into the calculator.

Authoritative source (verified 2026-06):
  City of San Diego DSD Zoning_Overlay/MapServer, Layer 1
  "Coastal Height Limitation Overlay Zone" (polygon; fields ZONENAME, ORDNUM).
"""

from __future__ import annotations

import logging

from plotlot.core.types import CoastalHeightOverlay
from plotlot.observability.tracing import start_span
from plotlot.property.arcgis_utils import spatial_query

logger = logging.getLogger(__name__)

# City of San Diego DSD Zoning Overlay — Layer 1 = Coastal Height Limitation
# Overlay Zone. A point-in-polygon hit means the parcel is inside the Prop D
# 30 ft height zone.
_COASTAL_OVERLAY_URL = (
    "https://webmaps.sandiego.gov/arcgis/rest/services/DSD/Zoning_Overlay/MapServer/1/query"
)

# Prop D height cap, in feet.
PROP_D_HEIGHT_LIMIT_FT = 30.0

_CITATION = (
    "San Diego Municipal Code §132.0505 — Coastal Height Limit Overlay Zone (Proposition D, 1972)"
)
_SOURCE = "City of San Diego DSD Zoning Overlay (Coastal Height Limitation Overlay Zone)"

_CA_ALIASES = {"CA", "CALIFORNIA"}


def is_san_diego_city(city: str, county: str, state: str) -> bool:
    """Prop D is City of San Diego–specific; gate the lookup to that jurisdiction.

    The overlay polygon is itself authoritative (a point outside the City's
    coastal zone simply returns no feature), so this gate is an optimisation that
    avoids pointless calls for parcels that cannot be in the overlay. We attempt
    the lookup whenever the parcel is in California and either the city *or* the
    county resolves to San Diego.
    """
    if (state or "").strip().upper() not in _CA_ALIASES:
        return False
    city_l = (city or "").strip().lower()
    county_l = (county or "").strip().lower().removesuffix(" county").strip()
    return city_l == "san diego" or county_l == "san diego"


async def fetch_coastal_height_overlay(
    lat: float,
    lng: float,
    *,
    city: str = "",
    county: str = "",
    state: str = "",
) -> CoastalHeightOverlay:
    """Resolve San Diego Coastal Height Limit (Prop D) membership for a point.

    Returns a ``CoastalHeightOverlay`` whose ``status`` is one of:
      * ``"in"``           — confirmed inside the overlay → 30 ft cap applies
      * ``"out"``          — confirmed outside the overlay
      * ``"unverified"``   — City service unreachable; caller surfaces a warning
      * ``"not_applicable"`` — parcel is not in the City/County of San Diego, CA
    """
    if not is_san_diego_city(city, county, state):
        return CoastalHeightOverlay(status="not_applicable")

    with start_span(name="coastal_overlay_fetch", span_type="RETRIEVER") as span:
        span.set_inputs({"lat": lat, "lng": lng, "city": city, "county": county})

        try:
            features = await spatial_query(
                _COASTAL_OVERLAY_URL, lat, lng, out_fields="ZONENAME,ORDNUM"
            )
        except Exception as exc:  # noqa: BLE001 — network/parse failure → degrade to unverified
            logger.warning("Coastal Height Overlay lookup unavailable: %s", exc)
            result = CoastalHeightOverlay(
                status="unverified",
                citation=_CITATION,
                source=_SOURCE,
                note=(
                    "City of San Diego overlay service was unreachable — the Prop D 30 ft "
                    "coastal height limit could not be confirmed. If this parcel is west of "
                    "I-5, verify the height limit manually before relying on the unit count."
                ),
            )
            span.set_outputs({"status": result.status})
            return result

        if features:
            attrs = features[0].get("attributes", {}) or {}
            zone_name = (
                str(attrs.get("ZONENAME") or "").strip() or "Coastal Height Limitation Overlay Zone"
            )
            result = CoastalHeightOverlay(
                applies=True,
                height_limit_ft=PROP_D_HEIGHT_LIMIT_FT,
                status="in",
                zone_name=zone_name,
                citation=_CITATION,
                source=_SOURCE,
                note=(
                    f"Parcel is within the {zone_name}: structures are capped at "
                    f"{PROP_D_HEIGHT_LIMIT_FT:g} ft (Proposition D). This limits building "
                    "height — and therefore stories — and can reduce achievable units below "
                    "base zoning."
                ),
            )
        else:
            result = CoastalHeightOverlay(
                status="out",
                citation=_CITATION,
                source=_SOURCE,
                note="Parcel is outside the San Diego Coastal Height Limit Overlay (Prop D).",
            )

        span.set_outputs({"status": result.status, "zone_name": result.zone_name})
        return result
