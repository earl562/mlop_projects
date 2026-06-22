from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.harness.agent_run_responses import AgentRunResponse
from plotlot.harness.agent_run_summary import (
    AgentRunSummaryArtifact,
    build_agent_run_summary_from_response,
)
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.models import Document, Report


@dataclass(frozen=True, slots=True)
class AgentRunPersistenceScope:
    workspace_id: str
    project_id: str
    site_id: str | None
    now: datetime


async def persist_agent_run_summary_artifacts(
    session: AsyncSession,
    response: AgentRunResponse,
    scope: AgentRunPersistenceScope,
) -> None:
    report_id = agent_run_report_id(response.run_id)
    document_id = agent_run_document_id(response.run_id)
    artifact = build_agent_run_summary_from_response(
        response,
        report_id=report_id,
        document_id=document_id,
    )
    if artifact.status != "draft":
        return
    await _upsert_report(session, artifact, scope)
    await _upsert_document(session, artifact, scope)
    await session.flush()


async def load_agent_run_summary_artifact(
    session: AsyncSession,
    run_id: str,
) -> AgentRunSummaryArtifact | None:
    report_id = agent_run_report_id(run_id)
    row = await session.get(Report, report_id)
    if row is None:
        return None
    raw_report_json: JsonValue = getattr(row, "report_json", {})
    report_json = _report_json(raw_report_json)
    if report_json is None:
        return None
    lookup_snapshot_id = _json_str(report_json.get("lookup_snapshot_id"))
    if lookup_snapshot_id is None:
        return None
    document_id = agent_run_document_id(run_id)
    document_row = await session.get(Document, document_id)
    raw_evidence_ids = getattr(row, "evidence_ids", ()) or ()
    return AgentRunSummaryArtifact(
        status=str(getattr(row, "status", None) or "draft"),
        run_id=run_id,
        lookup_snapshot_id=lookup_snapshot_id,
        evidence_ids=tuple(str(evidence_id) for evidence_id in raw_evidence_ids),
        report_json=report_json,
        report_id=report_id,
        document_id=None if document_row is None else document_id,
    )


def agent_run_report_id(run_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"plotlot:{run_id}:agent_run_summary_report"))


def agent_run_document_id(run_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"plotlot:{run_id}:agent_run_summary_document"))


async def _upsert_report(
    session: AsyncSession,
    artifact: AgentRunSummaryArtifact,
    scope: AgentRunPersistenceScope,
) -> None:
    if artifact.report_id is None:
        return
    row = await session.get(Report, artifact.report_id)
    if row is None:
        session.add(
            Report(
                id=artifact.report_id,
                workspace_id=scope.workspace_id,
                project_id=scope.project_id,
                site_id=scope.site_id,
                analysis_run_id=artifact.run_id,
                status=artifact.status,
                report_json=artifact.report_json,
                evidence_ids=list(artifact.evidence_ids),
                version=1,
            )
        )
        return
    setattr(row, "workspace_id", scope.workspace_id)
    setattr(row, "project_id", scope.project_id)
    setattr(row, "site_id", scope.site_id)
    setattr(row, "analysis_run_id", artifact.run_id)
    setattr(row, "status", artifact.status)
    setattr(row, "report_json", artifact.report_json)
    setattr(row, "evidence_ids", list(artifact.evidence_ids))
    setattr(row, "version", int(getattr(row, "version", 0) or 0) + 1)
    setattr(row, "updated_at", scope.now)


async def _upsert_document(
    session: AsyncSession,
    artifact: AgentRunSummaryArtifact,
    scope: AgentRunPersistenceScope,
) -> None:
    if artifact.document_id is None:
        return
    row = await session.get(Document, artifact.document_id)
    metadata_json: dict[str, JsonValue] = {
        "title": f"Agent run summary: {artifact.run_id}",
        "workspace_id": scope.workspace_id,
        "project_id": scope.project_id,
        "site_id": scope.site_id,
        "run_id": artifact.run_id,
        "lookup_snapshot_id": artifact.lookup_snapshot_id,
        "evidence_ids": list(artifact.evidence_ids),
    }
    if row is None:
        session.add(
            Document(
                id=artifact.document_id,
                workspace_id=scope.workspace_id,
                project_id=scope.project_id,
                site_id=scope.site_id,
                report_id=artifact.report_id,
                document_type="agent_run_summary",
                status=artifact.status,
                storage_url=None,
                metadata_json=metadata_json,
            )
        )
        return
    setattr(row, "workspace_id", scope.workspace_id)
    setattr(row, "project_id", scope.project_id)
    setattr(row, "site_id", scope.site_id)
    setattr(row, "report_id", artifact.report_id)
    setattr(row, "document_type", "agent_run_summary")
    setattr(row, "status", artifact.status)
    setattr(row, "metadata_json", metadata_json)
    setattr(row, "updated_at", scope.now)


def _report_json(value: JsonValue) -> dict[str, JsonValue] | None:
    if isinstance(value, dict):
        return value
    return None


def _json_str(value: JsonValue | None) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
