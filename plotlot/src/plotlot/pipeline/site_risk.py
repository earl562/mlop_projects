"""Site risk assessment — FEMA flood zone and NWI wetland data.

Pulls from two free federal APIs using only lat/lng:
- FEMA NFHL (National Flood Hazard Layer) — flood zone designation
- USFWS NWI (National Wetlands Inventory) — wetland presence and type

Both APIs are ArcGIS REST services with no authentication required.
Results degrade gracefully on timeout or service unavailability.
"""

from __future__ import annotations

import logging

import httpx

from plotlot.core.types import FloodZoneInfo, GeologicHazard, SiteRisk, WetlandInfo
from plotlot.observability.tracing import start_span

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FEMA NFHL — Layer 28 = Flood Hazard Zones (S_Fld_Haz_Ar)
# ---------------------------------------------------------------------------

_FEMA_URL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"

_FLOOD_RISK_LEVELS: dict[str, str] = {
    # Special Flood Hazard Areas (1% annual chance) — HIGH
    "A": "high",
    "AE": "high",
    "AH": "high",
    "AO": "high",
    "AR": "high",
    "A99": "high",
    # Coastal high hazard — HIGH
    "V": "high",
    "VE": "high",
    # 500-year flood zone — MODERATE
    "X500": "moderate",
    # Minimal / undetermined
    "X": "minimal",
    "D": "undetermined",
}

_FLOOD_DESCRIPTIONS: dict[str, str] = {
    "A": "Special Flood Hazard Area — 1% annual chance flood (no base flood elevation determined)",
    "AE": "Special Flood Hazard Area — 1% annual chance flood with base flood elevation",
    "AH": "Special Flood Hazard Area — shallow flooding (ponding), 1% annual chance",
    "AO": "Special Flood Hazard Area — sheet flow flooding, 1% annual chance",
    "AR": "Special Flood Hazard Area — temporarily protected by federal flood control system",
    "A99": "Special Flood Hazard Area — protected by federal levee under construction",
    "V": "Coastal High Hazard Area — 1% annual chance coastal flood with wave action",
    "VE": "Coastal High Hazard Area — 1% annual chance coastal flood with base flood elevation",
    "X": "Minimal flood hazard — outside 500-year flood plain",
    "X500": "Moderate flood hazard — within 500-year flood plain",
    "D": "Flood hazard undetermined — no FEMA study available",
}


# ---------------------------------------------------------------------------
# FEMA fetch
# ---------------------------------------------------------------------------


