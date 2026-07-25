"""Marin County per-city zoning resolver (point-in-polygon).

Marin's statewide/assessor parcel layer carries no zoning, so a found parcel
comes back with an empty ``zoning_code`` and the pipeline can't tell which zone
it is — it retrieves the right ordinance text but the LLM then *guesses* the
zone (e.g. it called 2307 Spanish Trail "R-3, 7 units" when the parcel is
actually RO-2, ~1 home).

Marin County publishes one ArcGIS zoning layer per incorporated city plus the
unincorporated areas, all under a single org. We intersect the parcel's lat/lng
with the matching city layer to recover the real zone. Verified 2026-06-21:
  2307 Spanish Trail Rd, Tiburon   -> RO-2   (Zoning_of_Tiburon, layer 124)
  416 Richardson St, Sausalito     -> R-2-2.5 (Zoning_of_Sausalito, layer 123)

The per-service layer id varies (Tiburon 124, Sausalito 123, Belvedere 114,
Unincorporated 0), so we discover it from the FeatureServer rather than
hardcoding it — only the org base URL and the field names are constants.
"""

from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

# Marin County's open-data ArcGIS org. Each incorporated city is published as a
# "Zoning_of_<City>" FeatureServer here. Verified 2026-06-21.
_MARIN_ZONING_ORG = "https://services6.arcgis.com/T8eS7sop5hLmgRRH/arcgis/rest/services"

# Candidate field names for the zone code / description across city layers.
_ZONE_FIELDS = ("Zoning", "ZONE", "ZONING", "ZONE_CODE")
_DESC_FIELDS = ("ZoningDescription", "ZONE_DESC", "ZONING_DESC", "Description")

_UNINCORPORATED = "Zoning_of_Unincorporated_Marin_County"

# Cache: service name -> layer id (None = service has no layers / does not exist).
_layer_id_cache: dict[str, int | None] = {}


def _service_candidates(municipality: str) -> list[str]:
    """Map a parcel/geocode municipality to candidate "Zoning_of_<City>" services.

    Handles composite CDP names ("Belvedere Tiburon" = two separate towns) and
    multi-word cities ("Mill Valley"). Point-in-polygon disambiguates — only the
    layer whose polygon contains the parcel returns a feature — so trying several
    candidates is safe. Unincorporated Marin is always the final fallback.
    """
    m = re.sub(r"\s+county$", "", municipality.strip(), flags=re.IGNORECASE).strip()

    def svc(name: str) -> str:
        return "Zoning_of_" + re.sub(r"\s+", "_", name.strip().title())

    candidates: list[str] = []
    if m:
        candidates.append(svc(m))  # full name, e.g. "Mill Valley" -> Zoning_of_Mill_Valley
        tokens = m.split()
        if len(tokens) > 1:
            # Composite CDP — try each token as its own incorporated city.
            candidates.extend(svc(t) for t in tokens)
    candidates.append(_UNINCORPORATED)

    return list(dict.fromkeys(candidates))  # de-dup, preserve order


def _first_value(attrs: dict, fields: tuple[str, ...]) -> str:
    for f in fields:
        val = attrs.get(f)
        if val is not None and str(val).strip().lower() not in ("", "none", "null", "n/a"):
            return str(val).strip()
    return ""


async def _layer_id(client: httpx.AsyncClient, service: str) -> int | None:
    """Discover (and cache) the single layer id of a Marin zoning FeatureServer."""
    if service in _layer_id_cache:
        return _layer_id_cache[service]
    lid: int | None = None
    try:
        resp = await client.get(
            f"{_MARIN_ZONING_ORG}/{service}/FeatureServer", params={"f": "json"}
        )
        resp.raise_for_status()
        layers = resp.json().get("layers") or []
        if layers:
            lid = int(layers[0]["id"])
    except Exception as exc:
        logger.debug("Marin zoning: layer discovery failed for %s: %s", service, exc)
    _layer_id_cache[service] = lid
    return lid


async def resolve_marin_zone(municipality: str, lat: float, lng: float) -> tuple[str, str]:
    """Return ``(zone_code, zone_description)`` for a Marin parcel, or ``("", "")``.

    Intersects the parcel point with each candidate city zoning layer and returns
    the first hit. Network failures degrade silently to an empty result (the
    caller keeps an empty zoning_code, same as before).
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        for service in _service_candidates(municipality):
            lid = await _layer_id(client, service)
            if lid is None:
                continue
            try:
                resp = await client.get(
                    f"{_MARIN_ZONING_ORG}/{service}/FeatureServer/{lid}/query",
                    params={
                        "geometry": f"{lng},{lat}",
                        "geometryType": "esriGeometryPoint",
                        "inSR": "4326",
                        "spatialRel": "esriSpatialRelIntersects",
                        "outFields": "*",
                        "returnGeometry": "false",
                        "f": "json",
                    },
                )
                resp.raise_for_status()
                features = resp.json().get("features") or []
            except Exception as exc:
                logger.debug("Marin zoning query failed (%s): %s", service, exc)
                continue
            if not features:
                continue
            attrs = features[0].get("attributes", {})
            code = _first_value(attrs, _ZONE_FIELDS)
            if code:
                desc = _first_value(attrs, _DESC_FIELDS)
                logger.info("Marin zoning: %r -> %s (%s)", municipality, code, service)
                return code, desc
    logger.info("Marin zoning: no zone found for %r at (%s, %s)", municipality, lat, lng)
    return "", ""
