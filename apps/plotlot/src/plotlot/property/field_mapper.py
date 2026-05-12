"""Field mapping engine — maps ArcGIS field names to PropertyRecord fields.

Uses a two-phase approach:
1. Heuristic keyword matching (fast, no LLM cost, confidence 0.7-0.95)
2. LLM fallback for ambiguous fields (slower, but handles edge cases)

Field mappings are cached locally so each county is mapped only once.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from plotlot.property.models import FieldMapping

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Heuristic keyword rules
# ---------------------------------------------------------------------------
# Each PropertyRecord field maps to a list of ArcGIS field keywords.
# Matching is case-insensitive substring/exact match.

_HEURISTIC_RULES: dict[str, list[str]] = {
    "folio": [
        "FOLIO",
        "FOLIO_NUMBER",
        "PARCEL_NUMBER",
        "PARCEL_ID",
        "PARCEL_NO",
        "APN",
        "PID",
        "PIN",
        "PARCELNO",
        "PARCEL_NUM",
        "TAX_ID",
    ],
    "address": [
        "SITE_ADDR",
        "TRUE_SITE_ADDR",
        "SITUS_ADDR",
        "PROP_ADDR",
        "SITE_ADDRESS",
        "PROPERTY_ADDRESS",
        "FULL_ADDRESS",
        "ADDRESS",
        "SITUS_ADDRESS",
        "SITE_ADDR_STR",
    ],
    "municipality": [
        "MUNICIPALITY",
        "CITY",
        "SITE_CITY",
        "TRUE_SITE_CITY",
        "SITUS_CITY",
        "MUNI",
    ],
    "owner": [
        "OWNER",
        "OWNER_NAME",
        "OWNER_NAME1",
        "NAME_LINE_1",
        "TRUE_OWNER1",
        "TRUE_OWNER",
        "OWN_NAME",
    ],
    "zoning_code": [
        "ZONE_CODE",
        "ZONING_CODE",
        "ZONE_CLASS",
        "ZONE",
        "ZONING",
        "ZONE_DESC",
        "ZONING_DISTRICT",
        "ZONE_TYPE",
    ],
    "zoning_description": [
        "ZONE_DESCRIPTION",
        "ZONING_DESCRIPTION",
        "ZONING_DESC",
        "ZONE_LABEL",
        "ZONING_NAME",
    ],
    "land_use_code": [
        "LAND_USE",
        "LAND_USE_CODE",
        "USE_CODE",
        "DOR_CODE",
        "DOR_CODE_CUR",
        "PROPERTY_USE",
        "LU_CODE",
    ],
    "land_use_description": [
        "LAND_USE_DESC",
        "DOR_DESC",
        "USE_DESC",
        "LAND_USE_DESCRIPTION",
        "LU_DESC",
    ],
    "lot_size_sqft": [
        "LOT_SIZE",
        "LOT_AREA",
        "LAND_SQFT",
        "SQ_FOOTAGE",
        "TOTAL_SQFT",
        "LAND_AREA",
    ],
    "bedrooms": [
        "BEDROOM_COUNT",
        "BEDROOMS",
        "BEDROOM",
        "BED_COUNT",
        "NUM_BEDROOMS",
        "NO_BEDROOMS",
    ],
    "bathrooms": [
        "BATHROOM_COUNT",
        "BATHROOMS",
        "BATHROOM",
        "BATH_COUNT",
        "NUM_BATHROOMS",
        "FULL_BATHS",
    ],
    "half_baths": [
        "HALF_BATHROOM_COUNT",
        "HALF_BATH",
        "HALF_BATHS",
    ],
    "floors": [
        "FLOOR_COUNT",
        "FLOORS",
        "STORIES",
        "NO_STORIES",
        "NUM_FLOORS",
        "STORY_COUNT",
    ],
    "living_units": [
        "UNIT_COUNT",
        "LIVING_UNITS",
        "UNITS",
        "NUM_UNITS",
        "DWELLING_UNITS",
        "NO_UNITS",
    ],
    "building_area_sqft": [
        "BUILDING_ACTUAL_AREA",
        "BUILDING_AREA",
        "BLDG_AREA",
        "BLDG_ADJ_SQ_FOOTAGE",
        "TOTAL_BLDG_AREA",
    ],
    "living_area_sqft": [
        "BUILDING_HEATED_AREA",
        "LIVING_AREA",
        "HEATED_AREA",
        "UNDER_AIR_SQFT",
        "UNDER_AIR",
        "HEATED_SQFT",
    ],
    "year_built": [
        "YEAR_BUILT",
        "YRBLT",
        "YR_BUILT",
        "BLDG_YEAR_BUILT",
        "YEARBUILT",
        "BUILT_YEAR",
    ],
    "assessed_value": [
        "ASSESSED_VAL",
        "ASSESSED_VALUE",
        "JUST_VALUE",
        "ASSESSED_VAL_CUR",
        "ASSESSED_TOTAL",
    ],
    "market_value": [
        "MARKET_VALUE",
        "TOTAL_MARKET",
        "MARKET_VAL",
        "JUST_MARKET_VALUE",
    ],
    "last_sale_price": [
        "PRICE_1",
        "SALE_PRICE",
        "LAST_SALE_PRICE",
        "PRICE",
        "SALE_AMOUNT",
        "LAST_SALE_AMT",
    ],
    "last_sale_date": [
        "DOS_1",
        "SALE_DATE",
        "LAST_SALE_DATE",
        "DATE_OF_SALE",
        "SALE_DT",
    ],
}

# Fields that need unit conversion based on field name keywords
_ACRE_KEYWORDS = {"ACRES", "ACREAGE", "LAND_ACRES"}
_SQ_METER_KEYWORDS = {"SQ_M", "SQMETERS", "SQ_METERS", "AREA_M2"}

ACRES_TO_SQFT = 43_560.0
SQ_METERS_TO_SQFT = 10.764


def map_fields_heuristic(source_fields: list[str]) -> FieldMapping:
    """Map ArcGIS fields to PropertyRecord fields using keyword heuristics.

    Args:
        source_fields: List of field names from the ArcGIS layer.

    Returns:
        FieldMapping with matched fields and confidence score.
    """
    mappings: dict[str, str] = {}
    unit_conversions: dict[str, str] = {}
    matched_count = 0

    upper_sources = {f.upper(): f for f in source_fields}

    for prop_field, keywords in _HEURISTIC_RULES.items():
        for keyword in keywords:
            keyword_upper = keyword.upper()
            # Exact match first
            if keyword_upper in upper_sources:
                mappings[upper_sources[keyword_upper]] = prop_field
                matched_count += 1
                break
            # Substring match
            for src_upper, src_orig in upper_sources.items():
                if keyword_upper in src_upper and src_orig not in mappings:
                    mappings[src_orig] = prop_field
                    matched_count += 1
                    break
            else:
                continue
            break

    # Detect lot size fields that need unit conversion
    for src_upper, src_orig in upper_sources.items():
        if any(kw in src_upper for kw in _ACRE_KEYWORDS):
            if src_orig not in mappings:
                mappings[src_orig] = "lot_size_sqft"
                matched_count += 1
            unit_conversions[src_orig] = "acres_to_sqft"
        elif any(kw in src_upper for kw in _SQ_METER_KEYWORDS):
            if src_orig not in mappings:
                mappings[src_orig] = "lot_size_sqft"
                matched_count += 1
            unit_conversions[src_orig] = "sq_meters_to_sqft"

    # Confidence based on how many target fields were matched
    total_target_fields = len(_HEURISTIC_RULES)
    confidence = min(matched_count / max(total_target_fields, 1), 1.0)
    # Scale: 5+ matches → 0.7+, 10+ → 0.85+, 15+ → 0.95+
    confidence = 0.5 + (confidence * 0.45)

    return FieldMapping(
        county_key="",  # Caller sets this
        mappings=mappings,
        unit_conversions=unit_conversions,
        confidence=round(confidence, 2),
        method="heuristic",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


async def map_fields(
    source_fields: list[str],
    sample_features: list[dict] | None = None,
    county: str = "",
) -> FieldMapping:
    """Map ArcGIS field names to PropertyRecord fields.

    Phase 1: Heuristic keyword matching (always runs).
    Phase 2: LLM fallback for unmapped fields (if confidence < 0.7 and sample data available).

    Args:
        source_fields: Field names from the ArcGIS layer.
        sample_features: Optional sample feature attributes for LLM context.
        county: County name for the mapping.

    Returns:
        FieldMapping with all matched fields.
    """
    mapping = map_fields_heuristic(source_fields)
    mapping.county_key = county.lower().strip()

    # If heuristic confidence is good enough, skip LLM
    if mapping.confidence >= 0.7:
        logger.info(
            "Heuristic mapping for %s: %d fields matched (confidence=%.2f)",
            county,
            len(mapping.mappings),
            mapping.confidence,
        )
        return mapping

    # LLM fallback for low-confidence mappings
    if sample_features:
        llm_mapping = await _llm_field_mapping(source_fields, sample_features, mapping)
        if llm_mapping:
            return llm_mapping

    return mapping


async def _llm_field_mapping(
    source_fields: list[str],
    sample_features: list[dict],
    partial_mapping: FieldMapping,
) -> FieldMapping | None:
    """Use LLM to map remaining unmapped fields."""
    try:
        from plotlot.retrieval.llm import call_llm
    except ImportError:
        logger.debug("LLM module not available for field mapping fallback")
        return None

    # Find unmapped PropertyRecord fields
    mapped_targets = set(partial_mapping.mappings.values())
    unmapped_targets = [f for f in _HEURISTIC_RULES if f not in mapped_targets]

    if not unmapped_targets:
        return None

    # Find unmapped source fields
    mapped_sources = set(partial_mapping.mappings.keys())
    unmapped_sources = [f for f in source_fields if f not in mapped_sources]

    if not unmapped_sources:
        return None

    # Build sample data string
    sample_str = ""
    for feat in sample_features[:2]:
        attrs = feat.get("attributes", feat)
        relevant = {k: v for k, v in attrs.items() if k in unmapped_sources}
        sample_str += f"\nSample: {relevant}"

    prompt = (
        "Map these ArcGIS field names to property record fields.\n\n"
        f"Unmapped ArcGIS fields: {unmapped_sources}\n"
        f"Target PropertyRecord fields needing mapping: {unmapped_targets}\n"
        f"{sample_str}\n\n"
        "Return ONLY a JSON object mapping ArcGIS field name → PropertyRecord field name. "
        'Only include confident mappings. Example: {"BLDG_YR": "year_built"}'
    )

    import json

    try:
        response = await call_llm(
            [{"role": "user", "content": prompt}],
            tools=None,
        )
        content = response.get("content", "") if response else ""
        # Parse JSON from response
        content = content.strip().strip("`").lstrip("json\n")
        llm_mappings = json.loads(content)

        if isinstance(llm_mappings, dict):
            # Merge LLM mappings into heuristic mappings
            new_mapping = partial_mapping.model_copy()
            for src, tgt in llm_mappings.items():
                if src in source_fields and tgt in _HEURISTIC_RULES:
                    new_mapping.mappings[src] = tgt
            new_mapping.method = "heuristic+llm"
            new_mapping.confidence = min(new_mapping.confidence + 0.1, 0.9)
            new_mapping.updated_at = datetime.now(timezone.utc)
            logger.info("LLM mapped %d additional fields", len(llm_mappings))
            return new_mapping
    except (json.JSONDecodeError, Exception):
        logger.warning("LLM field mapping failed", exc_info=True)

    return None
