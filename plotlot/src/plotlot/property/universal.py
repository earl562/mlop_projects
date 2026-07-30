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
from plotlot.property.hub_discovery import (
    discover_datasets,
    known_county_layer_identity,
)
from plotlot.property.models import CountyCache, DatasetInfo, FieldMapping
from plotlot.property.registry import get_registered_provider
from plotlot.property.schemas import (
    get_county_cache,
    get_field_mapping,
    save_county_cache,
    save_field_mapping,
)

logger = logging.getLogger(__name__)


def _matches_identity(
    dataset: DatasetInfo | None,
    identity: tuple[str, int] | None,
) -> bool:
    if identity is None:
        return True
    if dataset is None:
        return False
    url, layer_id = identity
    return dataset.url.rstrip("/") == url.rstrip("/") and dataset.layer_id == layer_id


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
        authoritative_provider = get_registered_provider(county)
        if authoritative_provider is not None and authoritative_provider is not self:
            return await authoritative_provider.lookup(
                address,
                county,
                lat=lat,
                lng=lng,
                state=state,
            )

        if lat is None or lng is None:
            logger.warning("UniversalProvider requires lat/lng for discovery")
            return None

        county_key = county.lower().strip()

        # Step 1: Try cache
        cache = await get_county_cache(county_key)
        parcels_ds = cache.parcels_dataset if cache else None
        zoning_ds = cache.zoning_dataset if cache else None
        field_map = cache.field_mapping if cache else None
        pinned_parcels = known_county_layer_identity(county, state, "parcels")
        pinned_zoning = known_county_layer_identity(county, state, "zoning")
        refresh_required = not _matches_identity(
            parcels_ds, pinned_parcels
        ) or not _matches_identity(zoning_ds, pinned_zoning)

        # Also check standalone field mapping cache
        if field_map is None and not refresh_required:
            field_map = await get_field_mapping(county_key)

        # Step 2: Discover if not cached
        if parcels_ds is None or refresh_required:
            parcels_ds, zoning_ds = await discover_datasets(lat, lng, county, state)

            if parcels_ds is None:
                logger.warning("No parcel dataset found for %s County", county)
                return None

            # Generate field mapping
            field_map = await map_fields(
                source_fields=parcels_ds.fields,
                county=county,
            )

            authoritative_resolution_complete = _matches_identity(
                parcels_ds, pinned_parcels
            ) and _matches_identity(zoning_ds, pinned_zoning)
            if authoritative_resolution_complete:
                new_cache = CountyCache(
                    county_key=county_key,
                    state=state,
                    parcels_dataset=parcels_ds,
                    zoning_dataset=zoning_ds,
                    field_mapping=field_map,
                )
                await save_county_cache(new_cache)
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
            parcel_feature,
            field_map,
            county,
            zoning_code,
            zoning_description,
            clear_parcel_zoning=pinned_zoning is not None,
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

        code = ""
        desc = ""
        for key in ("ZONE_CODE", "ZONING_CODE", "ZONE", "ZONING", "FCODE"):
            value = attrs.get(key)
            if value:
                code = str(value)
                break
        for key in ("ZONE_DESC", "ZONING_DESC", "ZONE_LABEL", "ZONE_NAME", "FNAME"):
            value = attrs.get(key)
            if value:
                desc = str(value)
                break
        if not code:
            for key, value in attrs.items():
                key_upper = key.upper()
                if any(
                    keyword in key_upper
                    for keyword in ("ZONE_CODE", "ZONING_CODE", "ZONE", "ZONING")
                ):
                    code = str(value) if value else ""
                    if code:
                        break

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
    *,
    clear_parcel_zoning: bool = False,
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

    if clear_parcel_zoning:
        record.zoning_code = ""
        record.zoning_description = ""

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