async def _fetch_fema_flood_zone(
    lat: float, lng: float, timeout: float = 10.0
) -> FloodZoneInfo | None:
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF",
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(_FEMA_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("FEMA API unavailable: %s", exc)
        return None

    features = data.get("features") or []
    if not features:
        # No FEMA record = outside any mapped flood zone → minimal risk
        return FloodZoneInfo(
            zone="X",
            zone_subtype="",
            in_sfha=False,
            risk_level="minimal",
            description=_FLOOD_DESCRIPTIONS["X"],
        )

    attrs = features[0].get("attributes") or {}
    zone = (attrs.get("FLD_ZONE") or "X").strip().upper()
    subty = (attrs.get("ZONE_SUBTY") or "").strip()
    sfha_tf = str(attrs.get("SFHA_TF") or "").strip().upper()

    # ZONE_SUBTY "0.2 PCT ANNUAL CHANCE FLOOD HAZARD" → treat as X500
    zone_key = zone
    if zone == "X" and "0.2" in subty:
        zone_key = "X500"

    risk_level = _FLOOD_RISK_LEVELS.get(zone_key, "undetermined")
    description = _FLOOD_DESCRIPTIONS.get(zone_key, f"Flood zone {zone}")
    in_sfha = sfha_tf == "T" or risk_level == "high"

    return FloodZoneInfo(
        zone=zone,
        zone_subtype=subty,
        in_sfha=in_sfha,
        risk_level=risk_level,
        description=description,
    )


# ---------------------------------------------------------------------------
# NWI fetch
# ---------------------------------------------------------------------------

_NWI_URL = "https://www.fws.gov/wetlands/arcgis/rest/services/Wetlands/MapServer/0/query"

# Small buffer around the point (in decimal degrees ≈ 100m) to catch adjacent wetlands
_NWI_BUFFER_DEG = 0.001


async def _fetch_nwi_wetlands(lat: float, lng: float, timeout: float = 10.0) -> list[WetlandInfo]:
    # Envelope query: bounding box around point
    xmin = lng - _NWI_BUFFER_DEG
    ymin = lat - _NWI_BUFFER_DEG
    xmax = lng + _NWI_BUFFER_DEG
    ymax = lat + _NWI_BUFFER_DEG

    params = {
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "WETLAND_TYPE,ACRES",
        "returnGeometry": "false",
        "f": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(_NWI_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("NWI API unavailable: %s", exc)
        return []

    wetlands = []
    for feature in data.get("features") or []:
        attrs = feature.get("attributes") or {}
        wetland_type = (attrs.get("WETLAND_TYPE") or "").strip()
        acres = float(attrs.get("ACRES") or 0)
        if wetland_type:
            wetlands.append(WetlandInfo(wetland_type=wetland_type, acres=acres))

    return wetlands


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CGS geologic / seismic hazard (California statewide parcel layer)
#
# The CA statewide parcel layer carries CGS Seismic Hazard Zone fields with
# authoritative coded-value legends. Codes 3/4 mean "not evaluated by CGS" — an
# honest unknown that must NOT be reported as "no hazard"/"low risk" (that was a
# narrator hallucination: "mild slope, low risk"). Outside California the query
# returns nothing, so geologic hazard is simply absent (graceful).
# ---------------------------------------------------------------------------

_GEOLOGIC_URL = (
    "https://services2.arcgis.com/zr3KAIbsRSUyARHG/arcgis/rest/services"
    "/CA_State_Parcels/FeatureServer/0/query"
)

# code → (legend, in_zone, evaluated)
_FAULT_DOMAIN: dict[int, tuple[str, bool, bool]] = {
    1: ("not within an Alquist-Priolo Earthquake Fault Zone", False, True),
    2: ("within an Alquist-Priolo Earthquake Fault Zone", True, True),
}
_LANDSLIDE_DOMAIN: dict[int, tuple[str, bool, bool]] = {
    1: ("within a CGS seismic landslide zone", True, True),
    2: ("not within a CGS seismic landslide zone", False, True),
    3: ("not fully evaluated by CGS for seismic landslide hazards", False, False),
    4: ("NOT evaluated by CGS for seismic landslide hazards", False, False),
}
_LIQUEFACTION_DOMAIN: dict[int, tuple[str, bool, bool]] = {
    1: ("within a CGS liquefaction zone", True, True),
    2: ("not within a CGS liquefaction zone", False, True),
    3: ("not fully evaluated by CGS for liquefaction hazards", False, False),
    4: ("NOT evaluated by CGS for liquefaction hazards", False, False),
}


async def _fetch_geologic_hazard(
    lat: float, lng: float, timeout: float = 10.0
) -> GeologicHazard | None:
    """CGS fault / landslide / liquefaction zones from the CA statewide layer.

    Returns ``None`` outside California (no parcel) or on any failure — geologic
    hazard is simply absent rather than guessed.
    """
    from plotlot.property.arcgis_utils import spatial_query

    try:
        features = await spatial_query(
            _GEOLOGIC_URL,  # already ends in /query, as spatial_query expects
            lat,
            lng,
            out_fields="FaultZone,LandslideZone,LiquefactionZone",
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001 — advisory, never fatal
        logger.warning("CGS geologic hazard API unavailable: %s", exc)
        return None

    if not features:
        return None
    attrs = features[0].get("attributes", {})

    def _resolve(code: object, domain: dict[int, tuple[str, bool, bool]]) -> tuple[str, bool, bool]:
        if not isinstance(code, (int, float)):
            return ("", False, True)
        return domain.get(int(code), ("", False, True))

    fault_txt, fault_in, _ = _resolve(attrs.get("FaultZone"), _FAULT_DOMAIN)
    ls_txt, ls_in, ls_eval = _resolve(attrs.get("LandslideZone"), _LANDSLIDE_DOMAIN)
    lq_txt, lq_in, lq_eval = _resolve(attrs.get("LiquefactionZone"), _LIQUEFACTION_DOMAIN)

    flags: list[str] = []
    if fault_in:
        flags.append("Earthquake Fault Zone — fault-rupture study required before building")
    if ls_in:
        flags.append("Seismic landslide zone — geotechnical landslide study required")
    if lq_in:
        flags.append("Liquefaction zone — geotechnical liquefaction study required")
    if not (ls_eval and lq_eval):
        flags.append(
            "Seismic landslide/liquefaction NOT evaluated by CGS here — a site-specific "
            "geotechnical review is needed (this is an unmapped unknown, not a clearance)"
        )

    return GeologicHazard(
        fault_zone=fault_txt,
        landslide_zone=ls_txt,
        liquefaction_zone=lq_txt,
        in_any_hazard_zone=fault_in or ls_in or lq_in,
        evaluated=ls_eval and lq_eval,
        flags=flags,
    )


# ---------------------------------------------------------------------------
# City of San Diego Airport Influence Areas (DSD overlay)
#
# A live City ArcGIS layer — a parcel in an Airport Influence Area carries
# disclosure / height-notification / safety review requirements (CA Airport Land
# Use Compatibility). SD-only; the point simply misses elsewhere (graceful).
# ---------------------------------------------------------------------------

_AIRPORT_URL = "https://webmaps.sandiego.gov/arcgis/rest/services/DSD/Airports/MapServer/1/query"


async def _fetch_airport_influence(lat: float, lng: float, timeout: float = 10.0) -> list[str]:
    """Airport Influence Areas (City of San Diego) intersecting the point."""
    from plotlot.property.arcgis_utils import spatial_query

    try:
        features = await spatial_query(
            _AIRPORT_URL, lat, lng, out_fields="Airport,Label,FEATURE_DE", timeout=timeout
        )
    except Exception as exc:  # noqa: BLE001 — advisory, never fatal
        logger.warning("SD Airport Influence API unavailable: %s", exc)
        return []

    seen: list[str] = []
    for feat in features:
        attrs = feat.get("attributes", {})
        airport = str(attrs.get("Airport") or "").strip()
        label = str(attrs.get("Label") or attrs.get("FEATURE_DE") or "").strip()
        if not (airport or label):
            continue
        text = f"{airport} — {label}" if airport and label else (airport or label)
        if text not in seen:
            seen.append(text)
    return seen


async def fetch_site_risk(lat: float, lng: float) -> SiteRisk:
    """Fetch FEMA flood, NWI wetland, and CGS geologic-hazard data for a location.

    All calls are made concurrently and degrade gracefully on failure.
    """
    import asyncio

    with start_span(name="site_risk_fetch", span_type="RETRIEVER") as span:
        span.set_inputs({"lat": lat, "lng": lng})

        flood_task = asyncio.create_task(_fetch_fema_flood_zone(lat, lng))
        wetland_task = asyncio.create_task(_fetch_nwi_wetlands(lat, lng))
        geologic_task = asyncio.create_task(_fetch_geologic_hazard(lat, lng))
        airport_task = asyncio.create_task(_fetch_airport_influence(lat, lng))

        flood_zone, wetlands, geologic, airport_influence = await asyncio.gather(
            flood_task, wetland_task, geologic_task, airport_task
        )

        # Build risk flags
        risk_flags: list[str] = []
        if flood_zone and flood_zone.in_sfha:
            risk_flags.append(
                f"SFHA flood zone {flood_zone.zone} — flood insurance required for federally-backed mortgages"
            )
        if flood_zone and flood_zone.risk_level == "moderate":
            risk_flags.append(f"500-year flood zone {flood_zone.zone} — moderate flood risk")
        if wetlands:
            total_acres = sum(w.acres for w in wetlands)
            types = ", ".join({w.wetland_type for w in wetlands})
            risk_flags.append(
                f"Wetlands present within ~100m: {types} ({total_acres:.2f} acres) — may require Section 404 permit"
            )
        if geologic:
            risk_flags.extend(geologic.flags)
        if airport_influence:
            risk_flags.append(
                "In an Airport Influence Area ("
                + "; ".join(airport_influence)
                + ") — disclosure and FAA/airport height-notification review may apply"
            )

        # Overall risk
        flood_risk = flood_zone.risk_level if flood_zone else "unknown"
        if flood_risk == "high" or (wetlands and flood_risk in ("high", "moderate")):
            overall_risk = "high"
        elif flood_risk == "moderate" or wetlands:
            overall_risk = "moderate"
        elif flood_risk == "minimal":
            overall_risk = "low"
        else:
            overall_risk = "unknown"

        # A mapped fault/landslide/liquefaction zone raises overall risk; an
        # unevaluated parcel is an honest unknown, not a clearance.
        if geologic and geologic.in_any_hazard_zone and overall_risk in ("low", "unknown"):
            overall_risk = "moderate"

        data_sources = []
        if flood_zone is not None:
            data_sources.append("FEMA National Flood Hazard Layer (NFHL)")
        data_sources.append("USFWS National Wetlands Inventory (NWI)")
        if geologic is not None:
            data_sources.append("California Geological Survey (CGS) Seismic Hazard Zones")
        if airport_influence:
            data_sources.append("City of San Diego Airport Influence Areas (DSD)")

        result = SiteRisk(
            flood_zone=flood_zone,
            wetlands=wetlands,
            has_wetlands=bool(wetlands),
            geologic=geologic,
            airport_influence=airport_influence,
            overall_risk=overall_risk,
            risk_flags=risk_flags,
            data_sources=data_sources,
        )

        span.set_outputs(
            {
                "flood_zone": flood_zone.zone if flood_zone else None,
                "flood_risk": flood_risk,
                "wetland_count": len(wetlands),
                "overall_risk": overall_risk,
            }
        )
        return result
