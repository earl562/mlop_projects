"""ArcGIS Hub dataset discovery — real-time search for parcel/zoning datasets.

Queries the ArcGIS Hub Search API (hub.arcgis.com/api/v3/datasets) to find
parcel and zoning Feature/Map Server endpoints for any US county. No
authentication required — all public datasets.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from plotlot.config import settings
from plotlot.property.models import DatasetInfo

logger = logging.getLogger(__name__)

# Keywords used to score dataset relevance
_PARCEL_FIELD_KEYWORDS = {
    "FOLIO",
    "PARCEL",
    "PID",
    "APN",
    "PIN",
    "LOT_SIZE",
    "ACRES",
    "OWNER",
    "SITE_ADDR",
    "ADDRESS",
    "SITUS",
    "YEAR_BUILT",
    "ASSESSED",
}
_ZONING_FIELD_KEYWORDS = {
    "ZONE",
    "ZONING",
    "ZONE_CODE",
    "DISTRICT",
    "ZONE_CLASS",
    "ZONING_CODE",
}
_PARCEL_NAME_KEYWORDS = {"parcel", "property", "appraiser", "tax", "cadastral"}
_ZONING_NAME_KEYWORDS = {"zoning", "zone", "land use", "landuse", "planning"}

# Sub-area indicators: district/neighborhood datasets cover only a small slice
# of the county and will fail spatial queries for addresses outside that area.
_SUB_AREA_PENALTY_KEYWORDS = {
    "cra",
    "redevelopment",
    "community redevelopment",
    "downtown",
    "district",
    "corridor",
    "neighborhood",
    "nra",  # neighborhood redevelopment area
    "tif",  # tax increment financing zone
    "enterprise zone",
}


async def discover_datasets(
    lat: float,
    lng: float,
    county: str,
    state: str,
) -> tuple[DatasetInfo | None, DatasetInfo | None]:
    """Discover parcel + zoning datasets for a county via ArcGIS Hub.

    Args:
        lat: Latitude of the target location.
        lng: Longitude of the target location.
        county: County name (e.g., "Harris").
        state: State name or abbreviation (e.g., "Texas" or "TX").

    Returns:
        Tuple of (parcels_dataset, zoning_dataset). Either may be None.
    """
    parcels = await _search_hub(lat, lng, county, state, dataset_type="parcels")
    zoning = await _search_hub(lat, lng, county, state, dataset_type="zoning")
    return parcels, zoning


async def _search_hub(
    lat: float,
    lng: float,
    county: str,
    state: str,
    dataset_type: str,
) -> DatasetInfo | None:
    """Search Hub for a specific dataset type and return the best match."""
    search_term = f"{dataset_type} {county} {state}"

    # Hub v3 API does not support filter[bbox]. Use filter[tags] for relevance
    # and rely on the search query + dataset scoring for spatial matching.
    tags = (
        "any(parcels,parcel,property,appraiser,cadastral)"
        if dataset_type == "parcels"
        else "any(zoning,zone,land-use,planning)"
    )

    params = {
        "q": search_term,
        "filter[type]": "Feature Service",
        "filter[tags]": tags,
        "page[size]": "10",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.hub_discovery_timeout) as client:
            resp = await client.get(settings.arcgis_hub_api_url, params=params)
            resp.raise_for_status()
            hub_data = resp.json()
    except httpx.HTTPError:
        logger.warning("Hub search failed for '%s'", search_term, exc_info=True)
        return None

    candidates = hub_data.get("data", [])
    if not candidates:
        logger.info("Hub returned no datasets for '%s'", search_term)
        return None

    # Score all candidates, then validate coverage in score order
    scored: list[tuple[float, DatasetInfo]] = []

    for item in candidates:
        attrs = item.get("attributes", {})
        dataset_url = attrs.get("url", "")
        dataset_name = attrs.get("name", "")
        dataset_id = item.get("id", "")

        if not dataset_url:
            continue

        # Fetch layer metadata to get field names
        fields, layer_id = await _fetch_layer_fields(dataset_url)
        if not fields:
            continue

        score = _score_dataset(fields, dataset_name, dataset_type, dataset_url)
        candidate = DatasetInfo(
            dataset_id=dataset_id,
            name=dataset_name,
            url=dataset_url,
            layer_id=layer_id,
            dataset_type=dataset_type,
            county=county,
            state=state,
            fields=fields,
            discovered_at=datetime.now(timezone.utc),
        )
        scored.append((score, candidate))

    # Sort highest score first, then validate each candidate has data at the target location
    scored.sort(key=lambda t: t[0], reverse=True)
    for score, candidate in scored:
        if await _has_coverage(candidate, lat, lng):
            logger.info(
                "Discovered %s dataset for %s, %s: %s (score=%.2f)",
                dataset_type,
                county,
                state,
                candidate.name,
                score,
            )
            return candidate
        logger.debug(
            "Skipping %s '%s' — no spatial results at (%.4f, %.4f)",
            dataset_type,
            candidate.name,
            lat,
            lng,
        )

    if scored:
        fallback = scored[0][1]
        logger.warning(
            "No %s dataset passed coverage validation for %s, %s; using top-scored fallback %s",
            dataset_type,
            county,
            state,
            fallback.name,
        )
        return fallback

    logger.info("No suitable %s dataset found for %s, %s", dataset_type, county, state)
    return None


async def _has_coverage(dataset: DatasetInfo, lat: float, lng: float) -> bool:
    """Return True if the dataset has at least one feature at the given coordinates.

    Used to filter out datasets that match keyword scoring but cover a different
    geographic area (e.g., another county or a sub-area like a CRA district).
    """
    from plotlot.property.arcgis_utils import spatial_query

    query_url = f"{dataset.url}/{dataset.layer_id}/query"
    try:
        features = await spatial_query(query_url, lat, lng)
        return bool(features)
    except Exception:
        logger.debug("Coverage check failed for %s", dataset.name, exc_info=True)
        return False


async def _fetch_layer_fields(base_url: str) -> tuple[list[str], int]:
    """Fetch field names from an ArcGIS service URL.

    Tries the service root first (?f=json) to find layers, then queries
    the first Feature layer for its field schema.

    Returns (field_names, layer_id).
    """
    # Normalize URL — strip trailing slash and /query suffix
    url = base_url.rstrip("/")
    if url.endswith("/query"):
        url = url.rsplit("/query", 1)[0]

    # Check if URL already points to a specific layer (ends with /digit)
    parts = url.rsplit("/", 1)
    if parts[-1].isdigit():
        layer_url = url
        layer_id = int(parts[-1])
    else:
        # Discover layers from service root
        layer_id = await _find_best_layer(url)
        layer_url = f"{url}/{layer_id}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(layer_url, params={"f": "json"})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        logger.debug("Failed to fetch layer metadata: %s", layer_url)
        return [], 0

    fields = [f.get("name", "") for f in data.get("fields", [])]
    return fields, layer_id


async def _find_best_layer(service_url: str) -> int:
    """Find the best layer ID in an ArcGIS service."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(service_url, params={"f": "json"})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        return 0

    layers = data.get("layers", [])
    if not layers:
        return 0

    # Prefer Feature layers (type="Feature Layer") over others
    for layer in layers:
        if layer.get("type") == "Feature Layer":
            return int(layer.get("id", 0))

    return int(layers[0].get("id", 0))


