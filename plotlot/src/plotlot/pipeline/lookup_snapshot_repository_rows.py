from __future__ import annotations

from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.core.lookup_snapshot import LookupSnapshot
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.pipeline.lookup_snapshot_store import StoredLookupSnapshot
from plotlot.pipeline.lookup_snapshot_repository_types import (
    LOOKUP_SNAPSHOT_SKILL_NAME,
    LOOKUP_TOOL_NAME,
    LookupSnapshotPersistenceContext,
)
from plotlot.storage.models import AnalysisRun, Project, Site, ToolRun, Workspace


async def ensure_workspace(
    session: AsyncSession,
    context: LookupSnapshotPersistenceContext,
    now: datetime,
) -> None:
    row = await session.get(Workspace, context.workspace_id)
    if row is not None:
        return
    session.add(
        Workspace(
            id=context.workspace_id,
            name="Default Workspace",
            owner_user_id=context.actor_user_id if context.actor_user_id != "anonymous" else None,
            settings_json={},
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()


async def ensure_project(
    session: AsyncSession,
    workspace_id: str,
    project_id: str,
    now: datetime,
) -> None:
    row = await session.get(Project, project_id)
    if row is not None:
        return
    session.add(
        Project(
            id=project_id,
            workspace_id=workspace_id,
            name="Default Lookup Project",
            description="Auto-created for lookup snapshot runs.",
            status="active",
            metadata_json={"purpose": "lookup_correctness"},
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()


async def ensure_site(
    session: AsyncSession,
    snapshot: LookupSnapshot,
    context: LookupSnapshotPersistenceContext,
    project_id: str,
    site_id: str,
    now: datetime,
) -> None:
    facts_json = _site_facts(snapshot)
    row = await session.get(Site, site_id)
    if row is not None:
        setattr(row, "facts_json", facts_json)
        setattr(row, "updated_at", now)
        await session.flush()
        return
    session.add(
        Site(
            id=site_id,
            workspace_id=context.workspace_id,
            project_id=project_id,
            address=context.request_address,
            parcel_id=_field_value(snapshot, "parcel.apn"),
            geometry_json={},
            facts_json=facts_json,
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()


async def upsert_analysis_run(
    session: AsyncSession,
    snapshot_id: str,
    context: LookupSnapshotPersistenceContext,
    project_id: str,
    site_id: str,
    payload: dict[str, JsonValue],
    now: datetime,
) -> None:
    row = await session.get(AnalysisRun, snapshot_id)
    if row is None:
        session.add(
            AnalysisRun(
                id=snapshot_id,
                workspace_id=context.workspace_id,
                project_id=project_id,
                site_id=site_id,
                analysis_id=None,
                skill_name=LOOKUP_SNAPSHOT_SKILL_NAME,
                status="completed",
                input_json={"address": context.request_address},
                output_json=payload,
                error_message=None,
                started_at=now,
                completed_at=now,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        setattr(row, "output_json", payload)
        setattr(row, "status", "completed")
        setattr(row, "completed_at", now)
        setattr(row, "updated_at", now)
    await session.flush()


async def upsert_tool_run(
    session: AsyncSession,
    snapshot_id: str,
    context: LookupSnapshotPersistenceContext,
    project_id: str,
    site_id: str,
    stored: StoredLookupSnapshot,
    now: datetime,
) -> str:
    tool_run_id = str(uuid5(NAMESPACE_URL, f"plotlot:{snapshot_id}:lookup_tool"))
    output: dict[str, JsonValue] = {
        "lookup_snapshot_id": snapshot_id,
        "evidence_ids": [str(evidence_id) for evidence_id in stored.trace_record.evidence_ids],
    }
    row = await session.get(ToolRun, tool_run_id)
    if row is None:
        session.add(
            ToolRun(
                id=tool_run_id,
                workspace_id=context.workspace_id,
                project_id=project_id,
                site_id=site_id,
                analysis_id=None,
                analysis_run_id=snapshot_id,
                tool_name=LOOKUP_TOOL_NAME,
                risk_class="read_only",
                status="ok",
                input_json={"address": context.request_address},
                output_json=output,
                error_message=None,
                started_at=now,
                completed_at=now,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        setattr(row, "status", "ok")
        setattr(row, "output_json", output)
        setattr(row, "completed_at", now)
        setattr(row, "updated_at", now)
    await session.flush()
    return tool_run_id


def _site_facts(snapshot: LookupSnapshot) -> dict[str, JsonValue]:
    return {
        "lookup_snapshot_id": str(snapshot.lookup_snapshot_id),
        "run_id": str(snapshot.run_id),
        "fields": {
            str(field.key): field.value
            for field in snapshot.fields
            if field.value not in ("", None)
        },
    }


def _field_value(snapshot: LookupSnapshot, key: str) -> str | None:
    for field in snapshot.fields:
        if str(field.key) == key and field.value not in ("", None):
            return str(field.value)
    return None
