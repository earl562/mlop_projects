"""Approval API for governed tool actions.

This is the minimal persistence surface to support:
- tool calls that emit pending approvals
- a user (or UI) approving/rejecting them
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from plotlot.storage.db import get_session
from plotlot.storage.models import ApprovalRequest


router = APIRouter(prefix="/api/v1", tags=["approvals"])


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject)$")
    response_json: dict = Field(default_factory=dict)


class ApprovalActionRequest(BaseModel):
    response_json: dict = Field(default_factory=dict)


@router.post("/approvals/{approval_id}/decision")
async def decide_approval(
    approval_id: str,
    body: ApprovalDecisionRequest,
    request: Request,
):
    session = await get_session()
    try:
        approval = await session.get(ApprovalRequest, approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail="Approval not found")

        if approval.status != "pending":
            raise HTTPException(status_code=409, detail="Approval is already decided")

        if approval.expires_at is not None and approval.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=409, detail="Approval has expired")

        approval.status = "approved" if body.decision == "approve" else "rejected"  # type: ignore[assignment]
        approval.decided_by = request.state.actor.user_id  # type: ignore[assignment]
        approval.decided_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        approval.response_json = body.response_json or {}  # type: ignore[assignment]
        await session.commit()
        return {
            "status": approval.status,
            "approval_id": approval.id,
        }
    finally:
        await session.close()


@router.post("/approvals/{approval_id}/approve")
async def approve_approval(
    approval_id: str,
    body: ApprovalActionRequest,
    request: Request,
):
    return await decide_approval(
        approval_id,
        ApprovalDecisionRequest(
            decision="approve",
            response_json=body.response_json,
        ),
        request,
    )


@router.post("/approvals/{approval_id}/reject")
async def reject_approval(
    approval_id: str,
    body: ApprovalActionRequest,
    request: Request,
):
    return await decide_approval(
        approval_id,
        ApprovalDecisionRequest(
            decision="reject",
            response_json=body.response_json,
        ),
        request,
    )


@router.get("/approvals/{approval_id}")
async def get_approval(approval_id: str):
    session = await get_session()
    try:
        approval = await session.get(ApprovalRequest, approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail="Approval not found")
        return {
            "approval_id": approval.id,
            "status": approval.status,
            "risk_class": approval.risk_class,
            "action_name": approval.action_name,
            "reason": approval.reason,
            "request_json": approval.request_json,
            "response_json": approval.response_json,
        }
    finally:
        await session.close()
