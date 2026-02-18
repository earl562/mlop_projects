"""Municode auto-discovery — dynamically find municipalities with zoning data.

Queries the Municode Library API at runtime to discover all South Florida
municipalities that have zoning ordinances hosted on Municode. Results are
cached per-process so discovery only runs once.

Production pattern: self-discovering data pipeline with graceful fallback.
If the Library API is down, consumers fall back to hardcoded _FALLBACK_CONFIGS.

Library API base: https://library.municode.com/api  (requires X-CSRF: 1 header)
Discovery flow per municipality:
  1. Clients/stateAbbr?stateAbbr=FL  →  all FL clients
  2. Match municipality name to client_id
  3. Products/clientId/{id}  →  find CODES product
  4. Jobs/latest/{productId}  →  fresh job_id
  5. codesToc/children?productId=X&jobId=Y  →  root TOC
  6. Search headings for zoning keywords  →  zoning_node_id
  7. Verify children > 0 (not a stub)
"""

import asyncio
import json
import logging
import re
import time
from pathlib import Path

import httpx

from plotlot.core.types import MunicodeConfig

logger = logging.getLogger(__name__)

LIBRARY_API_URL = "https://library.municode.com/api"
LIBRARY_HEADERS = {"X-CSRF": "1", "Accept": "application/json"}

ZONING_KEYWORDS = [
    "zoning", "land development", "land use", "uldc", "unified land",
    "development code", "development regulations", "planning and zoning",
    "building and zoning", "comprehensive zoning", "zoning regulations",
    "zoning ordinance", "land development code", "land development regulations",
    "appendix a", "appendix b",  # some munis put zoning in appendices
]

# Disk cache settings
CACHE_DIR = Path.home() / ".plotlot"
CACHE_FILE = CACHE_DIR / "discovery_cache.json"
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours

# All target municipalities by county label.
# These are the 104 municipalities + 3 unincorporated areas across
# Miami-Dade, Broward, and Palm Beach counties.
SOUTH_FLORIDA_MUNICIPALITIES: dict[str, list[str]] = {
    "miami_dade": [
        "Aventura", "Bal Harbour", "Bay Harbor Islands", "Biscayne Park",
        "Coral Gables", "Cutler Bay", "Doral", "El Portal", "Florida City",
        "Golden Beach", "Hialeah", "Hialeah Gardens", "Homestead",
        "Indian Creek Village", "Key Biscayne", "Medley", "Miami",
        "Miami Beach", "Miami Gardens", "Miami Lakes", "Miami Springs",
        "North Miami", "North Miami Beach", "Opa-locka", "Palmetto Bay",
        "Pinecrest", "South Miami", "Sunny Isles Beach", "Surfside",
        "Sweetwater", "Virginia Gardens", "West Miami",
    ],
    "broward": [
        "Coconut Creek", "Cooper City", "Coral Springs", "Dania Beach",
        "Deerfield Beach", "Fort Lauderdale", "Hallandale Beach",
        "Lauderdale Lakes", "Lauderhill", "Margate", "Miramar",
        "North Lauderdale", "Oakland Park", "Parkland", "Plantation",
        "Sea Ranch Lakes", "Southwest Ranches", "Sunrise", "Tamarac",
        "West Park", "Wilton Manors", "Davie", "Hillsboro Beach",
        "Lauderdale-by-the-Sea", "Pembroke Park",
    ],
    "palm_beach": [
        "Atlantis", "Belle Glade", "Boca Raton", "Boynton Beach",
        "Cloud Lake", "Delray Beach", "Glen Ridge", "Greenacres",
        "Gulf Stream", "Haverhill", "Highland Beach", "Hypoluxo",
        "Juno Beach", "Jupiter", "Jupiter Inlet Colony",
        "Lake Clarke Shores", "Lake Park", "Lake Worth Beach", "Lantana",
        "Loxahatchee Groves", "Mangonia Park", "North Palm Beach",
        "Ocean Ridge", "Pahokee", "Palm Beach", "Palm Beach Gardens",
        "Palm Beach Shores", "Palm Springs", "Riviera Beach",
        "Royal Palm Beach", "South Bay", "South Palm Beach", "Tequesta",
        "Wellington", "West Palm Beach", "Westlake",
    ],
}

