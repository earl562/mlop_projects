"""PostgreSQL county schema registry — async get/upsert for county cache and field mappings.

Replaces storage/firestore.py with a single PostgreSQL table (county_schemas).
The public interface is intentionally identical to firestore.py so callers only
need to change the import.

Graceful degradation: every function catches DB exceptions and returns None /
no-ops rather than crashing the pipeline — same contract as Firestore.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from plotlot.property.models import CountyCache, DatasetInfo, FieldMapping
from plotlot.storage.db import get_session
from plotlot.storage.models import CountySchema

logger = logging.getLogger(__name__)


async def get_county_cache(county_key: str) -> CountyCache | None:
    """Retrieve cached county datasets from PostgreSQL.

    Returns None when:
    - row does not exist
    - TTL has expired (age > ttl_hours)
    - any database error
    """
    try:
        async with await get_session() as session:
            row = await session.get(CountySchema, county_key)
            if row is None:
                return None

            age_hours = (
                datetime.now(timezone.utc) - row.last_verified.replace(tzinfo=timezone.utc)
            ).total_seconds() / 3600
            if age_hours > row.ttl_hours:
                logger.info(
                    "county_cache_expired county_key=%s age_hours=%.1f", county_key, age_hours
                )
                return None

            return _row_to_county_cache(row)
    except Exception:
        logger.warning("county_cache_read_failed county_key=%s", county_key, exc_info=True)
        return None


async def save_county_cache(cache: CountyCache) -> None:
    """Upsert county cache into PostgreSQL.  No-op on any database error."""
    try:
        async with await get_session() as session:
            stmt = (
                insert(CountySchema)
                .values(
                    county_key=cache.county_key,
                    state=cache.state,
                    parcels_dataset=(
                        cache.parcels_dataset.model_dump(mode="json")
                        if cache.parcels_dataset
                        else None
                    ),
                    zoning_dataset=(
                        cache.zoning_dataset.model_dump(mode="json")
                        if cache.zoning_dataset
                        else None
                    ),
                    field_mapping=(
                        cache.field_mapping.model_dump(mode="json") if cache.field_mapping else None
                    ),
                    ttl_hours=cache.ttl_hours,
                    last_verified=cache.last_verified,
                )
                .on_conflict_do_update(
                    index_elements=["county_key"],
                    set_={
                        "state": cache.state,
                        "parcels_dataset": (
                            cache.parcels_dataset.model_dump(mode="json")
                            if cache.parcels_dataset
                            else None
                        ),
                        "zoning_dataset": (
                            cache.zoning_dataset.model_dump(mode="json")
                            if cache.zoning_dataset
                            else None
                        ),
                        "field_mapping": (
                            cache.field_mapping.model_dump(mode="json")
                            if cache.field_mapping
                            else None
                        ),
                        "ttl_hours": cache.ttl_hours,
                        "last_verified": cache.last_verified,
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()
            logger.debug("county_cache_saved county_key=%s", cache.county_key)
    except Exception:
        logger.warning("county_cache_write_failed county_key=%s", cache.county_key, exc_info=True)


async def get_field_mapping(county_key: str) -> FieldMapping | None:
    """Retrieve field mapping from PostgreSQL county_schemas table.

    Returns None when row does not exist, field_mapping column is null,
    or any database error occurs.
    """
    try:
        async with await get_session() as session:
            result = await session.execute(
                select(CountySchema.field_mapping).where(CountySchema.county_key == county_key)
            )
            row = result.one_or_none()
            if row is None or row[0] is None:
                return None
            return FieldMapping.model_validate(row[0])
    except Exception:
        logger.warning("field_mapping_read_failed county_key=%s", county_key, exc_info=True)
        return None


async def save_field_mapping(mapping: FieldMapping) -> None:
    """Upsert field mapping into the county_schemas table.

    If the county row does not yet exist, inserts a skeleton row so the
    field_mapping column is populated.  No-op on any database error.
    """
    try:
        async with await get_session() as session:
            stmt = (
                insert(CountySchema)
                .values(
                    county_key=mapping.county_key,
                    state="",
                    field_mapping=mapping.model_dump(mode="json"),
                    last_verified=datetime.now(timezone.utc),
                )
                .on_conflict_do_update(
                    index_elements=["county_key"],
                    set_={"field_mapping": mapping.model_dump(mode="json")},
                )
            )
            await session.execute(stmt)
            await session.commit()
            logger.debug("field_mapping_saved county_key=%s", mapping.county_key)
    except Exception:
        logger.warning(
            "field_mapping_write_failed county_key=%s", mapping.county_key, exc_info=True
        )


# ── Private helpers ────────────────────────────────────────────────────────────


def _row_to_county_cache(row: CountySchema) -> CountyCache:
    """Convert a CountySchema ORM row into a CountyCache Pydantic model."""
    return CountyCache(
        county_key=row.county_key,
        state=row.state,
        parcels_dataset=(
            DatasetInfo.model_validate(row.parcels_dataset) if row.parcels_dataset else None
        ),
        zoning_dataset=(
            DatasetInfo.model_validate(row.zoning_dataset) if row.zoning_dataset else None
        ),
        field_mapping=(
            FieldMapping.model_validate(row.field_mapping) if row.field_mapping else None
        ),
        last_verified=row.last_verified.replace(tzinfo=timezone.utc),
        ttl_hours=row.ttl_hours,
    )
