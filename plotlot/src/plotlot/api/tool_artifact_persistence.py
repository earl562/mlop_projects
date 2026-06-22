from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.storage.models import Document, EvidenceItem, Report


@dataclass(frozen=True, slots=True)
class ToolArtifactContext:
    workspace_id: str
    project_id: str
    site_id: str | None
    analysis_run_id: str | None


@dataclass(frozen=True, slots=True)
class ToolArtifactPersistenceResult:
    status: Literal["ok", "blocked"]
    result_payload: dict[str, Any] | None
    message: str | None
    artifact_ids: dict[str, str]


async def persist_tool_artifacts(
    session: AsyncSession,
    result_payload: dict[str, Any] | None,
    context: ToolArtifactContext,
) -> ToolArtifactPersistenceResult:
    if result_payload is None:
        return _ok(result_payload, {})

    artifacts = result_payload.get("artifacts") or {}
    if not isinstance(artifacts, Mapping):
        return _ok(result_payload, {})

    report_spec = artifacts.get("report")
    document_spec = artifacts.get("document")
    evidence_ids = _artifact_evidence_ids(
        report_spec if isinstance(report_spec, Mapping) else None,
        document_spec if isinstance(document_spec, Mapping) else None,
    )
    missing_evidence_ids = await _missing_evidence_ids(session, evidence_ids)
    if missing_evidence_ids:
        return _blocked(result_payload, missing_evidence_ids)

    artifact_ids: dict[str, str] = {}
    if isinstance(report_spec, Mapping):
        report_id = str(uuid.uuid4())
        session.add(
            Report(
                id=report_id,
                workspace_id=context.workspace_id,
                project_id=context.project_id,
                site_id=context.site_id,
                analysis_run_id=context.analysis_run_id,
                status=str(report_spec.get("status") or "draft"),
                report_json=_mapping(report_spec.get("report_json")),
                evidence_ids=_evidence_ids(report_spec),
                version=1,
            )
        )
        await session.flush()
        artifact_ids["report_id"] = report_id

    if isinstance(document_spec, Mapping):
        document_id = str(uuid.uuid4())
        session.add(
            Document(
                id=document_id,
                workspace_id=context.workspace_id,
                project_id=context.project_id,
                site_id=context.site_id,
                report_id=artifact_ids.get("report_id"),
                document_type=str(document_spec.get("document_type") or "document"),
                status=str(document_spec.get("status") or "draft"),
                storage_url=_optional_str(document_spec.get("storage_url")),
                metadata_json=_mapping(document_spec.get("metadata_json")),
            )
        )
        artifact_ids["document_id"] = document_id

    return _ok(result_payload, artifact_ids)


async def _missing_evidence_ids(session: AsyncSession, evidence_ids: list[str]) -> list[str]:
    missing: list[str] = []
    for evidence_id in evidence_ids:
        row = await session.get(EvidenceItem, evidence_id)
        if row is None:
            missing.append(evidence_id)
    return missing


def _artifact_evidence_ids(
    report_spec: Mapping[str, Any] | None, document_spec: Mapping[str, Any] | None
) -> list[str]:
    evidence_ids: list[str] = []
    if report_spec is not None:
        evidence_ids.extend(_evidence_ids(report_spec))
    if document_spec is not None:
        evidence_ids.extend(_evidence_ids(document_spec))
        metadata = document_spec.get("metadata_json")
        if isinstance(metadata, Mapping):
            evidence_ids.extend(_evidence_ids(metadata))
    return list(dict.fromkeys(evidence_ids))


def _evidence_ids(spec: Mapping[str, Any]) -> list[str]:
    return [
        evidence_id
        for evidence_id in (str(raw).strip() for raw in spec.get("evidence_ids") or [])
        if evidence_id
    ]


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _blocked(
    result_payload: dict[str, Any], missing_evidence_ids: list[str]
) -> ToolArtifactPersistenceResult:
    message = "Report artifacts require recorded evidence items before persistence."
    payload = {
        **result_payload,
        "status": "blocked",
        "message": message,
        "missing_evidence_ids": missing_evidence_ids,
        "artifacts": {},
    }
    return ToolArtifactPersistenceResult(
        status="blocked",
        result_payload=payload,
        message=message,
        artifact_ids={},
    )


def _ok(
    result_payload: dict[str, Any] | None,
    artifact_ids: dict[str, str],
) -> ToolArtifactPersistenceResult:
    return ToolArtifactPersistenceResult(
        status="ok",
        result_payload=result_payload,
        message=None,
        artifact_ids=artifact_ids,
    )
