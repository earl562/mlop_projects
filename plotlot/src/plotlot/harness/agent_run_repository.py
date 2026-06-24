from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.harness.agent_run import AgentRunRecord
from plotlot.harness.agent_run_artifact_repository import (
    AgentRunPersistenceScope,
    persist_agent_run_summary_artifacts,
)
from plotlot.harness.agent_run_responses import AgentRunResponse
from plotlot.harness.context import ContextFieldPacket
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.models import AnalysisRun, Project, Site, Workspace

AGENT_RUN_SKILL_NAME = "agentic_land_developer_harness"


@dataclass(frozen=True, slots=True)
class AgentRunPersistenceInput:
    record: AgentRunRecord
    lookup_snapshot_id: str
    response: AgentRunResponse


@dataclass(frozen=True, slots=True)
class AgentRunIdConflictError(Exception):
    run_id: str

    def __str__(self) -> str:
        return f"Agent run {self.run_id} already exists"


async def persist_agent_run(
    session: AsyncSession,
    command: AgentRunPersistenceInput,
) -> None:
    scope = _persistence_scope(command.record)
    await _ensure_workspace(session, scope)
    await _ensure_project(session, scope)
    await _ensure_site(session, command, scope)
    payload: dict[str, JsonValue] = {
        "agent_run": command.response.model_dump(mode="json"),
        "lookup_snapshot_id": command.lookup_snapshot_id,
    }
    input_json: dict[str, JsonValue] = {
        "lookup_snapshot_id": command.lookup_snapshot_id,
        "objective": command.record.objective,
        "open_questions": list(command.record.open_questions),
        "warnings": list(command.record.warnings),
    }

    row = await session.get(AnalysisRun, str(command.record.run_id))
    if row is None:
        session.add(
            AnalysisRun(
                id=str(command.record.run_id),
                workspace_id=scope.workspace_id,
                project_id=scope.project_id,
                site_id=scope.site_id,
                analysis_id=None,
                skill_name=AGENT_RUN_SKILL_NAME,
                status=command.record.status.value,
                input_json=input_json,
                output_json=payload,
                error_message=None,
                started_at=scope.now,
                completed_at=scope.now,
                created_at=scope.now,
                updated_at=scope.now,
            )
        )
    else:
        raise AgentRunIdConflictError(str(command.record.run_id))
    await session.flush()
    await persist_agent_run_summary_artifacts(session, command.response, scope)
    await session.commit()


async def load_agent_run_response(
    session: AsyncSession,
    run_id: str,
    workspace_id: str | None = None,
) -> AgentRunResponse | None:
    row = await session.get(AnalysisRun, run_id)
    if row is None or row.skill_name != AGENT_RUN_SKILL_NAME:
        return None
    if workspace_id is not None and row.workspace_id != workspace_id:
        return None
    if not isinstance(row.output_json, dict):
        return None
    payload = row.output_json.get("agent_run")
    if not isinstance(payload, dict):
        return None
    return AgentRunResponse.model_validate(payload)


def default_agent_run_project_id(workspace_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"plotlot:{workspace_id}:agent_run_project"))


def _persistence_scope(record: AgentRunRecord) -> AgentRunPersistenceScope:
    project_id = record.project_id or default_agent_run_project_id(record.workspace_id)
    return AgentRunPersistenceScope(
        workspace_id=record.workspace_id,
        project_id=project_id,
        site_id=record.site_id,
        now=datetime.now(UTC),
    )


async def _ensure_workspace(
    session: AsyncSession,
    scope: AgentRunPersistenceScope,
) -> None:
    row = await session.get(Workspace, scope.workspace_id)
    if row is not None:
        return
    session.add(
        Workspace(
            id=scope.workspace_id,
            name="Default Agent Run Workspace",
            owner_user_id=None,
            settings_json={},
            created_at=scope.now,
            updated_at=scope.now,
        )
    )
    await session.flush()


async def _ensure_project(
    session: AsyncSession,
    scope: AgentRunPersistenceScope,
) -> None:
    row = await session.get(Project, scope.project_id)
    if row is not None:
        return
    session.add(
        Project(
            id=scope.project_id,
            workspace_id=scope.workspace_id,
            name="Default Agent Run Project",
            description="Auto-created for agentic land-developer harness runs.",
            status="active",
            metadata_json={"purpose": "agentic_land_developer_harness"},
            created_at=scope.now,
            updated_at=scope.now,
        )
    )
    await session.flush()


async def _ensure_site(
    session: AsyncSession,
    command: AgentRunPersistenceInput,
    scope: AgentRunPersistenceScope,
) -> None:
    if scope.site_id is None:
        return
    row = await session.get(Site, scope.site_id)
    if row is not None:
        return
    session.add(
        Site(
            id=scope.site_id,
            workspace_id=scope.workspace_id,
            project_id=scope.project_id,
            address=_site_address(command.record),
            parcel_id=_site_parcel_id(command.record),
            geometry_json={},
            facts_json=_site_facts_json(command.record, command.lookup_snapshot_id),
            created_at=scope.now,
            updated_at=scope.now,
        )
    )
    await session.flush()


def _site_address(record: AgentRunRecord) -> str:
    value = _context_field_value(record, "parcel.address")
    if isinstance(value, str) and value:
        return value
    return "Unknown site"


def _site_parcel_id(record: AgentRunRecord) -> str | None:
    value = _context_field_value(record, "parcel.apn")
    if isinstance(value, str) and value:
        return value
    return None


def _site_facts_json(
    record: AgentRunRecord,
    lookup_snapshot_id: str,
) -> dict[str, JsonValue]:
    return {
        "lookup_snapshot_id": lookup_snapshot_id,
        "fields": [_context_field_json(field) for field in record.context_packet.fields],
    }


def _context_field_json(field: ContextFieldPacket) -> dict[str, JsonValue]:
    return {
        "key": str(field.key),
        "label": field.label,
        "value": field.value,
        "unit": field.unit,
        "display_state": field.display_state.value,
        "evidence_ids": [str(evidence_id) for evidence_id in field.evidence_ids],
        "confidence": field.confidence,
        "warnings": list(field.warnings),
    }


def _context_field_value(
    record: AgentRunRecord,
    key: str,
) -> JsonValue:
    for field in record.context_packet.fields:
        if str(field.key) == key:
            return field.value
    return None
