"""Snapshot persistence service — stores OrdinanceSourceSnapshot to DB.

Review feedback #7. Previously snapshots were in-memory only with fake IDs
(content_hash[:16]). This service provides real DB persistence with full IDs.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from plotlot.ingestion.snapshots import OrdinanceSourceSnapshot
from plotlot.storage.db import get_session
from plotlot.storage.models import OrdinanceSourceSnapshotORM


async def persist_snapshot(snapshot: OrdinanceSourceSnapshot) -> OrdinanceSourceSnapshotORM:
    """Persist a snapshot to the DB. Returns the ORM row with real ID."""
    orm = OrdinanceSourceSnapshotORM(
        id=f"snap_{uuid.uuid4().hex[:12]}",
        source_authority_id=snapshot.source_authority_id,
        source_url=snapshot.source_url,
        final_url=snapshot.final_url,
        http_status=snapshot.http_status,
        content_type=snapshot.content_type,
        content_hash=snapshot.content_hash,
        raw_storage_url=snapshot.raw_storage_url,
        raw_text_excerpt=snapshot.raw_text_excerpt[:500] if snapshot.raw_text_excerpt else None,
        etag=snapshot.etag,
        last_modified=snapshot.last_modified,
        source_version=snapshot.source_version,
        metadata_json=snapshot.metadata_json,
    )
    session = await get_session()
    try:
        session.add(orm)
        await session.commit()
        return orm
    finally:
        await session.close()


async def get_latest_snapshot(source_authority_id: str) -> OrdinanceSourceSnapshotORM | None:
    session = await get_session()
    try:
        result = await session.execute(
            select(OrdinanceSourceSnapshotORM)
            .where(OrdinanceSourceSnapshotORM.source_authority_id == source_authority_id)
            .order_by(OrdinanceSourceSnapshotORM.fetched_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    finally:
        await session.close()


__all__ = ["get_latest_snapshot", "persist_snapshot"]