def _score_dataset(
    fields: list[str],
    name: str,
    dataset_type: str,
    url: str = "",
) -> float:
    """Score how well a dataset matches expected parcel/zoning fields.

    Scoring priorities (highest to lowest):
    1. Sub-area penalty: CRA/redevelopment/district datasets cover only a slice
       of the county — heavy penalty so they lose to county-wide datasets.
    2. Official gov domain bonus: .gov URLs are typically the authoritative source.
    3. Field keyword overlap: how many expected field names are present.
    4. Dataset name keywords: "parcel", "appraiser", etc.
    """
    score = 0.0
    upper_fields = {f.upper() for f in fields}
    name_lower = name.lower()

    # Sub-area penalty — any hit disqualifies the dataset vs. county-wide ones.
    # Avoid penalizing legitimate zoning datasets named "Zoning Districts".
    for kw in _SUB_AREA_PENALTY_KEYWORDS:
        if kw == "district" and "zoning district" in name_lower:
            continue
        if kw in name_lower:
            score -= 5.0
            break  # one penalty is enough

    # Official government domain bonus (e.g. miamidade.gov, broward.org)
    if ".gov" in url or ".org" in url:
        score += 3.0

    if dataset_type == "parcels":
        # Field name overlap with parcel keywords
        for kw in _PARCEL_FIELD_KEYWORDS:
            if any(kw in f for f in upper_fields):
                score += 1.0
        # Dataset name keywords
        for kw in _PARCEL_NAME_KEYWORDS:
            if kw in name_lower:
                score += 2.0
    else:
        for kw in _ZONING_FIELD_KEYWORDS:
            if any(kw in f for f in upper_fields):
                score += 1.5
        for kw in _ZONING_NAME_KEYWORDS:
            if kw in name_lower:
                score += 2.0

    return score
