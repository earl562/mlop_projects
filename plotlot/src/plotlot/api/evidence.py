"""Evidence + artifact read APIs.

These endpoints make the durable harness spine usable: callers can list and
retrieve evidence, reports, and documents that were written during governed tool
execution.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from plotlot.harness.contracts import EvidenceId as HarnessEvidenceId
from plotlot.harness.evidence_store import EvidenceNotFoundError, default_evidence_ledger
from plotlot.storage.db import get_session
from plotlot.storage.models import Document, EvidenceItem as StorageEvidenceItem, Report


router = APIRouter(prefix="/api/v1", tags=["evidence"])


@router.get("/evidence")
async def list_evidence(
    workspace_id: str,
    project_id: str | None = None,
    site_id: str | None = None,
    analysis_id: str | None = None,
    analysis_run_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    session = await get_session()
    try:
        q = select(StorageEvidenceItem).where(StorageEvidenceItem.workspace_id == workspace_id)
        if project_id:
            q = q.where(StorageEvidenceItem.project_id == project_id)
        if site_id:
            q = q.where(StorageEvidenceItem.site_id == site_id)
        if analysis_id:
            q = q.where(StorageEvidenceItem.analysis_id == analysis_id)
        if analysis_run_id:
            q = q.where(StorageEvidenceItem.analysis_run_id == analysis_run_id)
        q = q.order_by(StorageEvidenceItem.retrieved_at.desc()).limit(limit).offset(offset)
        result = await session.execute(q)
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "workspace_id": r.workspace_id,
                "project_id": r.project_id,
                "site_id": r.site_id,
                "analysis_id": r.analysis_id,
                "analysis_run_id": r.analysis_run_id,
                "claim_key": r.claim_key,
                "tool_name": r.tool_name,
                "confidence": r.confidence,
                "source_type": r.source_type,
                "source_url": r.source_url,
                "source_title": r.source_title,
                "retrieved_at": r.retrieved_at.isoformat(),
                "metadata_json": r.metadata_json,
            }
            for r in rows
        ]
    finally:
        await session.close()


@router.get("/evidence/{evidence_id}")
async def get_evidence(evidence_id: str):
    session = await get_session()
    try:
        row = await session.get(StorageEvidenceItem, evidence_id)
    finally:
        await session.close()
    if row is not None:
        return {
            "id": row.id,
            "workspace_id": row.workspace_id,
            "project_id": row.project_id,
            "site_id": row.site_id,
            "analysis_id": row.analysis_id,
            "analysis_run_id": row.analysis_run_id,
            "tool_run_id": row.tool_run_id,
            "claim_key": row.claim_key,
            "value_json": row.value_json,
            "source_type": row.source_type,
            "source_url": row.source_url,
            "source_title": row.source_title,
            "retrieval_method": row.retrieval_method,
            "trust_label": row.trust_label,
            "content_hash": row.content_hash,
            "tool_name": row.tool_name,
            "confidence": row.confidence,
            "metadata_json": row.metadata_json,
            "retrieved_at": row.retrieved_at.isoformat(),
        }
    try:
        return default_evidence_ledger().get_evidence(
            HarnessEvidenceId(evidence_id)
        ).model_dump(mode="json")
    except EvidenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Evidence not found") from exc


@router.get("/artifacts/reports")
async def list_reports(
    workspace_id: str,
    project_id: str | None = None,
    site_id: str | None = None,
    limit: int = 25,
    offset: int = 0,
):
    session = await get_session()
    try:
        q = select(Report).where(Report.workspace_id == workspace_id)
        if project_id:
            q = q.where(Report.project_id == project_id)
        if site_id:
            q = q.where(Report.site_id == site_id)
        q = q.order_by(Report.updated_at.desc()).limit(limit).offset(offset)
        result = await session.execute(q)
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "status": r.status,
                "version": r.version,
                "evidence_ids": list(r.evidence_ids or []),
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]
    finally:
        await session.close()


@router.get("/artifacts/reports/{report_id}")
async def get_report(report_id: str):
    session = await get_session()
    try:
        row = await session.get(Report, report_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return {
            "id": row.id,
            "workspace_id": row.workspace_id,
            "project_id": row.project_id,
            "site_id": row.site_id,
            "status": row.status,
            "version": row.version,
            "report_json": row.report_json,
            "evidence_ids": list(row.evidence_ids or []),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    finally:
        await session.close()


@router.get("/artifacts/documents")
async def list_documents(
    workspace_id: str,
    project_id: str | None = None,
    site_id: str | None = None,
    report_id: str | None = None,
    limit: int = 25,
    offset: int = 0,
):
    session = await get_session()
    try:
        q = select(Document).where(Document.workspace_id == workspace_id)
        if project_id:
            q = q.where(Document.project_id == project_id)
        if site_id:
            q = q.where(Document.site_id == site_id)
        if report_id:
            q = q.where(Document.report_id == report_id)
        q = q.order_by(Document.updated_at.desc()).limit(limit).offset(offset)
        result = await session.execute(q)
        rows = result.scalars().all()
        return [
            {
                "id": d.id,
                "document_type": d.document_type,
                "status": d.status,
                "report_id": d.report_id,
                "storage_url": d.storage_url,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            }
            for d in rows
        ]
    finally:
        await session.close()


@router.get("/artifacts/documents/{document_id}")
async def get_document(document_id: str):
    session = await get_session()
    try:
        row = await session.get(Document, document_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return {
            "id": row.id,
            "workspace_id": row.workspace_id,
            "project_id": row.project_id,
            "site_id": row.site_id,
            "report_id": row.report_id,
            "document_type": row.document_type,
            "status": row.status,
            "storage_url": row.storage_url,
            "metadata_json": row.metadata_json,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    finally:
        await session.close()
