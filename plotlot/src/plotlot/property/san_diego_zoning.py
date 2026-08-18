"""San Diego County per-city zoning resolver (point-in-polygon).

**Why this exists.** A dimensional standard is keyed on
``(municipality, district_code)``, but only City of San Diego parcels came back
carrying a ``district_code`` — ``california.py``'s ``"san diego"`` county config
has a single per-county ``zoning_url`` slot, and it points at the *City* of San
Diego's citywide layer. Every other SD city publishes its own layer, so their
parcels resolved with an empty ``zoning_code``, the standards join missed, and
density fell through to the LLM on every run. Validated districts sat in the
database unreachable.

This is a **curated** registry, not auto-discovery. Auto-discovery returns
overlay layers ahead of base districts and misses known-good services; each
entry below is added only after it has been verified end to end.

**A wrong zone code is worse than no zone code.** It silently selects another
district's standard and produces a confidently wrong unit count — the exact
failure the deterministic path was built to remove. So matching is
``EXACT``-only, and three code shapes are refused outright. All three are real
values on Escondido's live layer, and all three would be accepted by a
substring match:

* ``PZ-*`` — *pre-zoning* for land not yet annexed. ``PZ-R-1-10`` (56 polygons)
  contains ``R-1-10``, but the parcel is under **county** authority today, not
  the city's. Applying the city's standard would answer for the wrong
  jurisdiction.
* ``A/B`` composites — *split-zoned* parcels carrying two districts.
  ``R-1-10/RE-20`` contains ``R-1-10``; picking either half is a guess. 142
  polygons.
* ``COUNTY`` — explicitly outside city zoning authority. 8,747 polygons, the
  single largest value on the layer.

Codes with no ordinance equivalent (``S-P`` Specific Plan, ``PD-*`` Planned
Development) need no special-casing: they simply do not join to a stored
district, and ``get_dimensional_standard`` returning ``None`` is the correct,
honest outcome — the pipeline already marks such a count provisional.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CityZoning:
    """A verified per-city zoning layer.

    ``verified_at``/``verified_code`` record the parcel this entry was proven
    against, so a later reader can re-run the check rather than trust the entry.
    """

    url: str
    zone_field: str
    verified_at: str
    verified_code: str


# Only cities whose layer has passed the full verification recipe belong here.
# See docs/plans/per-city-zoning-registry.md for the five steps.
_SD_CITY_ZONING: dict[str, CityZoning] = {
    "escondido": CityZoning(
        # Layer 0 is the base district layer. (Layer 3 is "Split Zoning" — a
        # separate overlay, deliberately not consulted; a parcel needing it is
        # one we refuse to resolve anyway.)
        url=(
            "https://services2.arcgis.com/eJcVbjTyyZIzZ5Ye/arcgis/rest/services"
            "/Zoning/FeatureServer/0"
        ),
        zone_field="ZONING",
        # Verified 2026-08-13 through the production spatial_query helper on six
        # residential parcels (2 each R-1-6 / R-1-7 / R-1-10), 6/6 exact.
        verified_at="APN 2255935000 (33.145686, -117.049988)",
        verified_code="R-1-6",
    ),
    "oceanside": CityZoning(
        # Layer 11 is ZONING (the base districts). Not layer 12 — that is
        # "Preserve Planning Zones"; the coastal boundary is layer 2.
        url=(
            "https://gis.oceansideca.org/gis/rest/services/WebService/Planning_Hub/FeatureServer/11"
        ),
        # `Zone_Code` is the bare district. `Zone_Code_Print` is the same code
        # with its overlay appended (RS -> "RS-SP", RE-B -> "RE-B-EQ") and would
        # miss the standards join on every overlaid parcel — which is most of
        # them. Read the bare field; overlays live in Overlay1/Overlay2.
        zone_field="Zone_Code",
        # Verified 2026-08-13 through the production spatial_query helper on
        # RS / RM-A / RE-B / RH polygons, 4/4 exact. All 8 stored Oceanside
        # districts appear verbatim; they cover 12,514 of 32,002 zoned acres.
        verified_at="RE-B polygon, Zone_Code_Print='RE-B-EQ'",
        verified_code="RE-B",
    ),
}


def _is_usable_district(code: str) -> bool:
    """Whether a raw GIS zone code may be used as a district key.

    Refuses the three shapes documented in the module docstring. Everything else
    is passed through unchanged — a code with no stored standard simply misses
    the join, which is already handled honestly downstream.
    """
    normalized = code.strip().upper()
    if not normalized:
        return False
    if normalized == "COUNTY":
        return False
    if normalized.startswith("PZ-"):
        return False
    if "/" in normalized:
        return False
    return True


def _rejection_reason(code: str) -> str:
    normalized = code.strip().upper()
    if normalized == "COUNTY":
        return "parcel is under county zoning authority, not the city's"
    if normalized.startswith("PZ-"):
        return "pre-zoned for annexation; county authority applies today"
    if "/" in normalized:
        return "split-zoned across two districts; neither may be assumed"
    return "empty zone code"


async def _query_city(city: str, entry: CityZoning, lat: float, lng: float) -> str | None:
    """Return the usable district code from one city's layer, or None."""
    try:
        from plotlot.property.arcgis_utils import spatial_query

        features = await spatial_query(f"{entry.url}/query", lat, lng)
    except Exception as exc:  # noqa: BLE001 — best-effort enrichment
        logger.warning("SD zoning lookup failed for %s: %s", city, exc)
        return None

    if not features:
        # Either the parcel is in another city, or it fell in a gap — civic
        # buildings and street-centerline geocodes land outside zoning polygons.
        return None

    code = str(features[0].get("attributes", {}).get(entry.zone_field) or "").strip()
    if not _is_usable_district(code):
        logger.info(
            "Refusing %s zone code %r at (%s, %s): %s",
            city,
            code,
            lat,
            lng,
            _rejection_reason(code),
        )
        return None
    return code


