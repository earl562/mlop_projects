"""Universal PropertyProvider — dynamic ArcGIS dataset discovery for any US county.

Replaces hardcoded per-county providers with a single provider that:
1. Checks Firestore cache for previously discovered datasets + field mappings
2. If not cached: discovers datasets via ArcGIS Hub, maps fields, caches results
3. Queries the discovered ArcGIS endpoint and maps response to PropertyRecord
"""

from __future__ import annotations

import logging

from plotlot.core.types import PropertyRecord
from plotlot.property.arcgis_utils import (
    extract_parcel_rings,
    normalize_address,
    query_arcgis,
    safe_float,
    spatial_query,
)
from plotlot.property.base import PropertyProvider
from plotlot.property.field_mapper import ACRES_TO_SQFT, SQ_METERS_TO_SQFT, map_fields
from plotlot.property.hub_discovery import discover_datasets
from plotlot.property.models import CountyCache, DatasetInfo, FieldMapping
from plotlot.property.schemas import (
    get_county_cache,
    get_field_mapping,
    save_county_cache,
    save_field_mapping,
)

logger = logging.getLogger(__name__)


class UniversalProvider(PropertyProvider):
    """PropertyProvider that works for any US county via ArcGIS Hub discovery."""

    async def lookup(
        self,
        address: str,
        county: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
        state: str = "",
    ) -> PropertyRecord | None:
        """Look up property data for any US county.

        Flow:
        1. Check Firestore cache for county datasets + field mapping
        2. If not cached: discover via Hub, generate mapping, cache
        3. Query parcel dataset (address match → spatial fallback)
        4. Query zoning dataset (spatial)
        5. Map fields to PropertyRecord
        """
        if lat is None or lng is None:
            logger.warning("UniversalProvider requires lat/lng for discovery")
            return None

        county_key = county.lower().strip()

        # Step 1: Try cache
        cache = await get_county_cache(county_key)
        parcels_ds = cache.parcels_dataset if cache else None
        zoning_ds = cache.zoning_dataset if cache else None
        field_map = cache.field_mapping if cache else None

        # Also check standalone field mapping cache
        if field_map is None:
            field_map = await get_field_mapping(county_key)

        # Step 2: Discover if not cached
        if parcels_ds is None:
            parcels_ds, zoning_ds = await discover_datasets(lat, lng, county, state)

            if parcels_ds is None:
                logger.warning("No parcel dataset found for %s County", county)
                return None

            # Generate field mapping
            field_map = await map_fields(
                source_fields=parcels_ds.fields,
                county=county,
            )

            # Cache everything
            new_cache = CountyCache(
                county_key=county_key,
                state=state,
                parcels_dataset=parcels_ds,
                zoning_dataset=zoning_ds,
                field_mapping=field_map,
            )
            await save_county_cache(new_cache)
            if field_map:
                await save_field_mapping(field_map)

        if field_map is None:
            logger.warning("No field mapping available for %s County", county)
            return None

        # Step 3: Query parcel dataset
        parcel_feature = await _query_parcel(parcels_ds, address, lat, lng, field_map)

        # Step 4: Query zoning dataset (spatial)
        zoning_code = ""
        zoning_description = ""
        if zoning_ds:
            zoning_code, zoning_description = await _query_zoning(zoning_ds, lat, lng)

        # Step 5: Build PropertyRecord
        record = _build_property_record(
            parcel_feature, field_map, county, zoning_code, zoning_description
        )
        if record:
            record.lat = lat
            record.lng = lng
            # Pass dynamic zoning layer URL for frontend map
            if zoning_ds:
                record.zoning_layer_url = f"{zoning_ds.url}/{zoning_ds.layer_id}"

        return record


