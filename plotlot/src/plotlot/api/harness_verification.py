from __future__ import annotations

from fastapi import APIRouter, HTTPException

from plotlot.harness.contracts import JsonObject, ReportId, RunId, VerificationId, VerificationResult
from plotlot.harness.report_store import ReportNotFoundError, default_report_ledger
from plotlot.harness.verification_inspection import verification_payload
from plotlot.harness.verification_store import VerificationNotFoundError, default_verification_ledger

router = APIRouter(prefix="/api/v1", tags=["harness-verification"])


@router.get("/harness/runs/{run_id}/verification")
async def harness_run_verification(run_id: str) -> JsonObject:
    results = default_verification_ledger().list_verifications(run_id=RunId(run_id))
    if not results:
        raise HTTPException(status_code=404, detail="Verification not found")
    return _verification_response(results[-1])


@router.get("/verification/{verification_id}")
async def harness_verification(verification_id: str) -> JsonObject:
    try:
        result = default_verification_ledger().get_verification(VerificationId(verification_id))
    except VerificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _verification_response(result)


@router.get("/reports/{report_id}/verification")
async def harness_report_verification(report_id: str) -> JsonObject:
    try:
        result = default_verification_ledger().get_latest_for_report(ReportId(report_id))
    except VerificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _verification_response(result)


def _verification_response(result: VerificationResult) -> JsonObject:
    try:
        report = default_report_ledger().get_report(result.report_id)
    except ReportNotFoundError:
        report = None
    return verification_payload(result, report=report)