# Known name mismatches between our target list and Municode client names.
_NAME_MAP: dict[str, str] = {
    "Indian Creek Village": "Indian Creek",
    "Opa-locka": "Opa-Locka",
    "Lauderdale-by-the-Sea": "Lauderdale-By-The-Sea",
    "Lake Worth Beach": "Lake Worth",
    "Sea Ranch Lakes": "Sea Ranch Lakes",
    "Glen Ridge": "Glen Ridge",
    "Cloud Lake": "Cloud Lake",
    "Bal Harbour": "Bal Harbour Village",
    "West Park": "West Park",
    "Pembroke Park": "Pembroke Park",
}

# Module-level cache
_cached_configs: dict[str, MunicodeConfig] | None = None
_cache_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    """Lazy-init the asyncio lock (must be created within an event loop)."""
    global _cache_lock
    if _cache_lock is None:
        _cache_lock = asyncio.Lock()
    return _cache_lock


def clear_cache() -> None:
    """Clear the in-memory and disk caches. Useful for tests and forced re-discovery."""
    global _cached_configs, _cache_lock
    _cached_configs = None
    _cache_lock = None


def _write_disk_cache(configs: dict[str, MunicodeConfig]) -> None:
    """Persist discovery results to disk as JSON."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": time.time(),
            "configs": {
                key: {
                    "municipality": cfg.municipality,
                    "county": cfg.county,
                    "client_id": cfg.client_id,
                    "product_id": cfg.product_id,
                    "job_id": cfg.job_id,
                    "zoning_node_id": cfg.zoning_node_id,
                }
                for key, cfg in configs.items()
            },
        }
        CACHE_FILE.write_text(json.dumps(payload, indent=2))
        logger.info("Wrote discovery cache to %s (%d entries)", CACHE_FILE, len(configs))
    except OSError as e:
        logger.warning("Failed to write discovery cache: %s", e)


def _read_disk_cache() -> dict[str, MunicodeConfig] | None:
    """Read discovery results from disk if fresh enough."""
    if not CACHE_FILE.exists():
        return None
    try:
        payload = json.loads(CACHE_FILE.read_text())
        age = time.time() - payload.get("timestamp", 0)
        if age > CACHE_TTL_SECONDS:
            logger.info("Discovery cache expired (%.1f hours old)", age / 3600)
            return None
        configs = {
            key: MunicodeConfig(**data)
            for key, data in payload.get("configs", {}).items()
        }
        logger.info(
            "Loaded %d configs from disk cache (%.1f hours old)",
            len(configs), age / 3600,
        )
        return configs
    except (OSError, json.JSONDecodeError, TypeError) as e:
        logger.warning("Failed to read discovery cache: %s", e)
        return None


def _make_key(name: str) -> str:
    """Convert municipality name to a dict key.

    'Fort Lauderdale' → 'fort_lauderdale'
    'Miami-Dade' → 'miami_dade'
    """
    key = name.lower().strip()
    key = re.sub(r"[^a-z0-9\s]", " ", key)
    key = re.sub(r"\s+", "_", key.strip())
    return key


def _normalize(name: str) -> str:
    """Normalize a name for fuzzy matching."""
    return (
        name.lower()
        .strip()
        .replace("-", " ")
        .replace("'", "")
        .replace(".", "")
        .replace("village", "")
        .strip()
    )


def _match_client(
    target_name: str, fl_clients: list[dict],
) -> dict | None:
    """Find the best matching Municode client for a municipality name.

    Strategy:
      1. Exact normalized match
      2. Check _NAME_MAP for known aliases
      3. 'City of X' / 'Town of X' / 'Village of X' variants
      4. Substring match with length guard (avoid 'Miami' matching 'Miami Beach')
    """
    mapped_name = _NAME_MAP.get(target_name, target_name)
    norm_target = _normalize(mapped_name)

    # Pass 1: exact match
    for client in fl_clients:
        cname = client.get("ClientName", "")
        if _normalize(cname) == norm_target:
            return client

    # Pass 2: prefix variants (City of X, Town of X, Village of X)
    prefixed = [f"city of {norm_target}", f"town of {norm_target}", f"village of {norm_target}"]
    for client in fl_clients:
        norm_cname = _normalize(client.get("ClientName", ""))
        if norm_cname in prefixed:
            return client

    # Pass 3: substring with length guard
    for client in fl_clients:
        norm_cname = _normalize(client.get("ClientName", ""))
        if norm_target in norm_cname or norm_cname in norm_target:
            if abs(len(norm_target) - len(norm_cname)) < 4:
                return client

    return None


def _search_toc_for_zoning(toc_items: list[dict]) -> list[dict]:
    """Search TOC items for zoning-related chapters."""
    matches = []
    for item in toc_items:
        heading = (item.get("Heading") or item.get("heading") or "").lower()
        title = (item.get("Title") or item.get("title") or heading).lower()
        combined = heading + " " + title
        for kw in ZONING_KEYWORDS:
            if kw in combined:
                matches.append(item)
                break
    return matches


async def _deep_search_toc(
    client: httpx.AsyncClient,
    product_id: int,
    job_id: int,
    root_toc: list[dict],
) -> list[dict]:
    """Search one level deeper in the TOC for zoning chapters.

    Some municipalities nest zoning under "Part II", "Code of Ordinances",
    or "Appendices" — this checks children of top-level nodes.
    """
    matches = _search_toc_for_zoning(root_toc)
    if matches:
        return matches

    # Search children of top-level nodes
    for item in root_toc:
        node_id = str(
            item.get("Id") or item.get("id")
            or item.get("NodeId") or item.get("nodeId") or ""
        )
        if not node_id:
            continue
        children = await _fetch_json(
            client, "codesToc/children",
            productId=product_id, jobId=job_id, nodeId=node_id,
        )
        if children and isinstance(children, list):
            child_matches = _search_toc_for_zoning(children)
            matches.extend(child_matches)

    return matches


async def _fetch_json(
    client: httpx.AsyncClient, path: str, **params: str | int,
) -> dict | list | None:
    """GET request to the Municode Library API with error handling."""
    url = f"{LIBRARY_API_URL}/{path}"
    try:
        resp = await client.get(url, params=params, headers=LIBRARY_HEADERS)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Library API error: %s %s — %s", path, params, e)
        return None


async def _discover_municipality(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    county: str,
    name: str,
    fl_clients: list[dict],
) -> tuple[str, MunicodeConfig | None]:
    """Discover a single municipality's Municode config.

    Returns (key, config) or (key, None) if not found.
    """
    key = _make_key(name)

    async with semaphore:
        matched = _match_client(name, fl_clients)
        if not matched:
            logger.debug("No Municode client found for %s", name)
            return key, None

        client_id = matched.get("ClientID", 0)

        products = await _fetch_json(client, f"Products/clientId/{client_id}")
        if not products or not isinstance(products, list):
            return key, None

        code_products = [
            p for p in products
            if isinstance(p, dict) and p.get("ContentType", {}).get("Id") == "CODES"
        ]
        if not code_products:
            return key, None

        for prod in code_products:
            product_id = prod.get("ProductID")
            if not product_id:
                continue

            job_data = await _fetch_json(client, f"Jobs/latest/{product_id}")
            if not job_data or not isinstance(job_data, dict):
                continue
            job_id = job_data.get("Id")
            if not job_id:
                continue

            toc = await _fetch_json(
                client, "codesToc/children",
                productId=product_id, jobId=job_id,
            )
            if not toc or not isinstance(toc, list):
                continue

            matches = await _deep_search_toc(client, product_id, job_id, toc)
            if not matches:
                continue

            def _sort_key(m):
                h = (m.get("Heading") or "").lower()
                if "zoning" in h:
                    return 0
                if "land development" in h or "land use" in h:
                    return 1
                return 2

            sorted_matches = sorted(matches, key=_sort_key)

            for candidate in sorted_matches:
                node_id = str(
                    candidate.get("Id") or candidate.get("id")
                    or candidate.get("NodeId") or candidate.get("nodeId") or ""
                )
                if not node_id:
                    continue

                children = await _fetch_json(
                    client, "codesToc/children",
                    productId=product_id, jobId=job_id, nodeId=node_id,
                )
                if not children or not isinstance(children, list) or len(children) == 0:
                    logger.debug(
                        "Stub zoning chapter for %s: %s — trying next match",
                        name, candidate.get("Heading", ""),
                    )
                    continue

                config = MunicodeConfig(
                    municipality=name,
                    county=county,
                    client_id=client_id,
                    product_id=product_id,
                    job_id=job_id,
                    zoning_node_id=node_id,
                )
                logger.info(
                    "Discovered %s: client=%d product=%d job=%d node=%s (%d children)",
                    name, client_id, product_id, job_id, node_id, len(children),
                )
                return key, config

        return key, None


async def discover_all(
    max_concurrent: int = 5,
) -> dict[str, MunicodeConfig]:
    """Discover all South Florida municipalities with zoning data on Municode.

    Makes ~5 API calls per municipality with rate limiting.

    Returns:
        Dict of {key: MunicodeConfig} for all discovered municipalities.
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient(timeout=30.0) as client:
        fl_clients = await _fetch_json(client, "Clients/stateAbbr", stateAbbr="FL")
        if not fl_clients or not isinstance(fl_clients, list):
            logger.error("Failed to fetch FL clients from Municode Library API")
            return {}

        logger.info("Fetched %d FL clients from Municode", len(fl_clients))

        tasks = []
        for county, names in SOUTH_FLORIDA_MUNICIPALITIES.items():
            for name in names:
                tasks.append(
                    _discover_municipality(client, semaphore, county, name, fl_clients)
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        configs: dict[str, MunicodeConfig] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Discovery task failed: %s", result)
                continue
            key, config = result
            if config is not None:
                configs[key] = config

        logger.info("Discovered %d municipalities with zoning data", len(configs))
        return configs


async def get_municode_configs(
    force_refresh: bool = False,
) -> dict[str, MunicodeConfig]:
    """Get all known Municode configs, using cached discovery results.

    On first call, runs full discovery against the Library API.
    Subsequent calls return the cached result.
    """
    global _cached_configs

    lock = _get_lock()
    async with lock:
        if _cached_configs is not None and not force_refresh:
            return _cached_configs

        # Check disk cache before hitting the API
        if not force_refresh:
            disk_configs = _read_disk_cache()
            if disk_configs:
                _cached_configs = disk_configs
                return _cached_configs

        logger.info("Running Municode auto-discovery...")
        try:
            configs = await discover_all()
        except Exception as e:
            logger.error("Discovery failed, returning fallback configs: %s", e)
            from plotlot.core.types import _FALLBACK_CONFIGS
            _cached_configs = dict(_FALLBACK_CONFIGS)
            return _cached_configs

        if not configs:
            logger.warning("Discovery returned 0 results, using fallback configs")
            from plotlot.core.types import _FALLBACK_CONFIGS
            _cached_configs = dict(_FALLBACK_CONFIGS)
            return _cached_configs

        from plotlot.core.types import _FALLBACK_CONFIGS
        for key, fallback in _FALLBACK_CONFIGS.items():
            if key not in configs:
                configs[key] = fallback

        _cached_configs = configs
        _write_disk_cache(configs)
        logger.info("Cached %d municipality configs", len(_cached_configs))
        return _cached_configs
