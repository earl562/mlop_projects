from __future__ import annotations

from fastapi import APIRouter, HTTPException

from plotlot.harness.contracts import EvidenceId, JsonObject, RunId
from plotlot.harness.evidence_store import EvidenceNotFoundError, default_evidence_ledger

router = APIRouter(prefix="/api/v1", tags=["harness-evidence"])


@router.get("/harness/runs/{run_id}/evidence")
async def harness_run_evidence(run_id: str) -> JsonObject:
    evidence = default_evidence_ledger().list_evidence(run_id=RunId(run_id))
    return {"run_id": run_id, "evidence": [item.model_dump(mode="json") for item in evidence]}


@router.get("/evidence/{evidence_id}")
async def harness_evidence(evidence_id: str) -> JsonObject:
    try:
        item = default_evidence_ledger().get_evidence(EvidenceId(evidence_id))
    except EvidenceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return item.model_dump(mode="json")
