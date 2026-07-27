from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.storage.object_snapshots import SnapshotReceipt
from plotlot.storage.s3_objects import ObjectLegalHoldError, S3ImmutableObjectStore


class RetentionDecision(StrEnum):
    KEEP = "keep"
    DELETE = "delete"
    HOLD = "hold"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class LifecycleRecord:
    tenant_id: str
    object_key: str
    retain_until: datetime
    legal_hold: bool
    deletion_requested_at: datetime | None


@dataclass(frozen=True, slots=True)
class LifecycleRequest:
    request_id: str
    requesting_tenant_id: str
    object_key: str
    requested_by: str
    requested_at: datetime


@dataclass(frozen=True, slots=True)
class LifecycleReceipt:
    request_id: str
    tenant_id: str
    object_key: str
    object_version_id: str | None
    decision: RetentionDecision
    reason: str
    requested_by: str
    requested_at: datetime
    completed_at: datetime


def decide_retention(
    requesting_tenant_id: str,
    record: LifecycleRecord,
    now: datetime,
) -> RetentionDecision:
    if requesting_tenant_id != record.tenant_id:
        return RetentionDecision.DENY
    if record.legal_hold:
        return RetentionDecision.HOLD
    if record.deletion_requested_at is None or now < record.retain_until:
        return RetentionDecision.KEEP
    return RetentionDecision.DELETE


SessionProvider = Callable[[], Awaitable[AsyncSession]]


class LifecycleExecutor:
    def __init__(
        self,
        session_provider: SessionProvider,
        object_store: S3ImmutableObjectStore,
    ) -> None:
        self._session_provider = session_provider
        self._object_store = object_store

    async def execute(self, request: LifecycleRequest) -> LifecycleReceipt:
        session = await self._session_provider()
        async with session:
            async with session.begin():
                await session.execute(
                    text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                    {"tenant_id": request.requesting_tenant_id},
                )
                existing = (
                    (
                        await session.execute(
                            text(
                                """SELECT tenant_id, request_id, object_key, object_version_id,
                            decision, reason, requested_by, requested_at, completed_at
                            FROM plotlot.lifecycle_receipts
                            WHERE tenant_id = :tenant_id AND request_id = :request_id"""
                            ),
                            {
                                "tenant_id": request.requesting_tenant_id,
                                "request_id": request.request_id,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing is not None:
                    return self._receipt_from_row(existing)

                await session.execute(
                    text(
                        """SELECT pg_advisory_xact_lock(
                          hashtextextended(:tenant_id || '|' || :object_key, 0)
                        )"""
                    ),
                    {
                        "tenant_id": request.requesting_tenant_id,
                        "object_key": request.object_key,
                    },
                )
                snapshot = (
                    (
                        await session.execute(
                            text(
                                """SELECT tenant_id, object_key, object_version_id, content_sha256,
                            byte_length, source_uri, fetched_at, encryption_key_id,
                            retain_until, legal_hold
                            FROM plotlot.raw_snapshots
                            WHERE tenant_id = :tenant_id AND object_key = :object_key"""
                            ),
                            {
                                "tenant_id": request.requesting_tenant_id,
                                "object_key": request.object_key,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                decision, reason = await self._apply_decision(session, request, snapshot)
                inserted = (
                    (
                        await session.execute(
                            text(
                                """INSERT INTO plotlot.lifecycle_receipts
                            (tenant_id, request_id, object_key, object_version_id, decision,
                             reason, requested_by, requested_at)
                            VALUES
                            (:tenant_id, :request_id, :object_key, :object_version_id, :decision,
                             :reason, :requested_by, :requested_at)
                            RETURNING tenant_id, request_id, object_key, object_version_id,
                            decision, reason, requested_by, requested_at, completed_at"""
                            ),
                            {
                                "tenant_id": request.requesting_tenant_id,
                                "request_id": request.request_id,
                                "object_key": request.object_key,
                                "object_version_id": (
                                    snapshot["object_version_id"] if snapshot is not None else None
                                ),
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
                return self._receipt_from_row(inserted)

    async def _apply_decision(
        self,
        session: AsyncSession,
        request: LifecycleRequest,
        snapshot,
    ) -> tuple[RetentionDecision, str]:
        if snapshot is None:
            return RetentionDecision.DENY, "tenant_object_not_found"
        if snapshot["legal_hold"]:
            return RetentionDecision.HOLD, "database_legal_hold"
        if request.requested_at < snapshot["retain_until"]:
            return RetentionDecision.KEEP, "retention_window_active"
        version_id = snapshot["object_version_id"]
        if not isinstance(version_id, str) or not version_id:
            return RetentionDecision.DENY, "object_version_missing"
        receipt = SnapshotReceipt(
            tenant_id=snapshot["tenant_id"],
            object_key=snapshot["object_key"],
            source_uri=snapshot["source_uri"],
            fetched_at=snapshot["fetched_at"],
            encryption_key_id=snapshot["encryption_key_id"],
            content_sha256=snapshot["content_sha256"],
            byte_length=snapshot["byte_length"],
            version_id=version_id,
            physical_key=self._object_store.physical_key(
                snapshot["tenant_id"],
                snapshot["object_key"],
            ),
            retain_until=snapshot["retain_until"],
            legal_hold=snapshot["legal_hold"],
        )
        try:
            await self._object_store.delete_version(receipt)
        except ObjectLegalHoldError:
            return RetentionDecision.HOLD, "object_legal_hold"
        deleted = await session.scalar(
            text(
                """SELECT plotlot.delete_expired_snapshot(
                  :tenant_id, :object_key, :object_version_id, :requested_at
                )"""
            ),
            {
                "tenant_id": request.requesting_tenant_id,
                "object_key": request.object_key,
                "object_version_id": version_id,
                "requested_at": request.requested_at,
            },
        )
        if deleted is not True:
            raise RuntimeError("database lifecycle delete was not applied")
        return RetentionDecision.DELETE, "tenant_payload_deleted"

    @staticmethod
    def _receipt_from_row(row) -> LifecycleReceipt:
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
