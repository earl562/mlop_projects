"""ArcGIS Hub dataset discovery — real-time search for parcel/zoning datasets.

Queries the ArcGIS Hub Search API (hub.arcgis.com/api/v3/datasets) to find
parcel and zoning Feature/Map Server endpoints for any US county. No
authentication required — all public datasets.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from plotlot.config import settings
from plotlot.property.models import DatasetInfo

logger = logging.getLogger(__name__)

# Map 2-letter state abbreviations → full lowercase names for Hub metadata matching.
# Dataset metadata typically contains "Nevada" or "Clark County, Nevada", not "NV".
_STATE_FULL_NAMES: dict[str, str] = {
    "al": "alabama",
    "ak": "alaska",
    "az": "arizona",
    "ar": "arkansas",
    "ca": "california",
    "co": "colorado",
    "ct": "connecticut",
    "de": "delaware",
    "fl": "florida",
    "ga": "georgia",
    "hi": "hawaii",
    "id": "idaho",
    "il": "illinois",
    "in": "indiana",
    "ia": "iowa",
    "ks": "kansas",
    "ky": "kentucky",
    "la": "louisiana",
    "me": "maine",
    "md": "maryland",
    "ma": "massachusetts",
    "mi": "michigan",
    "mn": "minnesota",
    "ms": "mississippi",
    "mo": "missouri",
    "mt": "montana",
    "ne": "nebraska",
    "nv": "nevada",
    "nh": "new hampshire",
    "nj": "new jersey",
    "nm": "new mexico",
    "ny": "new york",
    "nc": "north carolina",
    "nd": "north dakota",
    "oh": "ohio",
    "ok": "oklahoma",
    "or": "oregon",
    "pa": "pennsylvania",
    "ri": "rhode island",
    "sc": "south carolina",
    "sd": "south dakota",
    "tn": "tennessee",
    "tx": "texas",
    "ut": "utah",
    "vt": "vermont",
    "va": "virginia",
    "wa": "washington",
    "wv": "west virginia",
    "wi": "wisconsin",
    "wy": "wyoming",
    "dc": "district of columbia",
}


def _expand_state(state: str) -> str:
    """Return the full state name for a 2-letter abbreviation, or the original."""
    return _STATE_FULL_NAMES.get(state.lower().strip(), state.lower().strip())


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

# ---------------------------------------------------------------------------
# Option 2 — State-level ArcGIS REST servers
#
# These are authoritative state/regional ArcGIS servers that host comprehensive
# county parcel data.  They are NOT on ArcGIS Hub so the Hub search won't find
# them.  The server URL is the root of the REST services tree (no trailing /).
# Only add entries that have been live-tested and confirmed to contain parcel
# data.  Keep the list small and accurate rather than large and flaky.
# ---------------------------------------------------------------------------
_STATE_SERVERS: dict[str, list[str]] = {
    "nc": ["https://services.nconemap.gov/secure/rest/services"],  # NC1Map statewide parcels
    "fl": ["https://ca.dep.state.fl.us/arcgis/rest/services"],  # FL DEP (county parcels)
    "wa": ["https://gismaps.kingcounty.gov/arcgis/rest/services"],  # King County WA
    "pa": ["https://gis.penndot.gov/arcgis/rest/services"],  # PA DOT
}

# Service-folder keywords that suggest parcel or zoning data.
# Used when crawling an ArcGIS server tree to skip irrelevant folders.
_RELEVANT_FOLDER_KEYWORDS = {
    "parcel",
    "property",
    "assessor",
    "appraisal",
    "cadastral",
    "zoning",
    "planning",
    "landuse",
    "land_use",
    "land use",
}

# ---------------------------------------------------------------------------
# Option 3 — County ArcGIS server URL pattern templates
#
# {county} = lowercase county name slug (spaces removed, e.g. "losangeles")
# {state}  = lowercase 2-letter state abbreviation (e.g. "ca")
#
# Patterns are tried in order; first one that returns a valid ArcGIS response
# wins.  Derived from live survey of major-metro county GIS portals.
# ---------------------------------------------------------------------------
_COUNTY_URL_PATTERNS: list[str] = [
    # county+state in subdomain  (Clark County NV → clarkcountynv.gov)
    "https://gis.{county}county{state}.gov/arcgis/rest/services",
    "https://maps.{county}county{state}.gov/arcgis/rest/services",
    # county only in subdomain
    "https://gis.{county}county.gov/arcgis/rest/services",
    "https://maps.{county}county.gov/arcgis/rest/services",
    "https://gismaps.{county}county.gov/arcgis/rest/services",  # King County WA
    "https://arcgis.{county}county.gov/arcgis/rest/services",
    # bare county name  (Maricopa AZ → gis.maricopa.gov)
    "https://gis.{county}.gov/arcgis/rest/services",
    "https://maps.{county}.gov/arcgis/rest/services",
    "https://gis.{county}{state}.gov/arcgis/rest/services",  # variant
    # co.county.state.us  (common midwest/rural pattern)
    "https://gis.co.{county}.{state}.us/arcgis/rest/services",
    "https://maps.co.{county}.{state}.us/arcgis/rest/services",
    # .net TLD (some counties)
    "https://gis.{county}county.net/arcgis/rest/services",
    "https://gis.{county}.net/arcgis/rest/services",
    # ArcGIS Online org  (county self-hosted on AGOL)
    "https://{county}county.maps.arcgis.com/arcgis/rest/services",
    "https://{county}{state}.maps.arcgis.com/arcgis/rest/services",
    # county.gov at root  (no gis. prefix)
    "https://{county}county.gov/arcgis/rest/services",
]

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
    *,
    validate_coverage: bool = True,
    place_hint: str | None = None,
) -> tuple[DatasetInfo | None, DatasetInfo | None]:
    """Discover parcel + zoning datasets for a county.

    Discovery cascade (stops at the first source that returns a result):
      1. ArcGIS Hub   — public global index (covers most well-published counties)
      2. State servers — authoritative state-level ArcGIS REST servers (Option 2)
      3. URL patterns  — probes common county GIS server URL templates (Option 3)

    Args:
        lat: Latitude of the target location.
        lng: Longitude of the target location.
        county: County name (e.g., "Harris").
        state: State name or abbreviation (e.g., "Texas" or "TX").

    Returns:
        Tuple of (parcels_dataset, zoning_dataset). Either may be None.
    """
    parcels, zoning = await _discover_pair(
        lat,
        lng,
        county,
        state,
        validate_coverage=validate_coverage,
        place_hint=place_hint,
    )
    return parcels, zoning


async def _discover_pair(
    lat: float,
    lng: float,
    county: str,
    state: str,
    *,
    validate_coverage: bool = True,
    place_hint: str | None = None,
) -> tuple[DatasetInfo | None, DatasetInfo | None]:
    """Run the three-stage discovery cascade for both parcels and zoning."""

    async def find(dataset_type: str) -> DatasetInfo | None:
        # Stage 1: ArcGIS Hub
        result = await _search_hub(
            lat,
            lng,
            county,
            state,
            dataset_type=dataset_type,
            validate_coverage=validate_coverage,
            place_hint=place_hint,
        )
        if result:
            return result

        # Stage 2: State-level ArcGIS servers (Option 2)
        result = await _search_state_servers(
            lat,
            lng,
            county,
            state,
            dataset_type=dataset_type,
        )
        if result:
            return result

        # Stage 3: County URL pattern probing (Option 3)
        result = await _probe_county_url_patterns(
            lat,
            lng,
            county,
            state,
            dataset_type=dataset_type,
        )
        return result

    parcels = await find("parcels")
    zoning = await find("zoning")
    return parcels, zoning


async def _search_hub(
    lat: float,
    lng: float,
    county: str,
    state: str,
    dataset_type: str,
    *,
    validate_coverage: bool = True,
    place_hint: str | None = None,
) -> DatasetInfo | None:
    """Search Hub for a specific dataset type and return the best match."""
    # Use full state name in Hub search queries — abbreviations like "NV" are
    # less reliably indexed than "Nevada" in ArcGIS Hub metadata.
    state_full = _expand_state(state) if len(state.strip()) == 2 else state
    place = f" {place_hint}" if place_hint else ""
    if dataset_type == "parcels":
        search_term = f"property parcels {county} {state_full}{place}"
    else:
        search_term = f"zoning {county} {state_full}{place}"

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

        metadata_text = " ".join(
            str(value or "")
            for value in [
                dataset_name,
                attrs.get("orgName", ""),
                attrs.get("snippet", ""),
                attrs.get("description", ""),
                attrs.get("tags", ""),
                dataset_url,
            ]
        )
        score = _score_dataset(
            fields,
            dataset_name,
            dataset_type,
            dataset_url,
            jurisdiction_text=metadata_text,
            county=county,
            state=state,
            place_hint=place_hint,
        )
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
    if scored and not validate_coverage:
        candidate = scored[0][1]
        logger.info(
            "Discovered %s dataset for %s, %s without coverage validation: %s",
            dataset_type,
            county,
            state,
            candidate.name,
        )
        return candidate

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
        if validate_coverage:
            logger.warning(
                "No %s dataset passed coverage validation for %s, %s",
                dataset_type,
                county,
                state,
            )
            return None
        fallback = scored[0][1]
        logger.warning(
            "Using unvalidated top-scored %s fallback for %s, %s: %s",
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
    *,
    jurisdiction_text: str = "",
    county: str = "",
    state: str = "",
    place_hint: str | None = None,
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
    jurisdiction_lower = jurisdiction_text.lower()
    county_lower = county.lower().strip()
    state_lower = state.lower().strip()
    # Also check the full state name so "NV" matches metadata containing "nevada"
    state_full_lower = _expand_state(state_lower)
    place_lower = (place_hint or "").lower().strip()

    if county_lower and f"{county_lower} county" in jurisdiction_lower:
        score += 8.0
    elif county_lower and county_lower in jurisdiction_lower:
        score += 5.0
    if place_lower and place_lower in jurisdiction_lower:
        score += 4.0
    if state_lower and (
        state_lower in jurisdiction_lower or state_full_lower in jurisdiction_lower
    ):
        score += 1.0

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


# ---------------------------------------------------------------------------
# Option 2 — State-level ArcGIS server probing
# ---------------------------------------------------------------------------


async def _probe_arcgis_server(
    base_url: str,
    county: str,
    state: str,
    dataset_type: str,
    lat: float,
    lng: float,
    *,
    timeout: float = 10.0,
) -> DatasetInfo | None:
    """Crawl an ArcGIS REST services tree and return the best matching dataset.

    Strategy:
    1. Fetch the root ``/rest/services`` JSON to get the folder list.
    2. Skip folders whose names contain none of ``_RELEVANT_FOLDER_KEYWORDS``.
    3. For each relevant folder, fetch its services list.
    4. For each MapServer/FeatureServer, fetch layer metadata.
    5. Score with ``_score_dataset()`` and validate coverage.
    """
    from datetime import datetime, timezone

    async def _get_json(url: str, params: dict | None = None) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, params={"f": "json", **(params or {})})
                resp.raise_for_status()
                result: dict[str, Any] = resp.json()
                return result
        except Exception:
            logger.debug("ArcGIS probe failed: %s", url)
            return None

    root = await _get_json(base_url)
    if not root:
        return None

    # Gather folders to probe (root services + relevant sub-folders)
    folders_to_check: list[str] = [""]  # "" → root
    for folder in root.get("folders", []):
        folder_lower = folder.lower()
        if any(kw in folder_lower for kw in _RELEVANT_FOLDER_KEYWORDS):
            folders_to_check.append(folder)

    best_score = -1.0
    best_candidate: DatasetInfo | None = None

    for folder in folders_to_check:
        folder_url = f"{base_url}/{folder}" if folder else base_url
        folder_data = await _get_json(folder_url)
        if not folder_data:
            continue

        for svc in folder_data.get("services", []):
            svc_type = svc.get("type", "")
            if svc_type not in ("MapServer", "FeatureServer"):
                continue

            svc_name = svc.get("name", "")
            # svc_name may be "FolderName/ServiceName"
            svc_url = f"{base_url}/{svc_name}/{svc_type}"

            svc_data = await _get_json(svc_url)
            if not svc_data:
                continue

            for layer in svc_data.get("layers", []):
                layer_id = layer.get("id", 0)
                layer_url = f"{svc_url}/{layer_id}"
                layer_data = await _get_json(layer_url)
                if not layer_data:
                    continue

                fields = [f.get("name", "") for f in layer_data.get("fields", [])]
                if not fields:
                    continue

                layer_name = layer_data.get("name", svc_name)
                jurisdiction_text = f"{svc_name} {layer_name} {county} {state}"

                score = _score_dataset(
                    fields,
                    layer_name,
                    dataset_type,
                    layer_url,
                    jurisdiction_text=jurisdiction_text,
                    county=county,
                    state=state,
                )
                if score <= best_score:
                    continue

                candidate = DatasetInfo(
                    dataset_id=layer_url,
                    name=f"{svc_name}/{layer_name}",
                    url=svc_url,
                    layer_id=layer_id,
                    dataset_type=dataset_type,
                    county=county,
                    state=state,
                    fields=fields,
                    discovered_at=datetime.now(timezone.utc),
                )
                if await _has_coverage(candidate, lat, lng):
                    best_score = score
                    best_candidate = candidate
                    logger.debug(
                        "ArcGIS probe candidate: %s score=%.2f",
                        candidate.name,
                        score,
                    )

    if best_candidate:
        logger.info(
            "ArcGIS probe found %s dataset for %s, %s: %s (score=%.2f)",
            dataset_type,
            county,
            state,
            best_candidate.name,
            best_score,
        )
    return best_candidate


async def _search_state_servers(
    lat: float,
    lng: float,
    county: str,
    state: str,
    *,
    dataset_type: str,
) -> DatasetInfo | None:
    """Option 2: probe known state-level ArcGIS REST servers.

    Looks up ``_STATE_SERVERS[state.lower()]`` and calls ``_probe_arcgis_server``
    on each server URL.  Returns the first successful result.
    """
    state_key = state.lower().strip()
    # Accept both "nv" and "nevada" as keys
    servers = _STATE_SERVERS.get(state_key) or _STATE_SERVERS.get(
        state_key[:2] if len(state_key) > 2 else state_key
    )
    if not servers:
        return None

    logger.info(
        "Trying %d state server(s) for %s, %s (%s)",
        len(servers),
        county,
        state,
        dataset_type,
    )
    for server_url in servers:
        result = await _probe_arcgis_server(server_url, county, state, dataset_type, lat, lng)
        if result:
            return result

    return None


async def _probe_county_url_patterns(
    lat: float,
    lng: float,
    county: str,
    state: str,
    *,
    dataset_type: str,
) -> DatasetInfo | None:
    """Option 3: probe common county ArcGIS server URL templates.

    Generates candidate URLs from ``_COUNTY_URL_PATTERNS`` using the county/state
    slug, fires a HEAD request concurrently to filter live servers, then calls
    ``_probe_arcgis_server`` on each live server in score order.
    """
    import asyncio
    import re

    county_slug = re.sub(r"[^a-z0-9]", "", county.lower())
    state_slug = state.lower().strip()
    if len(state_slug) > 2:
        # Convert full state name to 2-letter for URL patterns
        for abbr, full in _STATE_FULL_NAMES.items():
            if full == state_slug:
                state_slug = abbr
                break

    candidate_urls = [
        pat.format(county=county_slug, state=state_slug) for pat in _COUNTY_URL_PATTERNS
    ]

    # Quick HEAD probe — skip URLs that don't return 200 at the root
    async def _is_live(url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, params={"f": "json"})
                return resp.status_code < 400
        except Exception:
            return False

    logger.info(
        "Probing %d URL patterns for %s, %s (%s)",
        len(candidate_urls),
        county,
        state,
        dataset_type,
    )
    live_flags = await asyncio.gather(*[_is_live(url) for url in candidate_urls])
    live_urls = [url for url, alive in zip(candidate_urls, live_flags) if alive]

    if not live_urls:
        logger.info("No live county GIS servers found for %s, %s", county, state)
        return None

    logger.info(
        "%d live server(s) found for %s, %s: %s",
        len(live_urls),
        county,
        state,
        live_urls[:3],
    )
    for server_url in live_urls:
        result = await _probe_arcgis_server(server_url, county, state, dataset_type, lat, lng)
        if result:
            return result

    return None
