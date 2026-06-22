from __future__ import annotations

from plotlot.core.lookup_snapshot import LookupSnapshot
from plotlot.pipeline.lookup_snapshot_repository import (
    PersistedLookupSnapshotRecord,
    load_lookup_snapshot_record,
)
from plotlot.pipeline.lookup_snapshot_serialization import lookup_snapshot_from_dict
from plotlot.pipeline.lookup_snapshot_store import get_lookup_snapshot
from plotlot.storage.db import get_session


async def load_agent_run_lookup_snapshot(snapshot_id: str) -> LookupSnapshot | None:
    stored = get_lookup_snapshot(snapshot_id)
    if stored is not None:
        return stored.snapshot
    persisted = await _get_persisted_lookup_snapshot(snapshot_id)
    if persisted is None:
        return None
    return lookup_snapshot_from_dict(persisted.snapshot_json)


async def _get_persisted_lookup_snapshot(
    snapshot_id: str,
) -> PersistedLookupSnapshotRecord | None:
    session = await get_session()
    try:
        return await load_lookup_snapshot_record(session, snapshot_id)
    finally:
        await session.close()
