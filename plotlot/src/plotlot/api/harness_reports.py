from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from plotlot.harness.contracts import ClaimId, JsonObject, ReportId, RunId
from plotlot.harness.report_export import (
    ReportArtifactExportRequest,
    ReportExportFormat,
    export_report_artifact,
)
from plotlot.harness.report_finalization import ReportFinalizationBlockedError, finalize_report
from plotlot.harness.report_store import ClaimNotFoundError, ReportNotFoundError, default_report_ledger
from plotlot.harness.run_store import default_harness_run_store
from plotlot.harness.verification_store import default_verification_ledger

router = APIRouter(prefix="/api/v1", tags=["harness-reports"])


class ReportExportRequestBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    export_format: ReportExportFormat = ReportExportFormat.MARKDOWN


@router.get("/harness/runs/{run_id}/claims")
async def harness_run_claims(run_id: str) -> JsonObject:
    claims = default_report_ledger().list_claims(run_id=RunId(run_id))
    return {"run_id": run_id, "claims": [claim.model_dump(mode="json") for claim in claims]}


@router.get("/claims/{claim_id}")
async def harness_claim(claim_id: str) -> JsonObject:
    try:
        claim = default_report_ledger().get_claim(ClaimId(claim_id))
    except ClaimNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return claim.model_dump(mode="json")


@router.get("/harness/runs/{run_id}/reports")
async def harness_run_reports(run_id: str) -> JsonObject:
    reports = default_report_ledger().list_reports(run_id=RunId(run_id))
    return {"run_id": run_id, "reports": [report.model_dump(mode="json") for report in reports]}


@router.get("/reports/{report_id}")
async def harness_report(report_id: str) -> JsonObject:
    try:
        report = default_report_ledger().get_report(ReportId(report_id))
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return report.model_dump(mode="json")


@router.post("/reports/{report_id}/export")
async def harness_report_export(
    report_id: str,
    body: ReportExportRequestBody | None = None,
) -> JsonObject:
    request_body = body or ReportExportRequestBody()
    try:
        export = export_report_artifact(
            ReportArtifactExportRequest(
                report_id=ReportId(report_id),
                export_format=request_body.export_format,
            ),
            report_ledger=default_report_ledger(),
            run_store=default_harness_run_store(),
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return export.model_dump(mode="json")


@router.post("/reports/{report_id}/finalize")
async def harness_report_finalize(report_id: str) -> JsonObject:
    try:
        report = finalize_report(
            ReportId(report_id),
            report_ledger=default_report_ledger(),
            verification_ledger=default_verification_ledger(),
        )
    except ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReportFinalizationBlockedError as exc:
        verification_id = None if exc.verification is None else str(exc.verification.verification_id)
        raise HTTPException(
            status_code=409,
            detail={
                "error": "report_finalization_blocked",
                "reason": exc.reason,
                "verification_id": verification_id,
            },
        ) from exc
    return report.model_dump(mode="json")
