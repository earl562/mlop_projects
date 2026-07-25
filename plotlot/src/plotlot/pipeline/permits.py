"""Development permit data — city permitting system queries.

Currently supports:
- City of San Diego DSDPermits Accela layer (live, unauthenticated ArcGIS REST)

IMPORTANT: Query by APN, NOT by address. The GIS_ADDRESS LIKE query on this
layer returns wrong results (e.g. Torrey Pines data for a Linda Vista query).
Results degrade gracefully on timeout or service unavailability.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from plotlot.core.types import PermitRecord

logger = logging.getLogger(__name__)

_SD_PERMIT_URL = (
    "https://webmaps.sandiego.gov/arcgis/rest/services/DoIT_Public/DSDPermits/MapServer/0/query"
)

_SD_PERMIT_FIELDS = (
    "APPROVAL_PERMIT_HOLDER,APPROVAL_TYPE,APPROVAL_STATUS,"
    "APPROVAL_ISSUE_DATE,PROJECT_TITLE,APPROVAL_URL"
)


async def fetch_sd_permits(
    apn: str,
    *,
    max_results: int = 20,
    timeout: float = 15.0,
) -> list[PermitRecord]:
    """Query the City of San Diego Accela permit system by APN (not address).

    The DSDPermits layer's GIS_APN field is reliable for matching. The
    GIS_ADDRESS LIKE query returns wrong cross-street results and MUST
    NOT be used — this function only queries by APN.

    Returns an empty list on any failure (API unavailable, timeout, no
    matching permits) — never raises.
    """
    where = f"GIS_APN='{apn}'"

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
        logger.warning("SD permit API unavailable for APN %s: %s", apn, exc)
        return []

    features = data.get("features") or []
    results: list[PermitRecord] = []
    for feat in features:
        attrs = feat.get("attributes") or {}
        timestamp = attrs.get("APPROVAL_ISSUE_DATE")
        date_str = ""
        if timestamp and timestamp > 0:
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
    apn: str,
    county: str,
) -> dict:
    """Aggregate development-activity signals for a property.

    Returns permit records, counts, unique holder names, and a
    data-source label. Supported counties: San Diego (via Accela
    DSDPermits). Other counties return empty data gracefully.
    """
    permits: list[PermitRecord] = []
    county_key = county.lower().strip()

    if county_key == "san diego" and apn:
        permits = await fetch_sd_permits(apn)
    else:
        logger.info("Permit query not yet supported for county: %s", county)

    active_states = {"issued", "inspection followup", "opened", "in progress"}
    active = [p for p in permits if p.permit_status.lower().strip() in active_states]
    holders = sorted({p.permit_holder for p in permits if p.permit_holder.strip()})

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