async def _query_parcel(
    dataset: DatasetInfo,
    address: str,
    lat: float,
    lng: float,
    field_map: FieldMapping,
) -> dict | None:
    """Query parcel dataset — try address match first, fall back to spatial."""
    query_url = f"{dataset.url}/{dataset.layer_id}/query"

    # Find the address field name from field mapping
    addr_field = None
    for src_field, tgt_field in field_map.mappings.items():
        if tgt_field == "address":
            addr_field = src_field
            break

    # Try address match first
    if addr_field:
        normalized = normalize_address(address)
        where = f"UPPER({addr_field}) LIKE '%{normalized}%'"
        try:
            features = await query_arcgis(query_url, where=where, extra_params={"outSR": "4326"})
            if features:
                return features[0]
        except Exception:
            logger.debug("Address query failed, trying spatial", exc_info=True)

    # Spatial fallback
    try:
        features = await spatial_query(query_url, lat, lng)
        if features:
            return features[0]
    except Exception:
        logger.warning("Spatial parcel query failed for (%.4f, %.4f)", lat, lng, exc_info=True)

    return None


async def _query_zoning(
    dataset: DatasetInfo,
    lat: float,
    lng: float,
) -> tuple[str, str]:
    """Spatial query on zoning dataset to get zoning code."""
    query_url = f"{dataset.url}/{dataset.layer_id}/query"

    try:
        features = await spatial_query(query_url, lat, lng)
        if not features:
            return "", ""

        attrs = features[0].get("attributes", {})

        # Try common zoning field names
        code = ""
        desc = ""
        for key, val in attrs.items():
            key_upper = key.upper()
            if not code and any(
                kw in key_upper for kw in ("ZONE_CODE", "ZONING_CODE", "ZONE", "ZONING")
            ):
                code = str(val) if val else ""
            if not desc and any(
                kw in key_upper for kw in ("ZONE_DESC", "ZONING_DESC", "ZONE_LABEL", "ZONE_NAME")
            ):
                desc = str(val) if val else ""

        return code, desc
    except Exception:
        logger.warning("Zoning query failed at (%.4f, %.4f)", lat, lng, exc_info=True)
        return "", ""


def _build_property_record(
    feature: dict | None,
    field_map: FieldMapping,
    county: str,
    zoning_code: str = "",
    zoning_description: str = "",
) -> PropertyRecord | None:
    """Build PropertyRecord from ArcGIS feature using field mapping."""
    if feature is None:
        return None

    attrs = feature.get("attributes", {})
    record = PropertyRecord(county=county)

    # Apply field mappings
    for src_field, tgt_field in field_map.mappings.items():
        raw_val = attrs.get(src_field)
        if raw_val is None:
            continue

        # Apply unit conversions
        if src_field in field_map.unit_conversions:
            conversion = field_map.unit_conversions[src_field]
            numeric_val = safe_float(raw_val)
            if conversion == "acres_to_sqft":
                raw_val = numeric_val * ACRES_TO_SQFT
            elif conversion == "sq_meters_to_sqft":
                raw_val = numeric_val * SQ_METERS_TO_SQFT

        _set_record_field(record, tgt_field, raw_val)

    # Override with spatial zoning if available
    if zoning_code:
        record.zoning_code = zoning_code
    if zoning_description:
        record.zoning_description = zoning_description

    # Extract parcel geometry
    record.parcel_geometry = extract_parcel_rings(feature)

    return record


def _set_record_field(record: PropertyRecord, field: str, value: object) -> None:
    """Set a PropertyRecord field with type coercion."""
    if not hasattr(record, field):
        return

    if field in (
        "lot_size_sqft",
        "building_area_sqft",
        "living_area_sqft",
        "assessed_value",
        "market_value",
        "last_sale_price",
    ):
        setattr(record, field, safe_float(value))
    elif field in ("bedrooms", "half_baths", "floors", "living_units", "year_built"):
        try:
            setattr(record, field, int(safe_float(value)))
        except (ValueError, TypeError):
            pass
    elif field == "bathrooms":
        setattr(record, field, safe_float(value))
    else:
        setattr(record, field, str(value).strip() if value else "")
