from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.storage.lifecycle import (
    LifecycleReceipt,
    LifecycleRequest,
    RetentionDecision,
)
from plotlot.storage.operations import StorageOperation


async def load_receipt(
    session: AsyncSession,
    tenant_id: str,
    request_id: str,
) -> LifecycleReceipt | None:
    row = (
        (
            await session.execute(
                text(
                    """SELECT tenant_id, request_id, object_key, object_version_id,
                    decision, reason, requested_by, requested_at, completed_at
                    FROM plotlot.lifecycle_receipts
                    WHERE tenant_id=:tenant_id AND request_id=:request_id"""
                ),
                {"tenant_id": tenant_id, "request_id": request_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    return receipt_from_row(row) if row is not None else None


async def insert_receipt(
    session: AsyncSession,
    request: LifecycleRequest,
    version_id: str | None,
    decision: RetentionDecision,
    reason: str,
) -> LifecycleReceipt:
    row = (
        (
            await session.execute(
                text(
                    """INSERT INTO plotlot.lifecycle_receipts
                    (tenant_id, request_id, object_key, object_version_id, decision,
                     reason, requested_by, requested_at)
                    VALUES (:tenant_id, :request_id, :object_key, :version_id, :decision,
                     :reason, :requested_by, :requested_at)
                    RETURNING tenant_id, request_id, object_key, object_version_id,
                     decision, reason, requested_by, requested_at, completed_at"""
                ),
                {
                    "tenant_id": request.requesting_tenant_id,
                    "request_id": request.request_id,
                    "object_key": request.object_key,
                    "version_id": version_id,
                    "decision": decision.value,
                    "reason": reason,
                    "requested_by": request.requested_by,
                    "requested_at": request.requested_at,
                },
            )
        )
        .mappings()
        .one()
    )
    return receipt_from_row(row)


def request_from_operation(operation: StorageOperation) -> LifecycleRequest:
    if operation.request_id is None:
        raise RuntimeError("delete operation has no request id")
    return LifecycleRequest(
        request_id=operation.request_id,
        requesting_tenant_id=operation.tenant_id,
        object_key=operation.object_key,
        requested_by=operation.requested_by,
        requested_at=operation.requested_at,
    )


def receipt_from_row(row) -> LifecycleReceipt:
    return LifecycleReceipt(
        request_id=row["request_id"],
        tenant_id=row["tenant_id"],
        object_key=row["object_key"],
        object_version_id=row["object_version_id"],
        decision=RetentionDecision(row["decision"]),
        reason=row["reason"],
        requested_by=row["requested_by"],
        requested_at=row["requested_at"],
        completed_at=row["completed_at"],
    )
