from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.core.lookup_snapshot import LookupSnapshot
from plotlot.pipeline.lookup_snapshot_repository_payload import (
    analysis_run_output,
    persisted_record_from_payload,
)
from plotlot.pipeline.lookup_snapshot_repository_evidence import upsert_evidence_item
from plotlot.pipeline.lookup_snapshot_repository_rows import (
    ensure_project,
    ensure_site,
    ensure_workspace,
    upsert_analysis_run,
    upsert_tool_run,
)
from plotlot.pipeline.lookup_snapshot_repository_types import (
    DEFAULT_LOOKUP_PROJECT_ID,
    DEFAULT_LOOKUP_WORKSPACE_ID,
    LookupSnapshotPersistenceContext,
    PersistedLookupSnapshotRecord,
)
from plotlot.pipeline.lookup_snapshot_store import (
    StoredLookupSnapshot,
    build_stored_lookup_snapshot,
)
from plotlot.storage.models import AnalysisRun


async def persist_lookup_snapshot(
    session: AsyncSession,
    snapshot: LookupSnapshot,
    context: LookupSnapshotPersistenceContext,
) -> StoredLookupSnapshot:
    stored = build_stored_lookup_snapshot(snapshot)
    now = datetime.now(UTC)
    project_id = context.project_id or DEFAULT_LOOKUP_PROJECT_ID
    site_id = context.site_id or str(snapshot.site_id)
    snapshot_id = str(snapshot.lookup_snapshot_id)
    payload = analysis_run_output(snapshot, stored)

    await ensure_workspace(session, context, now)
    await ensure_project(session, context.workspace_id, project_id, now)
    await ensure_site(session, snapshot, context, project_id, site_id, now)
    await upsert_analysis_run(session, snapshot_id, context, project_id, site_id, payload, now)
    tool_run_id = await upsert_tool_run(
        session, snapshot_id, context, project_id, site_id, stored, now
    )
    for record in stored.evidence_records:
        await upsert_evidence_item(
            session,
            snapshot_id,
            tool_run_id,
            context,
            project_id,
            site_id,
            record,
        )
    await session.commit()
    return stored


async def load_lookup_snapshot_record(
    session: AsyncSession,
    snapshot_id: str,
) -> PersistedLookupSnapshotRecord | None:
    row = await session.get(AnalysisRun, snapshot_id)
    if row is None or row.status != "completed":
        return None
    if not isinstance(row.output_json, dict):
        return None
    return persisted_record_from_payload(row.output_json)


__all__ = [
    "DEFAULT_LOOKUP_PROJECT_ID",
    "DEFAULT_LOOKUP_WORKSPACE_ID",
    "LookupSnapshotPersistenceContext",
    "PersistedLookupSnapshotRecord",
    "load_lookup_snapshot_record",
    "persist_lookup_snapshot",
]
