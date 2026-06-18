"""Curated comparable-sales source registry.

``find_comparables`` needs a sales dataset (a feature-layer URL + its field
names) for the subject's county. The default path searches ArcGIS Hub by
keyword, which works for many Florida counties but returns nothing for markets
(e.g. San Diego) that don't publish an open arms-length-sales layer.

This registry lets us curate a known-good source per ``(state, county)`` so the
resolver in ``find_comparables`` becomes:

    curated registry  →  ArcGIS Hub keyword discovery (fallback)

**Generalization is the whole point.** Adding a new market is *one dict entry*,
not a rewrite — the same field-mapping and spatial-query code downstream is
reused unchanged because a curated source returns the exact ``(layer_url,
field_names)`` shape the Hub discovery already produces. This mirrors the parcel
provider registry in ``property/california.py`` (``_COUNTY_CONFIG``).

A market whose only reliable sale-price data is behind a paid API (common in CA,
where counties rarely expose arms-length prices via open GIS) is supported by
the same seam: register a ``provider`` callable instead of a static layer.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# A pluggable async source: given (lat, lng, radius_miles) it returns the same
# (layer_url, field_names) tuple find_comparables expects — or None. Lets a paid
# data API (ATTOM/Regrid/CoreLogic) drop in per market without touching comps.py.
SalesProvider = Callable[[float, float, float], Awaitable["tuple[str, list[str]] | None"]]


@dataclass(frozen=True)
class SalesSource:
    """A curated comparable-sales dataset for one ``(state, county)``.

    ``layer_url`` + ``fields`` is the common case: a public ArcGIS feature layer
    whose field names are known. ``provider`` is the escape hatch for markets
    behind a paid API. Exactly one of the two should be set.
    """

    layer_url: str = ""
    # The layer's field names (the comps field-mapper picks price/date/lot/etc.
    # from these). Captured at curation time so no extra metadata round-trip is
    # needed; confirm them with ``diag_sd_data.py`` against the live service.
    fields: tuple[str, ...] = ()
    provider: SalesProvider | None = None
    source: str = ""  # provenance / citation (who published the layer, when verified)
    note: str = ""


def _norm_county(county: str) -> str:
    """Lowercase + strip a trailing ' county' (matches cost_model / providers)."""
    c = (county or "").strip().lower()
    return c[: -len(" county")].strip() if c.endswith(" county") else c


# (state_upper, county_normalized) -> SalesSource.
#
# To add a market: confirm the layer exposes arms-length sale price + date fields
# (run ``diag_sd_data.py``), then add one entry here. Example shape:
#
#   ("CA", "san diego"): SalesSource(
#       layer_url="https://<host>/arcgis/rest/services/<Sales>/FeatureServer/0",
#       fields=("SALE_PRICE", "SALE_DATE", "LOT_SIZE", "USE_CODE", ...),
#       source="SanGIS/SANDAG, verified YYYY-MM",
#   ),
#
# San Diego is intentionally left unpopulated until a live-verified sale-price
# source is confirmed — CA counties rarely expose arms-length prices via open
# GIS, so the real source here may be a paid ``provider`` (see SalesProvider).
_SALES_SOURCES: dict[tuple[str, str], SalesSource] = {}


def register_sales_source(state: str, county: str, source: SalesSource) -> None:
    """Register (or override) a curated sales source for a market.

    Lets deployments wire a paid-API provider at startup without editing this
    module — e.g. ``register_sales_source("CA", "San Diego", SalesSource(provider=attom))``.
    """
    _SALES_SOURCES[((state or "").strip().upper(), _norm_county(county))] = source


def get_sales_source(state: str, county: str) -> SalesSource | None:
    """Return the curated sales source for ``(state, county)``, or None."""
    return _SALES_SOURCES.get(((state or "").strip().upper(), _norm_county(county)))


async def resolve_sales_dataset(
    state: str,
    county: str,
    lat: float,
    lng: float,
    radius_miles: float,
) -> tuple[str, list[str]] | None:
    """Resolve a sales dataset for the subject, preferring a curated source.

    Returns ``(layer_url, field_names)`` (the shape ``find_comparables`` consumes)
    or None when neither a curated source nor the registered provider yields one.
    The caller falls back to ArcGIS Hub discovery when this returns None.
    """
    src = get_sales_source(state, county)
    if src is None:
        return None
    if src.provider is not None:
        try:
            return await src.provider(lat, lng, radius_miles)
        except Exception as exc:  # noqa: BLE001 — provider failure → Hub fallback
            logger.warning("Sales provider for %s, %s failed: %s", county, state, exc)
            return None
    if src.layer_url and src.fields:
        return src.layer_url, list(src.fields)
    return None
