"""Municode auto-discovery — dynamically find municipalities with zoning data.

Queries the Municode Library API at runtime to discover all South Florida
and NC Charlotte metro municipalities that have zoning ordinances hosted
on Municode.  Results are cached per-process so discovery only runs once.

Production pattern: self-discovering data pipeline with graceful fallback.
If the Library API is down, consumers fall back to hardcoded _FALLBACK_CONFIGS
(FL) and _NC_FALLBACK_CONFIGS (NC).

Library API base: https://library.municode.com/api  (requires X-CSRF: 1 header)
Discovery flow per municipality:
  1. Clients/stateAbbr?stateAbbr=FL (or NC)  →  all clients for that state
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
    "zoning",
    "land development",
    "land use",
    "uldc",
    "unified land",
    "development code",
    "development regulations",
    "planning and zoning",
    "building and zoning",
    "comprehensive zoning",
    "zoning regulations",
    "zoning ordinance",
    "land development code",
    "land development regulations",
    "appendix a",
    "appendix b",  # some munis put zoning in appendices
    # Industrial / data center site selection keywords
    "industrial",
    "manufacturing",
    "light industrial",
    "heavy industrial",
    "industrial district",
    "industrial park",
    "special use",
    "utility",
    "utilities",
    "performance standards",
    "noise",
    "vibration",
    "outdoor storage",
    "loading",
    "truck",
    "warehouse",
    "logistics",
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
        "Aventura",
        "Bal Harbour",
        "Bay Harbor Islands",
        "Biscayne Park",
        "Coral Gables",
        "Cutler Bay",
        "Doral",
        "El Portal",
        "Florida City",
        "Golden Beach",
        "Hialeah",
        "Hialeah Gardens",
        "Homestead",
        "Indian Creek Village",
        "Key Biscayne",
        "Medley",
        "Miami",
        "Miami Beach",
        "Miami Gardens",
        "Miami Lakes",
        "Miami Springs",
        "North Miami",
        "North Miami Beach",
        "Opa-locka",
        "Palmetto Bay",
        "Pinecrest",
        "South Miami",
        "Sunny Isles Beach",
        "Surfside",
        "Sweetwater",
        "Virginia Gardens",
        "West Miami",
    ],
    "broward": [
        "Coconut Creek",
        "Cooper City",
        "Coral Springs",
        "Dania Beach",
        "Deerfield Beach",
        "Fort Lauderdale",
        "Hallandale Beach",
        "Lauderdale Lakes",
        "Lauderhill",
        "Margate",
        "Miramar",
        "North Lauderdale",
        "Oakland Park",
        "Parkland",
        "Plantation",
        "Sea Ranch Lakes",
        "Southwest Ranches",
        "Sunrise",
        "Tamarac",
        "West Park",
        "Wilton Manors",
        "Davie",
        "Hillsboro Beach",
        "Lauderdale-by-the-Sea",
        "Pembroke Park",
    ],
    "palm_beach": [
        "Atlantis",
        "Belle Glade",
        "Boca Raton",
        "Boynton Beach",
        "Cloud Lake",
        "Delray Beach",
        "Glen Ridge",
        "Greenacres",
        "Gulf Stream",
        "Haverhill",
        "Highland Beach",
        "Hypoluxo",
        "Juno Beach",
        "Jupiter",
        "Jupiter Inlet Colony",
        "Lake Clarke Shores",
        "Lake Park",
        "Lake Worth Beach",
        "Lantana",
        "Loxahatchee Groves",
        "Mangonia Park",
        "North Palm Beach",
        "Ocean Ridge",
        "Pahokee",
        "Palm Beach",
        "Palm Beach Gardens",
        "Palm Beach Shores",
        "Palm Springs",
        "Riviera Beach",
        "Royal Palm Beach",
        "South Bay",
        "South Palm Beach",
        "Tequesta",
        "Wellington",
        "West Palm Beach",
        "Westlake",
    ],
}

# NC Charlotte metro municipalities by county.
# Covers Mecklenburg + surrounding counties (Cabarrus, Iredell, Union).
NC_CHARLOTTE_METRO: dict[str, list[str]] = {
    "mecklenburg": [
        "Charlotte",
        "Huntersville",
        "Cornelius",
        "Davidson",
        "Matthews",
        "Mint Hill",
        "Pineville",
    ],
    "union": [
        "Indian Trail",
        "Stallings",
        "Weddington",
        "Waxhaw",
        "Monroe",
    ],
    "cabarrus": [
        "Concord",
        "Kannapolis",
        "Harrisburg",
        "Midland",
        "Locust",
    ],
    "iredell": [
        "Mooresville",
    ],
}

# TX major metro municipalities by county.
# Covers Houston, Dallas-Fort Worth, San Antonio, Austin, and El Paso metros.
TEXAS_METROS: dict[str, list[str]] = {
    "harris": [
        "Houston",
        "Bellaire",
        "Humble",
        "Jersey Village",
        "Katy",
        "La Porte",
        "Missouri City",
        "Pasadena",
        "Pearland",
        "Spring Valley Village",
        "Stafford",
        "Sugar Land",
        "West University Place",
    ],
    "fort_bend": [
        "Richmond",
        "Rosenberg",
        "Fulshear",
        "Needville",
    ],
    "montgomery": [
        "Conroe",
        "The Woodlands",
        "Shenandoah",
        "Magnolia",
    ],
    "dallas": [
        "Dallas",
        "Balch Springs",
        "Cedar Hill",
        "Cockrell Hill",
        "DeSoto",
        "Duncanville",
        "Farmers Branch",
        "Garland",
        "Glenn Heights",
        "Grand Prairie",
        "Highland Park",
        "Irving",
        "Lancaster",
        "Mesquite",
        "Richardson",
        "Rowlett",
        "Sachse",
        "Seagoville",
        "University Park",
        "Wilmer",
    ],
    "tarrant": [
        "Fort Worth",
        "Arlington",
        "Bedford",
        "Benbrook",
        "Colleyville",
        "Euless",
        "Grapevine",
        "Haltom City",
        "Hurst",
        "Keller",
        "Mansfield",
        "North Richland Hills",
        "Southlake",
        "Watauga",
    ],
    "collin": [
        "Allen",
        "Frisco",
        "McKinney",
        "Plano",
        "Prosper",
        "Wylie",
    ],
    "denton": [
        "Denton",
        "Flower Mound",
        "Lewisville",
        "Little Elm",
        "The Colony",
    ],
    "bexar": [
        "San Antonio",
        "Alamo Heights",
        "Castle Hills",
        "Converse",
        "Helotes",
        "Leon Valley",
        "Live Oak",
        "Schertz",
        "Selma",
        "Universal City",
        "Windcrest",
    ],
    "travis": [
        "Austin",
        "Bee Cave",
        "Cedar Park",
        "Lakeway",
        "Pflugerville",
        "Rollingwood",
        "Sunset Valley",
        "West Lake Hills",
    ],
    "williamson": [
        "Georgetown",
        "Round Rock",
        "Leander",
        "Taylor",
    ],
    "el_paso": [
        "El Paso",
        "Anthony",
        "Socorro",
        "Horizon City",
    ],
}

# GA major metro municipalities by county.
# Covers Atlanta metro, Savannah, Augusta, and Columbus.
GEORGIA_METROS: dict[str, list[str]] = {
    "fulton": [
        "Atlanta",
        "Alpharetta",
        "College Park",
        "East Point",
        "Fairburn",
        "Hapeville",
        "Johns Creek",
        "Milton",
        "Mountain Park",
        "Palmetto",
        "Roswell",
        "Sandy Springs",
        "Union City",
    ],
    "dekalb": [
        "Avondale Estates",
        "Brookhaven",
        "Chamblee",
        "Clarkston",
        "Decatur",
        "Doraville",
        "Dunwoody",
        "Lithonia",
        "Pine Lake",
        "Stone Mountain",
        "Stonecrest",
        "Tucker",
    ],
    "gwinnett": [
        "Buford",
        "Dacula",
        "Duluth",
        "Lawrenceville",
        "Lilburn",
        "Loganville",
        "Norcross",
        "Peachtree Corners",
        "Snellville",
        "Suwanee",
    ],
    "cobb": [
        "Acworth",
        "Austell",
        "Kennesaw",
        "Marietta",
        "Powder Springs",
        "Smyrna",
    ],
    "clayton": [
        "Forest Park",
        "Jonesboro",
        "Lake City",
        "Morrow",
        "Riverdale",
    ],
    "chatham": [
        "Savannah",
        "Bloomingdale",
        "Garden City",
        "Pooler",
        "Port Wentworth",
        "Tybee Island",
        "Thunderbolt",
    ],
    "richmond": [
        "Augusta",
        "Hephzibah",
    ],
    "muscogee": [
        "Columbus",
    ],
    "bibb": [
        "Macon",
    ],
    "hall": [
        "Gainesville",
    ],
    "henry": [
        "McDonough",
        "Hampton",
        "Locust Grove",
        "Stockbridge",
    ],
    "forsyth": [
        "Cumming",
    ],
    "cherokee": [
        "Canton",
        "Holly Springs",
        "Woodstock",
    ],
    "douglas": [
        "Douglasville",
    ],
}

# SC major metro municipalities by county.
# Covers Charleston, Columbia, Greenville, and Myrtle Beach metros.
SOUTH_CAROLINA_METROS: dict[str, list[str]] = {
    "charleston": [
        "Charleston",
        "Folly Beach",
        "Isle of Palms",
        "Mount Pleasant",
        "North Charleston",
        "Sullivan's Island",
    ],
    "berkeley": [
        "Goose Creek",
        "Hanahan",
        "Moncks Corner",
        "Summerville",
    ],
    "dorchester": [
        "Summerville",
        "St. George",
    ],
    "richland": [
        "Columbia",
        "Forest Acres",
        "Irmo",
    ],
    "lexington": [
        "Cayce",
        "Lexington",
        "West Columbia",
    ],
    "greenville": [
        "Greenville",
        "Greer",
        "Mauldin",
        "Simpsonville",
        "Travelers Rest",
    ],
    "spartanburg": [
        "Spartanburg",
        "Boiling Springs",
        "Duncan",
        "Inman",
    ],
    "horry": [
        "Myrtle Beach",
        "Conway",
        "North Myrtle Beach",
        "Surfside Beach",
    ],
    "georgetown": [
        "Georgetown",
        "Pawleys Island",
    ],
    "york": [
        "Rock Hill",
        "Fort Mill",
        "Tega Cay",
        "York",
    ],
    "beaufort": [
        "Beaufort",
        "Bluffton",
        "Hilton Head Island",
        "Port Royal",
    ],
    "aiken": [
        "Aiken",
        "North Augusta",
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
    # NC Charlotte metro aliases
    "Indian Trail": "Indian Trail",
    "Mint Hill": "Mint Hill",
    # TX aliases
    "West University Place": "West University Place",
    "Spring Valley Village": "Spring Valley Village",
    "North Richland Hills": "North Richland Hills",
    "The Woodlands": "Woodlands",
    "The Colony": "Colony",
    # GA aliases
    "Peachtree Corners": "Peachtree Corners",
    "Stone Mountain": "Stone Mountain",
    # SC aliases
    "Mount Pleasant": "Mount Pleasant",
    "North Charleston": "North Charleston",
    "Sullivan's Island": "Sullivans Island",
    "Isle of Palms": "Isle of Palms",
    "North Myrtle Beach": "North Myrtle Beach",
    "Hilton Head Island": "Hilton Head Island",
    "North Augusta": "North Augusta",
    # CA NorCal aliases — Municode often uses "City of X" which pass-2 handles,
    # but some clients have unusual names worth mapping explicitly.
    "East Palo Alto": "East Palo Alto",
    "Mountain View": "Mountain View",
    "Los Altos Hills": "Los Altos Hills",
    "Portola Valley": "Portola Valley",
    "Woodside": "Woodside",
    "Atherton": "Atherton",
    "San Ramon": "San Ramon",
    "Walnut Creek": "Walnut Creek",
    "Pleasant Hill": "Pleasant Hill",
    "El Cerrito": "El Cerrito",
    "Elk Grove": "Elk Grove",
    "Citrus Heights": "Citrus Heights",
}

# CA Northern California high-development metros by county.
# Priority order based on LAND DEAL ACTIVITY for PlotLot's core use case
# (land acquisition pricing for residential development), NOT permit volume:
#
#   1. sacramento    — Eliminated SFR zoning (FAR-limited = PlotLot's exact calc).
#                      $583M traded in 2025, Waegell (6,916 units), fastest-growing CA metro.
#   2. contra_costa  — Concord Naval Weapons Station (15,600 units, master dev being finalized).
#                      Antioch/Pittsburg lead East Bay rent growth. Low land costs = high deal vol.
#   3. alameda       — Fremont 13,000-unit RHNA mandate, Milpitas 60du/acre TOD, Hayward corridor.
#   4. santa_clara   — San Jose RHNA pressure + city incentive programs. High land cost = fewer
#                      individual deals but still strong developer community.
#   5. san_mateo     — Redwood City infill hub, East Palo Alto accessible land.
#   6. san_francisco — Last: scarce land, deals are institutional-scale ($15M+), not PlotLot's user.
#
# Within each county, cities are ordered by individual land deal activity.
NORCAL_METROS: dict[str, list[str]] = {
    "sacramento": [
        "Sacramento",  # eliminated SFR zoning — every R-1 lot is now a dev site
        "Elk Grove",  # fastest-growing NorCal city (176K), $84M dev pipeline
        "Rancho Cordova",  # Waegell property 6,916 units, Rio Del Oro — massive land deals
        "Roseville",  # fast-growing suburb, active new construction
        "Rocklin",  # same growth corridor as Roseville
        "West Sacramento",  # infill-focused, across from downtown
        "Citrus Heights",
        "Folsom",
        "Davis",
        "Woodland",
        "Lincoln",
    ],
    "contra_costa": [
        "Concord",  # Naval Weapons Station 15,600 units, BART TOD, master dev being finalized
        "Antioch",  # DeNova Homes active, Somersville 702 units, leads East Bay rent growth
        "Pittsburg",  # same submarket as Antioch, BART access, low land costs
        "Richmond",  # large underutilized sites, strong RHNA obligation
        "Brentwood",  # fast-growing outer East Bay, active residential dev
        "San Ramon",
        "Walnut Creek",
        "Pleasant Hill",
        "Martinez",
        "El Cerrito",
        "Hercules",
        "Pinole",
        "Orinda",
        "Lafayette",
        "Moraga",
    ],
    "alameda": [
        "Fremont",  # 13,000-unit RHNA obligation, zoning reform Jan 2024
        "Hayward",  # Mission Blvd corridor priority dev area
        "San Leandro",  # two neighborhood projects recently approved
        "Oakland",  # infill pipeline active, 8-story approvals
        "Union City",  # BART corridor, accessible land
        "Newark",
        "Dublin",  # fast-growing BART corridor
        "Emeryville",  # 1,815 units recently approved
        "Pleasanton",
        "Livermore",
        "Berkeley",
        "Alameda",
        "Albany",
        "Piedmont",
    ],
    "santa_clara": [
        "San Jose",  # RHNA pressure, city multifamily incentive programs
        "Milpitas",  # BART corridor, 60du/acre in Town Center zone
        "Santa Clara",  # 1,700-unit project near Levi's Stadium
        "Sunnyvale",
        "Mountain View",
        "Cupertino",  # Vallco Mall 2,600 units resuming
        "Campbell",
        "Los Altos",
        "Gilroy",
        "Morgan Hill",
        "Los Altos Hills",
        "Monte Sereno",
        "Saratoga",
        "Los Gatos",
        "Palo Alto",  # very high land cost — institutional deals, lower PlotLot relevance
    ],
    "san_mateo": [
        "Redwood City",  # Peninsula infill hub
        "East Palo Alto",  # most accessible land in county, genuine missing-middle market
        "South San Francisco",
        "San Mateo",
        "Daly City",
        "Foster City",
        "Burlingame",
        "San Bruno",
        "Millbrae",
        "Belmont",
        "San Carlos",
        "Half Moon Bay",
        "Menlo Park",
        "Hillsborough",
        "Atherton",  # ultra-high land cost, minimal deal activity for PlotLot users
        "Portola Valley",
        "Woodside",
    ],
    "san_francisco": [
        "San Francisco",  # last: scarce land, institutional-scale deals, lowest PlotLot relevance
    ],
}

# CA SoCal — San Diego County.
# Added to serve Kevin Woo (Jakob Ventures) who is actively evaluating SD addresses.
SOCAL_METROS: dict[str, list[str]] = {
    "san_diego": [
        "San Diego",  # primary — 92110 (Mission Valley) is where Kevin's deal is
        "Chula Vista",  # fast-growing south county, active residential pipeline
        "El Cajon",
        "La Mesa",
        "Santee",
        "Lemon Grove",
        "National City",
        "Coronado",
        "Poway",
        "Escondido",
    ],
}

COUNTY_AUTHORITY_STATES = ("FL", "NC", "CA")

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
                    "state": cfg.state,
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
        configs = {key: MunicodeConfig(**data) for key, data in payload.get("configs", {}).items()}
        logger.info(
            "Loaded %d configs from disk cache (%.1f hours old)",
            len(configs),
            age / 3600,
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


def normalize_county_key(county: str) -> str:
    """Normalize county labels into the keys used by Municode configs.

    Examples:
      ``Miami-Dade County`` -> ``miami_dade``
      ``St. Johns`` -> ``st_johns``
    """

    label = county.strip()
    label = re.sub(r"\bcounty\b", "", label, flags=re.IGNORECASE)
    label = label.replace(" - ", "-")
    return _make_key(label)


def _county_key_from_client_name(client_name: str) -> str | None:
    """Return a county key for exact county government Municode clients.

    Municode state lists include unrelated authorities with "County" in their
    names (water districts, clerks, boards, trusts). For county-level zoning
    research we only want clients whose display name is exactly a county.
    """

    stripped = client_name.strip()
    lowered = stripped.lower()
    agency_words = (" board ", " clerk ", " district", " trust ", " authority")
    if " of " in lowered or "," in lowered or any(word in lowered for word in agency_words):
        return None
    if not re.search(r"\bcounty$", stripped, flags=re.IGNORECASE):
        return None
    return normalize_county_key(stripped)


def _merge_config(configs: dict[str, MunicodeConfig], key: str, config: MunicodeConfig) -> None:
    """Merge configs while preserving same-name authorities across states."""

    state_key = f"{config.state.lower()}_{key}"
    configs[state_key] = config

    existing = configs.get(key)
    if existing is None or existing.state.upper() == config.state.upper():
        configs[key] = config
        return

    existing_key = f"{existing.state.lower()}_{key}"
    configs.setdefault(existing_key, existing)


def _merge_configs(
    configs: dict[str, MunicodeConfig], new_configs: dict[str, MunicodeConfig]
) -> None:
    for key, config in new_configs.items():
        _merge_config(configs, key, config)


def resolve_municode_config(
    configs: dict[str, MunicodeConfig],
    jurisdiction_name: str,
    *,
    state: str | None = None,
) -> MunicodeConfig | None:
    """Resolve a Municode config with state-aware collision handling."""

    key = _make_key(jurisdiction_name)
    state_code = (state or "").strip().upper()

    exact = configs.get(key)
    if exact and (not state_code or exact.state.upper() == state_code):
        return exact

    if state_code:
        state_exact = configs.get(f"{state_code.lower()}_{key}")
        if state_exact:
            return state_exact

    candidates = [cfg for cfg in configs.values() if _make_key(cfg.municipality) == key]
    if state_code:
        candidates = [cfg for cfg in candidates if cfg.state.upper() == state_code]
    if candidates:
        return candidates[0]

    return exact if not state_code else None


# Convenience flat set of all NC target municipality names (lowercased, underscored).
# Defined after _make_key so the helper is available.
NC_CHARLOTTE_METRO_KEYS: set[str] = {
    _make_key(name) for names in NC_CHARLOTTE_METRO.values() for name in names
}

TEXAS_METROS_KEYS: set[str] = {_make_key(name) for names in TEXAS_METROS.values() for name in names}

GEORGIA_METROS_KEYS: set[str] = {
    _make_key(name) for names in GEORGIA_METROS.values() for name in names
}

SOUTH_CAROLINA_METROS_KEYS: set[str] = {
    _make_key(name) for names in SOUTH_CAROLINA_METROS.values() for name in names
}

NORCAL_METROS_KEYS: set[str] = {
    _make_key(name) for names in NORCAL_METROS.values() for name in names
}

SOCAL_METROS_KEYS: set[str] = {_make_key(name) for names in SOCAL_METROS.values() for name in names}

CA_METROS_KEYS: set[str] = NORCAL_METROS_KEYS | SOCAL_METROS_KEYS


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
    target_name: str,
    fl_clients: list[dict],
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


def _toc_node_id(item: dict) -> str:
    return str(item.get("Id") or item.get("id") or item.get("NodeId") or item.get("nodeId") or "")


# Top-level titles worth descending into to find a nested zoning chapter
# (e.g. Tiburon's "Chapter 16 - Zoning" lives under "Title IV - Land ... and Use").
_DESCEND_HINTS = ("zon", "land", "develop", "use", "planning", "part ii", "code of ordinance")


def zoning_rank(heading: str) -> int:
    """Rank a TOC candidate as the *primary* zoning/development code (lower = better).

    A naive "contains the word zoning" match is wrong: Marin's "Title 20 - Coastal
    Zoning Code" contains "zoning" but is a specialized partial code, while the real
    ordinance is "Title 22 - Development Code". This penalizes specialized/partial
    codes and prefers the main code or an actual "... Zoning" chapter.
    """
    h = (heading or "").lower()
    # Specialized / partial codes — never the primary ordinance even if they say "zoning".
    if any(
        x in h
        for x in (
            "coastal",
            "overlay",
            "sign",
            "historic",
            "trip reduction",
            "specific plan",
            "redevelopment",
            "subdivision",
            "appendix",
        )
    ):
        return 6
    if "development code" in h or "land development code" in h or "unified land" in h:
        return 0
    if "zoning ordinance" in h or "zoning code" in h or "comprehensive zoning" in h:
        return 1
    if "zoning" in h:
        return 2
    if "development regulations" in h or "land development" in h:
        return 3
    if "land use" in h:
        return 4
    return 5


async def _deep_search_toc(
    client: httpx.AsyncClient,
    product_id: int,
    job_id: int,
    root_toc: list[dict],
) -> list[dict]:
    """Collect candidate zoning nodes from the TOC, top-level AND one level deep.

    The old version returned early on ANY top-level keyword hit, so a weak match
    ("Title III - Businesses, Professions and Utilities") short-circuited the
    search and the real nested "Chapter 16 - Zoning" was never surfaced. We now
    always also descend into land/zoning/development-ish titles and merge, leaving
    the final pick to :func:`zoning_rank`.
    """
    matches: list[dict] = list(_search_toc_for_zoning(root_toc))

    for item in root_toc:
        node_id = _toc_node_id(item)
        if not node_id:
            continue
        heading = (item.get("Heading") or item.get("heading") or "").lower()
        if not any(hint in heading for hint in _DESCEND_HINTS):
            continue
        children = await _fetch_json(
            client,
            "codesToc/children",
            productId=product_id,
            jobId=job_id,
            nodeId=node_id,
        )
        if children and isinstance(children, list):
            matches.extend(_search_toc_for_zoning(children))

    # Dedup by node id, preserving first-seen order.
    seen: set[str] = set()
    deduped: list[dict] = []
    for m in matches:
        nid = _toc_node_id(m)
        if nid and nid not in seen:
            seen.add(nid)
            deduped.append(m)
    return deduped


async def _fetch_json(
    client: httpx.AsyncClient,
    path: str,
    **params: str | int,
) -> dict | list | None:
    """GET request to the Municode Library API with error handling."""
    url = f"{LIBRARY_API_URL}/{path}"
    try:
        resp = await client.get(url, params=params, headers=LIBRARY_HEADERS)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]
    except (httpx.HTTPError, ValueError) as e:
        logger.warning("Library API error: %s %s — %s", path, params, e)
        return None


async def _discover_municipality(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    county: str,
    name: str,
    fl_clients: list[dict],
    state: str = "FL",
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
            p
            for p in products
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
                client,
                "codesToc/children",
                productId=product_id,
                jobId=job_id,
            )
            if not toc or not isinstance(toc, list):
                continue

            matches = await _deep_search_toc(client, product_id, job_id, toc)
            if not matches:
                continue

            sorted_matches = sorted(matches, key=lambda m: zoning_rank(m.get("Heading") or ""))

            for candidate in sorted_matches:
                node_id = str(
                    candidate.get("Id")
                    or candidate.get("id")
                    or candidate.get("NodeId")
                    or candidate.get("nodeId")
                    or ""
                )
                if not node_id:
                    continue

                children = await _fetch_json(
                    client,
                    "codesToc/children",
                    productId=product_id,
                    jobId=job_id,
                    nodeId=node_id,
                )
                if not children or not isinstance(children, list) or len(children) == 0:
                    logger.debug(
                        "Stub zoning chapter for %s: %s — trying next match",
                        name,
                        candidate.get("Heading", ""),
                    )
                    continue

                config = MunicodeConfig(
                    municipality=name,
                    county=county,
                    client_id=client_id,
                    product_id=product_id,
                    job_id=job_id,
                    zoning_node_id=node_id,
                    state=state,
                )
                logger.info(
                    "Discovered %s: client=%d product=%d job=%d node=%s (%d children)",
                    name,
                    client_id,
                    product_id,
                    job_id,
                    node_id,
                    len(children),
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
                    _discover_municipality(client, semaphore, county, name, fl_clients, state="FL")
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        configs: dict[str, MunicodeConfig] = {}
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("Discovery task failed: %s", result)
                continue
            key, config = result
            if config is not None:
                configs[key] = config

        logger.info("Discovered %d municipalities with zoning data", len(configs))
        return configs


async def discover_nc(
    max_concurrent: int = 5,
) -> dict[str, MunicodeConfig]:
    """Discover NC Charlotte metro municipalities with zoning data on Municode.

    Uses stateAbbr=NC (stateId=34) to fetch all NC clients, then filters
    to the Charlotte metro target list.

    Returns:
        Dict of {key: MunicodeConfig} for discovered NC municipalities.
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient(timeout=30.0) as client:
        nc_clients = await _fetch_json(client, "Clients/stateAbbr", stateAbbr="NC")
        if not nc_clients or not isinstance(nc_clients, list):
            logger.error("Failed to fetch NC clients from Municode Library API")
            return {}

        logger.info("Fetched %d NC clients from Municode", len(nc_clients))

        tasks = []
        for county, names in NC_CHARLOTTE_METRO.items():
            for name in names:
                tasks.append(
                    _discover_municipality(client, semaphore, county, name, nc_clients, state="NC")
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        configs: dict[str, MunicodeConfig] = {}
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("NC discovery task failed: %s", result)
                continue
            key, config = result
            if config is not None:
                configs[key] = config

        logger.info("Discovered %d NC municipalities with zoning data", len(configs))
        return configs


def get_nc_municode_configs() -> dict[str, MunicodeConfig]:
    """Return static NC Charlotte metro Municode configs (fallback).

    Unlike the FL discovery which runs async against the API, this provides
    a synchronous fallback using the verified _NC_FALLBACK_CONFIGS.
    For live discovery, use :func:`discover_nc` instead.

    Returns:
        Dict of {key: MunicodeConfig} for known NC Charlotte metro municipalities.
    """
    from plotlot.core.types import _NC_FALLBACK_CONFIGS

    return dict(_NC_FALLBACK_CONFIGS)


async def _discover_state(
    state_abbr: str,
    metros: dict[str, list[str]],
    max_concurrent: int = 5,
) -> dict[str, MunicodeConfig]:
    """Generic state discovery — queries Municode for all municipalities in a state.

    Args:
        state_abbr: Two-letter state code (TX, GA, SC).
        metros: Dict of {county: [municipality_names]} to discover.
        max_concurrent: Max parallel API calls.

    Returns:
        Dict of {key: MunicodeConfig} for discovered municipalities.
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient(timeout=30.0) as client:
        state_clients = await _fetch_json(client, "Clients/stateAbbr", stateAbbr=state_abbr)
        if not state_clients or not isinstance(state_clients, list):
            logger.error("Failed to fetch %s clients from Municode Library API", state_abbr)
            return {}

        logger.info("Fetched %d %s clients from Municode", len(state_clients), state_abbr)

        tasks = []
        for county, names in metros.items():
            for name in names:
                tasks.append(
                    _discover_municipality(
                        client, semaphore, county, name, state_clients, state=state_abbr
                    )
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        configs: dict[str, MunicodeConfig] = {}
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("%s discovery task failed: %s", state_abbr, result)
                continue
            key, config = result
            if config is not None:
                configs[key] = config

        logger.info("Discovered %d %s municipalities with zoning data", len(configs), state_abbr)
        return configs


async def discover_municode_authority_for_name(
    jurisdiction_name: str,
    state_abbr: str,
    *,
    county: str | None = None,
) -> MunicodeConfig | None:
    """Discover one live Municode zoning authority by name and state.

    This is used as a fallback when an MCP caller asks for a county or
    municipality that is not present in the warm cache yet.
    """

    state_code = state_abbr.strip().upper()
    county_key = normalize_county_key(county or jurisdiction_name)
    async with httpx.AsyncClient(timeout=30.0) as client:
        state_clients = await _fetch_json(client, "Clients/stateAbbr", stateAbbr=state_code)
        if not state_clients or not isinstance(state_clients, list):
            logger.error("Failed to fetch %s clients from Municode Library API", state_code)
            return None
        _, config = await _discover_municipality(
            client,
            asyncio.Semaphore(1),
            county_key,
            jurisdiction_name,
            state_clients,
            state=state_code,
        )
        return config


async def discover_county_authorities(
    state_abbr: str,
    *,
    county: str | None = None,
    max_concurrent: int = 5,
) -> dict[str, MunicodeConfig]:
    """Discover exact county-government Municode authorities for a state.

    The Municode state client API has no county metadata for cities, but many
    counties publish a first-class county client. This discovers those county
    authorities directly and filters out similarly named non-county agencies.
    """

    state_code = state_abbr.strip().upper()
    requested_county_key = normalize_county_key(county) if county else None
    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient(timeout=30.0) as client:
        state_clients = await _fetch_json(client, "Clients/stateAbbr", stateAbbr=state_code)
        if not state_clients or not isinstance(state_clients, list):
            logger.error("Failed to fetch %s clients from Municode Library API", state_code)
            return {}

        targets: list[tuple[str, str]] = []
        for state_client in state_clients:
            if not isinstance(state_client, dict):
                continue
            client_name = str(state_client.get("ClientName") or "").strip()
            county_key = _county_key_from_client_name(client_name)
            if not county_key:
                continue
            if requested_county_key and county_key != requested_county_key:
                continue
            targets.append((county_key, client_name))

        tasks = [
            _discover_municipality(
                client,
                semaphore,
                county_key,
                client_name,
                state_clients,
                state=state_code,
            )
            for county_key, client_name in targets
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        configs: dict[str, MunicodeConfig] = {}
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("%s county authority discovery task failed: %s", state_code, result)
                continue
            key, config = result
            if config is not None:
                configs[key] = config

        logger.info(
            "Discovered %d %s county Municode authorities with zoning data",
            len(configs),
            state_code,
        )
        return configs


async def discover_tx(max_concurrent: int = 5) -> dict[str, MunicodeConfig]:
    """Discover TX municipalities with zoning data on Municode."""
    return await _discover_state("TX", TEXAS_METROS, max_concurrent)


async def discover_ga(max_concurrent: int = 5) -> dict[str, MunicodeConfig]:
    """Discover GA municipalities with zoning data on Municode."""
    return await _discover_state("GA", GEORGIA_METROS, max_concurrent)


async def discover_sc(max_concurrent: int = 5) -> dict[str, MunicodeConfig]:
    """Discover SC municipalities with zoning data on Municode."""
    return await _discover_state("SC", SOUTH_CAROLINA_METROS, max_concurrent)


async def discover_ca(max_concurrent: int = 5) -> dict[str, MunicodeConfig]:
    """Discover CA municipalities (NorCal + SoCal) with zoning data on Municode."""
    norcal, socal = await asyncio.gather(
        _discover_state("CA", NORCAL_METROS, max_concurrent),
        _discover_state("CA", SOCAL_METROS, max_concurrent),
    )
    return {**norcal, **socal}


async def get_all_municode_configs(
    force_refresh: bool = False,
) -> dict[str, MunicodeConfig]:
    """Get known Municode configs, using cached discovery results.

    Runs metro municipal discovery plus county-government authority discovery
    for FL, NC, TX, GA, SC, and CA. Same-name authorities across states are
    preserved with state-prefixed aliases so callers can resolve by name + state.
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
                from plotlot.core.types import _CA_OVERRIDES

                disk_configs.update(_CA_OVERRIDES)
                _cached_configs = disk_configs
                return _cached_configs

        logger.info(
            "Running combined municipal + FL/NC/TX/GA/SC/CA county Municode auto-discovery..."
        )
        configs: dict[str, MunicodeConfig] = {}
        try:
            (
                fl_configs,
                nc_configs,
                tx_configs,
                ga_configs,
                sc_configs,
                ca_configs,
                fl_county_configs,
                nc_county_configs,
                ca_county_configs,
            ) = await asyncio.gather(
                discover_all(),
                discover_nc(),
                discover_tx(),
                discover_ga(),
                discover_sc(),
                discover_ca(),
                discover_county_authorities("FL"),
                discover_county_authorities("NC"),
                discover_county_authorities("CA"),
                return_exceptions=False,
            )
            for discovered in (
                fl_configs,
                nc_configs,
                tx_configs,
                ga_configs,
                sc_configs,
                ca_configs,
                fl_county_configs,
                nc_county_configs,
                ca_county_configs,
            ):
                _merge_configs(configs, discovered)
        except Exception as e:
            logger.error("Combined discovery failed, returning fallback configs: %s", e)
            from plotlot.core.types import _CA_OVERRIDES, _FALLBACK_CONFIGS, _NC_FALLBACK_CONFIGS

            _cached_configs = {}
            _merge_configs(_cached_configs, {**_FALLBACK_CONFIGS, **_NC_FALLBACK_CONFIGS})
            return _cached_configs

        if not configs:
            logger.warning("Discovery returned 0 results, using fallback configs")
            from plotlot.core.types import _CA_OVERRIDES, _FALLBACK_CONFIGS, _NC_FALLBACK_CONFIGS

            _cached_configs = {}
            _merge_configs(_cached_configs, {**_FALLBACK_CONFIGS, **_NC_FALLBACK_CONFIGS})
            return _cached_configs

        # Merge in fallback configs for any municipalities not discovered
        from plotlot.core.types import _CA_OVERRIDES, _FALLBACK_CONFIGS, _NC_FALLBACK_CONFIGS

        for key, fallback in {**_FALLBACK_CONFIGS, **_NC_FALLBACK_CONFIGS}.items():
            if (
                resolve_municode_config(configs, fallback.municipality, state=fallback.state)
                is None
            ):
                _merge_config(configs, key, fallback)

        # CA overrides always win — they correct wrong products from auto-discovery
        configs.update(_CA_OVERRIDES)

        _cached_configs = configs
        _write_disk_cache(configs)
        logger.info("Cached %d Municode configs", len(_cached_configs))
        return _cached_configs


async def get_municode_configs(
    force_refresh: bool = False,
) -> dict[str, MunicodeConfig]:
    """Get all known Municode configs, using cached discovery results.

    On first call, runs full discovery against the Library API.
    Subsequent calls return the cached result.

    Includes metro municipalities and FL/NC/CA county-government authorities
    that have zoning content on Municode.
    """
    return await get_all_municode_configs(force_refresh=force_refresh)
