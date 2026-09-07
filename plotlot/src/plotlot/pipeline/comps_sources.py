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
# Verified live 2026-06-26 (AGENTS.md rule #11: verify, don't assert).
# These replace RentCast (not free) and the noisy generic Hub keyword discovery
# for the three South FL counties. Each is the county property appraiser's own
# ArcGIS layer carrying arms-length sale price + sale date.
#
# To add a market: probe the county's ArcGIS server for a parcels-or-sales layer
# with SALE_PRICE/SALE_DATE fields, then add one entry here.
_SALES_SOURCES: dict[tuple[str, str], SalesSource] = {
    # Miami-Dade Property Appraiser — PaGISView parcels layer 0.
    # Sale price + date ride directly on the parcel feature.
    # Verified fields: PRICE_1, DATEOFSALE_UTC (+ LOT_SIZE, USE_CODE, etc.).
    ("FL", "miami-dade"): SalesSource(
        layer_url=(
            "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/ArcGIS/rest/services"
            "/PaGISView_gdb/FeatureServer/0"
        ),
        fields=(
            "FOLIO",
            "PRICE_1",
            "DATEOFSALE_UTC",
            "LOT_SIZE",
            "USE_CODE",
            "BEDROOMS",
            "BATHROOMS",
            "LIVING_AREA",
            "YEAR_BUILT",
            "ZIP_CODE",
            "MUNICIPALITY",
        ),
        source="Miami-Dade County Property Appraiser PaGISView, verified 2026-06-26",
        note="Sale price + date on the parcel feature; 0-3 mi radius query.",
    ),
    # Broward County Property Appraiser (BCPA) — 2025 Sales layer (MapServer 18).
    # Separate sales layer (year-bucketed); parcel layer 36 lacks sale price.
    # Verified fields: SALE_AMOUNT, SALE_DATE, FOLIO_NUMBER (DB-qualified names).
    ("FL", "broward"): SalesSource(
        layer_url=(
            "https://gisweb-adapters.bcpa.net/arcgis/rest/services/BCPA_EXTERNAL_JAN26/MapServer/18"
        ),
        fields=(
            "SQLGIS02.DATALAYER.Parcel_Polygons.FOLIO",
            "SQLGIS02.DATALAYER.Parcel_Polygons.PARCEL_TYPE",
            "SQLGIS02.dbo.BCPA_SALES.FOLIO_NUMBER",
            "SQLGIS02.dbo.BCPA_SALES.SALE_DATE",
            "SQLGIS02.dbo.BCPA_SALES.SALE_AMOUNT",
            "SQLGIS02.dbo.BCPA_SALES.SALE_VER",
            "SQLGIS02.dbo.BCPA_SALES.SALE_YEAR",
        ),
        source="Broward County Property Appraiser (BCPA) 2025 Sales, verified 2026-06-26",
        note="Year-bucketed sales layer; map to sibling years (17=2026, 19=2024) for broader recency window.",
    ),
    # Palm Beach County Property Appraiser — Parcels layer 0.
    # Sale price + date ride directly on the parcel feature.
    # Verified live 2026-06-26 (field names reconciled against the actual layer schema,
    # not the metadata listing — the listing and live schema diverge for this layer).
    # Actual fields: PARCEL_NUMBER, PRICE, SALE_DATE, MONTHS_SINCE_SALE, ACRES,
    # PROPERTY_USE, YEAR_ADDED, SALEKEY.
    ("FL", "palm beach"): SalesSource(
        layer_url=(
            "https://services1.arcgis.com/ZWOoUZbtaYePLlPw/arcgis/rest/services"
            "/Parcels_and_Property_Details_WebMercator/FeatureServer/0"
        ),
        fields=(
            "PARCEL_NUMBER",
            "PRICE",
            "SALE_DATE",
            "MONTHS_SINCE_SALE",
            "SALEKEY",
            "PROPERTY_USE",
            "ACRES",
            "YEAR_ADDED",
            "AG_USE_VAL",
        ),
        source="Palm Beach County Property Appraiser Parcels, verified 2026-06-26",
        note="Sale price + date on the parcel feature; 0-3 mi radius query.",
    ),
}


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
