"""Genuine CEQA data from CEQAnet — fetch real filings and match them to a parcel.

Replaces the old LLM-suggested "leads" with REAL documents from the State
Clearinghouse. CEQAnet (``ceqanet.lci.ca.gov``) has no JSON/REST API, but its
search exposes a **CSV export** (``/Search?County=..&City=..&OutputFormat=CSV``,
55 columns) for any result set under 10k rows — that is the machine-readable
source used here.

Two-tier matching (parcels have no clean CEQA key, so this is best-effort):

* **Tier 1 — strong** (``ceqa_documents``, may drive the timeline + confidence):
  APN exact match, the parcel's exact street address found in the CEQA record,
  or coordinates within ``STRONG_RADIUS_M`` of the parcel.
* **Tier 2 — candidate** (``ceqa_candidates``, display-only, never drives):
  nearby coordinates, a partial address reference, strong project-title or
  owner/contact similarity, or a matching ZIP. Pure same-city with no secondary
  signal is intentionally dropped — the false-positive cost of attributing the
  wrong filing to a parcel is far higher than a miss.

All network calls degrade gracefully — any failure returns empty, never raises.
The matcher is pure/deterministic (no I/O) and unit-tested without the network.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from dataclasses import replace
from difflib import SequenceMatcher
from math import asin, cos, radians, sin, sqrt

import httpx

from plotlot.core.types import CEQADocument

logger = logging.getLogger(__name__)

_CEQANET_SEARCH_URL = "https://ceqanet.lci.ca.gov/Search"

# Matching thresholds (metres / similarity ratio). Conservative by design.
STRONG_RADIUS_M = 150.0
CANDIDATE_RADIUS_M = 2000.0
TITLE_SIMILARITY_THRESHOLD = 0.72
MAX_CANDIDATES = 8

# Document-type review-stage priority for per-project (per-SCH) aggregation.
# A determination/exemption means CEQA is effectively resolved for that action;
# an EIR/NOP/MND in progress is what actually carries timeline risk.
_RESOLVED_TYPES = {"NOD", "NOE"}
_ACTIVE_EIR_TYPES = {"EIR", "NOP", "EA"}

_STREET_SUFFIXES = {
    "st",
    "street",
    "ave",
    "avenue",
    "blvd",
    "boulevard",
    "dr",
    "drive",
    "rd",
    "road",
    "ln",
    "lane",
    "way",
    "ct",
    "court",
    "pl",
    "place",
    "ter",
    "terrace",
    "cir",
    "circle",
    "hwy",
    "highway",
    "pkwy",
    "parkway",
    "trl",
    "trail",
    "sq",
    "square",
    "row",
    "walk",
    "path",
    "real",
}

# One DMS coordinate, e.g. ``32°42'8"N`` or ``117°10'46.1"W`` (seconds optional).
# The degree class tolerates a mis-decoded byte (``�``) defensively, though
# ``_decode_csv`` should already have recovered the real ``°``.
_DMS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[°º�]\s*"
    r"(\d+(?:\.\d+)?)\s*['’′]\s*"
    r"(?:(\d+(?:\.\d+)?)\s*[\"”″])?\s*"
    r"([NSEW])",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Geometry / identity helpers (pure)
# ---------------------------------------------------------------------------


def _dms_to_decimal(raw: str) -> tuple[float, float] | None:
    """Parse CEQAnet's ``DD°MM'SS"N DDD°MM'SS"W`` coordinate into (lat, lng).

    Falls back to a plain ``lat, lng`` decimal pair. Returns None when neither a
    latitude nor a longitude can be recovered.
    """
    if not raw:
        return None
    lat = lng = None
    for deg, minute, sec, hemi in _DMS_RE.findall(raw):
        val = float(deg) + float(minute) / 60.0 + (float(sec) / 3600.0 if sec else 0.0)
        hemi = hemi.upper()
        if hemi in ("S", "W"):
            val = -val
        if hemi in ("N", "S"):
            lat = val
        else:
            lng = val
    if lat is not None and lng is not None:
        return round(lat, 6), round(lng, 6)
    # A DMS-style string (has compass letters) that failed to parse must NOT fall
    # through to the decimal path — that would misread the seconds as lat/lng.
    if re.search(r"[NSEW]", raw, re.IGNORECASE):
        return None
    # Fallback: a plain decimal "lat, lng" pair.
    dec = re.findall(r"-?\d{1,3}\.\d+", raw)
    if len(dec) >= 2:
        return float(dec[0]), float(dec[1])
    return None


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    earth_r = 6_371_000.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lng2 - lng1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * earth_r * asin(sqrt(a))


def _normalize_apn(raw: str) -> str:
    """Reduce a parcel string to comparable digits, or "" if it is not an APN.

    ``760-057-00-02`` → ``7600570002``; free text like
    ``Unparcelled Public Trust Lands`` → "" (rejected).
    """
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    return digits if len(digits) >= 8 else ""


def _address_tokens(address: str) -> tuple[str, str]:
    """Split a street address into (house_number, street_core_name).

    ``"1233 Hueneme St, San Diego, CA"`` → ``("1233", "hueneme")``.
    """
    if not address:
        return "", ""
    first = address.split(",")[0].strip().lower()
    toks = re.findall(r"[a-z0-9]+", first)
    number = toks[0] if toks and toks[0].isdigit() else ""
    name_toks = [t for t in toks[1:] if t not in _STREET_SUFFIXES and not t.isdigit()]
    return number, " ".join(name_toks)


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ---------------------------------------------------------------------------
# CEQAnet CSV client (network — graceful)
# ---------------------------------------------------------------------------


async def fetch_ceqa_documents(
    county: str,
    city: str,
    *,
    timeout: float = 20.0,
) -> list[CEQADocument]:
    """Fetch CEQA filings for a city from the CEQAnet CSV export.

    Returns an empty list on any failure, including when CEQAnet declines the
    CSV (results over 10k → an HTML page instead of CSV). Never raises.
    """
    if not county or not city:
        return []
    params = {"County": county, "City": city, "OutputFormat": "CSV"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(_CEQANET_SEARCH_URL, params=params)
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("CEQAnet query failed for %s, %s: %s", city, county, exc)
        return []

    if "csv" not in resp.headers.get("content-type", "").lower():
        # Over the 10k CSV cap → CEQAnet returns the HTML results page instead.
        logger.info("CEQAnet returned non-CSV (likely >10k results) for %s, %s", city, county)
        return []

    try:
        return _parse_ceqa_csv(_decode_csv(resp.content))
    except Exception as exc:  # malformed CSV — degrade, do not raise
        logger.warning("CEQAnet CSV parse failed for %s, %s: %s", city, county, exc)
        return []


def _decode_csv(content: bytes) -> str:
    """Decode the CEQAnet CSV bytes — it is cp1252, not UTF-8, so ``°`` etc.

    survive (httpx's ``.text`` mis-decodes the degree symbol to ``�``).
    """
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _parse_ceqa_csv(text: str) -> list[CEQADocument]:
    """Parse the 55-column CEQAnet CSV export into CEQADocument rows."""
    docs: list[CEQADocument] = []
    for row in csv.DictReader(io.StringIO(text)):
        coords_raw = (row.get("Location Coordinates") or "").strip()
        latlng = _dms_to_decimal(coords_raw)
        docs.append(
            CEQADocument(
                doc_type=(row.get("Document Type") or "").strip() or "Other",
                filed_date=(row.get("Received") or "").strip(),
                description=(row.get("Document Description") or "").strip(),
                lead_agency=(row.get("Lead Agency Name") or "").strip(),
                source_url=(row.get("Document Portal URL") or "").strip(),
                sch_number=(row.get("SCH Number") or "").strip(),
                title=(row.get("Document Title") or row.get("Project Title") or "").strip(),
                coordinates=coords_raw,
                lat=latlng[0] if latlng else None,
                lng=latlng[1] if latlng else None,
                parcel_number=(row.get("Location Parcel Number") or "").strip(),
                cross_streets=(row.get("Location Cross Streets") or "").strip(),
                zip_code=(row.get("Location Zip Code") or "").strip(),
                cities=(row.get("Cities") or "").strip(),
                counties=(row.get("Counties") or "").strip(),
                contact_name=(row.get("Contact Full Name") or "").strip(),
            )
        )
    return docs


# ---------------------------------------------------------------------------
# Two-tier matcher (pure / deterministic)
# ---------------------------------------------------------------------------


def _classify(
    d: CEQADocument,
    *,
    napn: str,
    parcel_lat: float | None,
    parcel_lng: float | None,
    house_no: str,
    street_core: str,
    parcel_zip: str,
    owner: str,
) -> tuple[str, str, float]:
    """Return (tier, basis, confidence) for one document. tier in {strong,candidate,}."""
    # Distance, if both ends are geocoded.
    dist: float | None = None
    if (
        parcel_lat is not None
        and parcel_lng is not None
        and d.lat is not None
        and d.lng is not None
    ):
        dist = _haversine_m(parcel_lat, parcel_lng, d.lat, d.lng)
        d.distance_m = round(dist, 1)

    hay = f"{d.title} {d.cross_streets} {d.description}".lower()
    name_hit = bool(street_core) and street_core in hay
    num_hit = bool(house_no) and re.search(rf"\b{re.escape(house_no)}\b", hay) is not None

    # --- Tier 1: strong ---
    if napn and _normalize_apn(d.parcel_number) == napn:
        return "strong", f"APN {d.parcel_number} exact match", 1.0
    if name_hit and num_hit:
        return "strong", f"address '{house_no} {street_core}' found in CEQA record", 0.95
    if dist is not None and dist <= STRONG_RADIUS_M:
        conf = round(0.85 + 0.15 * (1 - dist / STRONG_RADIUS_M), 3)
        return "strong", f"{int(dist)} m from parcel", conf

    # --- Tier 2: candidate (requires a real secondary signal) ---
    if dist is not None and dist <= CANDIDATE_RADIUS_M:
        conf = round(0.20 + 0.40 * (1 - dist / CANDIDATE_RADIUS_M), 3)
        return "candidate", f"{int(dist)} m from parcel (nearby)", conf
    if name_hit:
        return "candidate", f"street '{street_core}' referenced in CEQA record", 0.50
    if (
        owner
        and d.contact_name
        and _similarity(owner, d.contact_name) >= TITLE_SIMILARITY_THRESHOLD
    ):
        return "candidate", f"contact '{d.contact_name}' resembles owner", 0.40
    if street_core and _similarity(street_core, d.title) >= TITLE_SIMILARITY_THRESHOLD:
        return "candidate", "project title resembles the parcel", 0.40
    if parcel_zip and d.zip_code.strip()[:5] == parcel_zip:
        return "candidate", f"same ZIP ({parcel_zip})", 0.30
    return "", "", 0.0


def _aggregate_by_sch(rows: list[CEQADocument]) -> list[CEQADocument]:
    """Collapse multiple notices of one project (shared SCH) into one record.

    Picks the highest-confidence row as representative and infers a review
    ``status`` from all of the project's document types (resolved vs in-progress).
    """
    by_sch: dict[str, list[CEQADocument]] = {}
    for d in rows:
        by_sch.setdefault(d.sch_number or d.source_url or id(d), []).append(d)  # type: ignore[arg-type]

    out: list[CEQADocument] = []
    for group in by_sch.values():
        rep = replace(max(group, key=lambda g: g.match_confidence))
        types = {g.doc_type.upper() for g in group}
        if types & _RESOLVED_TYPES:
            rep.status = "completed" if "NOD" in types else "exempt"
        elif types & _ACTIVE_EIR_TYPES:
            rep.status, rep.doc_type = "in_progress", "EIR"
        elif "MND" in types:
            rep.status, rep.doc_type = "in_progress", "MND"
        elif "ND" in types:
            rep.status, rep.doc_type = "in_progress", "ND"
        out.append(rep)
    out.sort(key=lambda d: d.match_confidence, reverse=True)
    return out


def match_ceqa_documents(
    docs: list[CEQADocument],
    *,
    parcel_apn: str = "",
    parcel_lat: float | None = None,
    parcel_lng: float | None = None,
    parcel_zip: str = "",
    parcel_address: str = "",
    owner: str = "",
    max_candidates: int = MAX_CANDIDATES,
) -> tuple[list[CEQADocument], list[CEQADocument]]:
    """Classify CEQA documents against a parcel into (strong, candidate) lists.

    Pure and deterministic — no network. Every input ``docs`` row is already
    same-city (the fetch is city-scoped), so same-city alone is NOT a candidate;
    a secondary signal is required. Both lists are deduped per project (SCH);
    candidates are sorted by confidence and capped at ``max_candidates``.
    """
    napn = _normalize_apn(parcel_apn)
    house_no, street_core = _address_tokens(parcel_address)
    pzip = (parcel_zip or "").strip()[:5]
    owner_l = (owner or "").strip()

    strong_rows: list[CEQADocument] = []
    candidate_rows: list[CEQADocument] = []
    for d in docs:
        tier, basis, conf = _classify(
            d,
            napn=napn,
            parcel_lat=parcel_lat,
            parcel_lng=parcel_lng,
            house_no=house_no,
            street_core=street_core,
            parcel_zip=pzip,
            owner=owner_l,
        )
        if not tier:
            continue
        d.match_tier = tier
        d.match_basis = basis
        d.match_confidence = conf
        d.on_parcel = tier == "strong"
        (strong_rows if tier == "strong" else candidate_rows).append(d)

    strong = _aggregate_by_sch(strong_rows)
    candidates = _aggregate_by_sch(candidate_rows)
    # A project that qualifies as strong must never also appear as a candidate.
    strong_schs = {d.sch_number for d in strong if d.sch_number}
    candidates = [d for d in candidates if d.sch_number not in strong_schs]
    return strong, candidates[:max_candidates]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def find_parcel_ceqa(
    *,
    county: str,
    city: str,
    parcel_apn: str = "",
    parcel_lat: float | None = None,
    parcel_lng: float | None = None,
    parcel_zip: str = "",
    parcel_address: str = "",
    owner: str = "",
    timeout: float = 20.0,
) -> tuple[list[CEQADocument], list[CEQADocument]]:
    """Fetch CEQAnet filings for the city and match them to the parcel.

    Returns ``(strong, candidates)``. Empty on any failure (graceful).
    """
    docs = await fetch_ceqa_documents(county, city, timeout=timeout)
    if not docs:
        return [], []
    return match_ceqa_documents(
        docs,
        parcel_apn=parcel_apn,
        parcel_lat=parcel_lat,
        parcel_lng=parcel_lng,
        parcel_zip=parcel_zip,
        parcel_address=parcel_address,
        owner=owner,
    )
