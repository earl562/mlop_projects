"""Durable cache for county-assessor parcel lookups.

Every function here is best-effort: the assessor lookup must still work when the
database is unavailable, so a cache miss and a cache failure are the same thing
to the caller (``None``). Nothing raises.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from plotlot.storage.models import AssessorParcelCache

logger = logging.getLogger(__name__)

# Lot area is static between lot splits, but ownership changes on sale — a stale
# owner is a trust problem, so rows expire rather than living forever.
ASSESSOR_CACHE_TTL_DAYS = 30


def cache_key(source_url: str, apn_digits: str) -> str:
    """Identify a parcel within the specific county layer it was read from."""
    digest = hashlib.sha256((source_url or "").encode()).hexdigest()[:12]
    return f"{digest}:{apn_digits}"


async def get_cached_parcel(source_url: str, apn_digits: str) -> tuple[float | None, str] | None:
    """Return ``(lot_sqft, owner)`` if a live cache row exists, else ``None``."""
    from plotlot.storage.db import get_session

    key = cache_key(source_url, apn_digits)
    try:
        session = await get_session()
        try:
            row = (
                await session.execute(
                    select(AssessorParcelCache).where(
                        AssessorParcelCache.cache_key == key,
                        AssessorParcelCache.expires_at > datetime.now(timezone.utc),
                    )
                )
            ).scalar_one_or_none()
        finally:
            await session.close()
    except Exception:
        logger.debug("Assessor cache read unavailable for APN %s", apn_digits, exc_info=True)
        return None

    if row is None:
        return None
    return row.lot_sqft, (row.owner or "")


async def store_cached_parcel(
    source_url: str, apn_digits: str, lot_sqft: float | None, owner: str
) -> None:
    """Upsert a successful lookup. Failures to persist are logged, never raised."""
    from plotlot.storage.db import get_session

    key = cache_key(source_url, apn_digits)
    expires = datetime.now(timezone.utc) + timedelta(days=ASSESSOR_CACHE_TTL_DAYS)
    try:
        session = await get_session()
        try:
            existing = await session.get(AssessorParcelCache, key)
            if existing is None:
                session.add(
                    AssessorParcelCache(
                        cache_key=key,
                        apn=apn_digits,
                        source_url=source_url,
                        lot_sqft=lot_sqft,
                        owner=owner or None,
                        expires_at=expires,
                    )
                )
            else:
                existing.lot_sqft = lot_sqft
                existing.owner = owner or None
                existing.fetched_at = datetime.now(timezone.utc)
                existing.expires_at = expires
            await session.commit()
        finally:
            await session.close()
    except Exception:
        logger.debug("Assessor cache write unavailable for APN %s", apn_digits, exc_info=True)