async def resolve_san_diego_zone(
    municipality: str,
    lat: float,
    lng: float,
) -> tuple[str | None, str | None]:
    """Resolve a San Diego County parcel's zoning district from its city layer.

    **The municipality name is a hint, not a key.** San Diego County parcels come
    from the CA statewide layer, whose ``SITE_CITY`` is blank for them, so by the
    time this runs ``record.municipality`` is usually ``""`` — keying on it alone
    meant this never fired at all. Geometry is the reliable discriminator: city
    zoning layers do not overlap, so only the layer covering the parcel returns a
    feature. A recognised name takes the single-request fast path; anything else
    fans out across the registry.

    Returns ``(code, None)``, or ``(None, None)`` when nothing matched, the code
    was refused, or — deliberately — when two cities both claimed the point. The
    description slot is always ``None`` (these layers publish only a code and an
    APN), but the pair matches ``resolve_marin_zone``'s shape at the call site.

    Never raises: a layer outage must leave the parcel exactly as it was rather
    than fail the whole lookup.
    """
    if not _SD_CITY_ZONING:
        return None, None

    entry = _SD_CITY_ZONING.get(municipality.strip().lower())
    if entry is not None:
        return await _query_city(municipality.strip().lower(), entry, lat, lng), None

    import asyncio

    cities = list(_SD_CITY_ZONING.items())
    results = await asyncio.gather(
        *(_query_city(city, cfg, lat, lng) for city, cfg in cities),
        return_exceptions=False,
    )
    hits = [(city, code) for (city, _), code in zip(cities, results, strict=True) if code]

    if not hits:
        return None, None
    if len(hits) > 1:
        # Incorporated cities do not overlap, so this means a registry entry
        # points at a regional layer rather than one city's. Refuse rather than
        # pick — a wrong district silently selects another city's standard.
        logger.warning(
            "Ambiguous SD zoning at (%s, %s): %s — refusing to choose",
            lat,
            lng,
            ", ".join(f"{c}={z}" for c, z in hits),
        )
        return None, None

    return hits[0][1], None
