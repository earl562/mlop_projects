"""Site risk assessment - FEMA flood zone, NWI wetland data, and CGS geologic hazards.

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
# CGS geologic hazard fetch
# ---------------------------------------------------------------------------

# CA statewide parcel layer carries FaultZone, LandslideZone, LiquefactionZone
# fields with CGS coded-value legends (all 58 counties).
_CGS_PARCEL_URL = (
    "https://services2.arcgis.com/zr3KAIbsRSUyARHG/arcgis/rest/services"
    "/CA_State_Parcels/FeatureServer/0/query"
)

# CGS domain label maps (from CA_State_Parcels layer field domain annotations)
_CGS_FAULT_LABELS = {1: "Not within an earthquake fault zone", 2: "Within an earthquake fault zone"}
_CGS_LANDSLIDE_LABELS = {
    1: "Within a landslide zone",
    2: "Not within a landslide zone",
    3: "Partial evaluation by CGS",
    4: "Not evaluated by CGS for landslide hazards",
}
_CGS_LIQUEFACTION_LABELS = {
    1: "Within a liquefaction zone",
    2: "Not within a liquefaction zone",
    3: "Partial evaluation by CGS",
    4: "Not evaluated by CGS for liquefaction hazards",
}


def _cgs_code_label(code: int, labels: dict[int, str]) -> str:
    """Look up a CGS coded-value; return the label or 'Unknown code {n}'."""
    return labels.get(code, f"Unknown code {code}")


async def _fetch_cgs_hazards(lat: float, lng: float, timeout: float = 10.0) -> GeologicHazard | None:
    """Query the CA statewide parcel layer for CGS geologic/seismic hazard fields.

    Returns a GeologicHazard with human-readable status strings, or None
    if the query fails or returns no parcel.
    """
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "FaultZone,LandslideZone,LiquefactionZone",
        "returnGeometry": "false",
        "f": "json",
        "resultRecordCount": "1",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(_CGS_PARCEL_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("CGS hazard API unavailable: %s", exc)
        return None

    features = data.get("features") or []
    if not features:
        return None

    attrs = features[0].get("attributes") or {}
    fault = attrs.get("FaultZone")
    landslide = attrs.get("LandslideZone")
    liquefaction = attrs.get("LiquefactionZone")

    return GeologicHazard(
        fault_zone_status=_cgs_code_label(fault, _CGS_FAULT_LABELS) if fault else "",
        landslide_status=_cgs_code_label(landslide, _CGS_LANDSLIDE_LABELS) if landslide else "",
        liquefaction_status=_cgs_code_label(liquefaction, _CGS_LIQUEFACTION_LABELS) if liquefaction else "",
        source="CA_State_Parcels CGS fields",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_site_risk(lat: float, lng: float) -> SiteRisk:
    """Fetch FEMA flood zone and NWI wetland data for a location.

    Both calls are made concurrently and degrade gracefully on failure.
    Total timeout budget: 12s (both APIs have 10s individual timeouts).
    """
    import asyncio

    with start_span(name="site_risk_fetch", span_type="RETRIEVER") as span:
        span.set_inputs({"lat": lat, "lng": lng})

        flood_task = asyncio.create_task(_fetch_fema_flood_zone(lat, lng))
        wetland_task = asyncio.create_task(_fetch_nwi_wetlands(lat, lng))
        cgs_task = asyncio.create_task(_fetch_cgs_hazards(lat, lng))

        flood_zone, wetlands, cgs_hazard = await asyncio.gather(flood_task, wetland_task, cgs_task)

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
        if cgs_hazard:
            if cgs_hazard.fault_zone_status and "within" in cgs_hazard.fault_zone_status.lower():
                risk_flags.append(f"Earthquake fault zone: {cgs_hazard.fault_zone_status}")
            elif cgs_hazard.fault_zone_status and "not evaluated" not in cgs_hazard.fault_zone_status.lower():
                risk_flags.append(f"Earthquake fault: {cgs_hazard.fault_zone_status}")
            if cgs_hazard.landslide_status and "within" in cgs_hazard.landslide_status.lower():
                risk_flags.append(f"Landslide zone: {cgs_hazard.landslide_status}")
            elif cgs_hazard.landslide_status and "not evaluated" not in cgs_hazard.landslide_status.lower():
                risk_flags.append(f"Landslide: {cgs_hazard.landslide_status}")
            if cgs_hazard.liquefaction_status and "within" in cgs_hazard.liquefaction_status.lower():
                risk_flags.append(f"Liquefaction zone: {cgs_hazard.liquefaction_status}")
            elif cgs_hazard.liquefaction_status and "not evaluated" not in cgs_hazard.liquefaction_status.lower():
                risk_flags.append(f"Liquefaction: {cgs_hazard.liquefaction_status}")

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

        data_sources = []
        if flood_zone is not None:
            data_sources.append("FEMA National Flood Hazard Layer (NFHL)")
        data_sources.append("USFWS National Wetlands Inventory (NWI)")
        if cgs_hazard is not None:
            data_sources.append("CA_State_Parcels CGS geologic hazard fields")

        result = SiteRisk(
            flood_zone=flood_zone,
            wetlands=wetlands,
            has_wetlands=bool(wetlands),
            geologic_hazard=cgs_hazard,
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
