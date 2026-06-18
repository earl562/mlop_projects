"""Development permit data — city permitting system queries.

Currently supports:
- City of San Diego DSDPermits Accela layer (live, unauthenticated ArcGIS REST)

Results degrade gracefully on timeout or service unavailability.
"""

from __future__ import annotations

import logging

import httpx

from plotlot.core.types import PermitRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# City of San Diego — DSDPermits Accela layer (current cloud-based system)
# ---------------------------------------------------------------------------

_SD_PERMIT_URL = (
    "https://webmaps.sandiego.gov/arcgis/rest/services"
    "/DoIT_Public/DSDPermits/MapServer/0/query"
)

_SD_PERMIT_FIELDS = (
    "APPROVAL_PERMIT_HOLDER,APPROVAL_TYPE,APPROVAL_STATUS,"
    "APPROVAL_ISSUE_DATE,PROJECT_TITLE,APPROVAL_URL"
)


async def fetch_sd_permits(
    address: str,
    *,
    max_results: int = 20,
    timeout: float = 15.0,
) -> list[PermitRecord]:
    """Query the City of San Diego Accela permit system for a given address.

    Returns up to *max_results* PermitRecords, sorted by most recent issue date.
    Returns empty list on any error (graceful degradation).
    """
    normalized = address.strip().upper()
    # Match on street address — the Accela layer stores addresses in GIS_ADDRESS
    where = f"UPPER(GIS_ADDRESS) LIKE '%{normalized}%'"

    params = {
        "where": where,
        "outFields": _SD_PERMIT_FIELDS,
        "returnGeometry": "false",
        "f": "json",
        "resultRecordCount": str(max_results),
        "orderByFields": "APPROVAL_ISSUE_DATE DESC",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(_SD_PERMIT_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("SD permit API unavailable for %s: %s", address, exc)
        return []

    features = data.get("features") or []
    results: list[PermitRecord] = []
    for feat in features:
        attrs = feat.get("attributes") or {}
        timestamp = attrs.get("APPROVAL_ISSUE_DATE")
        date_str = ""
        if timestamp and timestamp > 0:
            from datetime import datetime, timezone

            date_str = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).strftime(
                "%Y-%m-%d"
            )

        results.append(
            PermitRecord(
                permit_holder=str(attrs.get("APPROVAL_PERMIT_HOLDER") or ""),
                permit_type=str(attrs.get("APPROVAL_TYPE") or ""),
                permit_status=str(attrs.get("APPROVAL_STATUS") or ""),
                issue_date=date_str,
                project_title=str(attrs.get("PROJECT_TITLE") or ""),
                approval_url=str(attrs.get("APPROVAL_URL") or ""),
            )
        )

    return results


async def fetch_development_signals(
    address: str,
    county: str,
) -> dict:
    """Fetch development-activity signals for a property: permits + ownership context.

    Returns a dict with:
      - permits: list[PermitRecord]
      - permit_count: int
      - active_permit_count: int
      - unique_permit_holders: list[str]
      - data_source: str

    Currently supports San Diego only (county == 'san diego').
    """
    permits: list[PermitRecord] = []
    county_key = county.lower().strip()

    if county_key == "san diego":
        permits = await fetch_sd_permits(address)
    else:
        logger.info("Permit query not yet supported for county: %s", county)

    active_states = {"issued", "inspection followup", "opened", "in progress"}
    active = [p for p in permits if p.permit_status.lower().strip() in active_states]
    holders = sorted(
        {p.permit_holder for p in permits if p.permit_holder.strip()}
    )

    return {
        "permits": permits,
        "permit_count": len(permits),
        "active_permit_count": len(active),
        "unique_permit_holders": holders,
        "data_source": (
            "City of San Diego DSDPermits (Accela)"
            if county_key == "san diego"
            else "not available"
        ),
    }
