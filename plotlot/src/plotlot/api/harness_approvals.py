from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from plotlot.harness.approval_store import (
    ApprovalAlreadyResolvedError,
    ApprovalNotFoundError,
    InvalidApprovalDecisionError,
    default_approval_ledger,
)
from plotlot.harness.contracts import (
    ApprovalId,
    ApprovalStatus,
    JsonObject,
    PlotLotEventSource,
    RiskLevel,
    RunId,
)

router = APIRouter(prefix="/api/v1", tags=["harness-approvals"])


class HarnessApprovalRequestBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    requested_action: str = Field(min_length=1)
    risk_level: RiskLevel
    reason: str = Field(min_length=1)
    policy_ids: list[str] = Field(default_factory=list)
    request_payload: JsonObject = Field(default_factory=dict)


class HarnessApprovalDecisionBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    resolved_by: str | None = None
    response_payload: JsonObject = Field(default_factory=dict)


@router.post("/harness/runs/{run_id}/approvals")
async def harness_approval_request(run_id: str, body: HarnessApprovalRequestBody) -> JsonObject:
    approval = default_approval_ledger().request_approval(
        run_id=RunId(run_id),
        requested_action=body.requested_action,
        risk_level=body.risk_level,
        reason=body.reason,
        source=PlotLotEventSource.FRONTEND,
        policy_ids=body.policy_ids,
        request_payload=body.request_payload,
    )
    return approval.model_dump(mode="json")


@router.get("/harness/runs/{run_id}/approvals")
async def harness_approvals_for_run(
    run_id: str,
    status: ApprovalStatus | None = None,
) -> JsonObject:
    approvals = default_approval_ledger().list_approvals(
        run_id=RunId(run_id),
        status=status,
    )
    return {
        "run_id": run_id,
        "approvals": [approval.model_dump(mode="json") for approval in approvals],
    }


@router.get("/harness/approvals/{approval_id}")
async def harness_approval_show(approval_id: str) -> JsonObject:
    try:
        approval = default_approval_ledger().get_approval(ApprovalId(approval_id))
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return approval.model_dump(mode="json")


@router.post("/harness/approvals/{approval_id}/approve")
async def harness_approval_approve(
    approval_id: str,
    body: HarnessApprovalDecisionBody,
) -> JsonObject:
    return _resolve(ApprovalId(approval_id), decision=ApprovalStatus.APPROVED, body=body)


@router.post("/harness/approvals/{approval_id}/deny")
async def harness_approval_deny(
    approval_id: str,
    body: HarnessApprovalDecisionBody,
) -> JsonObject:
    return _resolve(ApprovalId(approval_id), decision=ApprovalStatus.DENIED, body=body)


def _resolve(
    approval_id: ApprovalId,
    *,
    decision: ApprovalStatus,
    body: HarnessApprovalDecisionBody,
) -> JsonObject:
    try:
        approval = default_approval_ledger().resolve_approval(
            approval_id,
            decision=decision,
            resolved_by=body.resolved_by,
            response_payload=body.response_payload,
            source=PlotLotEventSource.FRONTEND,
        )
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalAlreadyResolvedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InvalidApprovalDecisionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return approval.model_dump(mode="json")
