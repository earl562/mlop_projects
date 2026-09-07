from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.storage.lifecycle import (
    LifecycleReceipt,
    LifecycleRequest,
    RetentionDecision,
)
from plotlot.storage.lifecycle_receipts import insert_receipt
from plotlot.storage.object_snapshots import SnapshotReceipt
from plotlot.storage.operation_repository import (
    OPERATION_COLUMNS,
    load_in_session,
    lock_object,
    operation_from_row,
    set_tenant,
)
from plotlot.storage.operations import StorageOperation
from plotlot.storage.s3_objects import S3ImmutableObjectStore


SessionProvider = Callable[[], Awaitable[AsyncSession]]


class DeleteOperationPreparer:
    def __init__(
        self,
        session_provider: SessionProvider,
        object_store: S3ImmutableObjectStore,
    ) -> None:
        self._session_provider = session_provider
        self._object_store = object_store

    async def prepare(
        self,
        request: LifecycleRequest,
        identity: str,
    ) -> StorageOperation | LifecycleReceipt:
        session = await self._session_provider()
        async with session:
            async with session.begin():
                await set_tenant(session, request.requesting_tenant_id)
                await lock_object(session, request.requesting_tenant_id, request.object_key)
                existing = await load_in_session(
                    session,
                    request.requesting_tenant_id,
                    identity,
                )
                if existing is not None:
                    return existing
                snapshot = await self._snapshot(session, request)
                terminal = await self._terminal_decision(session, request, snapshot)
                if terminal is not None:
                    return terminal
                operation = await self._insert_operation(session, request, identity, snapshot)
                marked = await session.scalar(
                    text(
                        """SELECT plotlot.mark_snapshot_deleting(
                          :tenant_id, :object_key, :version_id, :operation_id
                        )"""
                    ),
                    {
                        "tenant_id": operation.tenant_id,
                        "object_key": operation.object_key,
                        "version_id": operation.object_version_id,
                        "operation_id": operation.operation_id,
                    },
                )
                if marked is not True:
                    raise RuntimeError("snapshot delete tombstone was not applied")
                return operation

    async def _terminal_decision(
        self,
        session: AsyncSession,
        request: LifecycleRequest,
        snapshot,
    ) -> LifecycleReceipt | None:
        if snapshot is None:
            return await insert_receipt(
                session,
                request,
                None,
                RetentionDecision.DENY,
                "tenant_object_not_found",
            )
        version_id = snapshot["object_version_id"]
        if snapshot["lifecycle_state"] != "ACTIVE":
            return await insert_receipt(
                session,
                request,
                version_id,
                RetentionDecision.DENY,
                "delete_in_progress",
            )
        if snapshot["legal_hold"]:
            return await insert_receipt(
                session,
                request,
                version_id,
                RetentionDecision.HOLD,
                "database_legal_hold",
            )
        if request.requested_at < snapshot["retain_until"]:
            return await insert_receipt(
                session,
                request,
                version_id,
                RetentionDecision.KEEP,
                "retention_window_active",
            )
        if await self._object_store.is_legal_hold_enabled(_snapshot_receipt(snapshot)):
            return await insert_receipt(
                session,
                request,
                version_id,
                RetentionDecision.HOLD,
                "object_legal_hold",
            )
        return None

    async def _snapshot(self, session: AsyncSession, request: LifecycleRequest):
        return (
            (
                await session.execute(
                    text(
                        """SELECT tenant_id, snapshot_id, object_key, object_version_id,
                        content_sha256, byte_length, source_uri, fetched_at,
                        encryption_algorithm, encryption_key_id, retain_until,
                        legal_hold, lifecycle_state
                        FROM plotlot.raw_snapshots
                        WHERE tenant_id=:tenant_id AND object_key=:object_key"""
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

    async def _insert_operation(
        self,
        session: AsyncSession,
        request: LifecycleRequest,
        identity: str,
        snapshot,
    ) -> StorageOperation:
        row = (
            (
                await session.execute(
                    text(
                        f"""INSERT INTO plotlot.storage_operations
                        (tenant_id, operation_id, operation_type, status, object_key,
                         snapshot_id, content_sha256, byte_length, source_uri, fetched_at,
                         encryption_algorithm, encryption_key_id, retain_until, legal_hold,
                         object_version_id, request_id, requested_by, requested_at)
                        VALUES (:tenant_id, :operation_id, 'DELETE', 'INTENT', :object_key,
                         :snapshot_id, :content_sha256, :byte_length, :source_uri, :fetched_at,
                         :encryption_algorithm, :encryption_key_id, :retain_until, :legal_hold,
                         :object_version_id, :request_id, :requested_by, :requested_at)
                        RETURNING {OPERATION_COLUMNS}"""
                    ),
                    {
                        **dict(snapshot),
                        "operation_id": identity,
                        "request_id": request.request_id,
                        "requested_by": request.requested_by,
                        "requested_at": request.requested_at,
                    },
                )
            )
            .mappings()
            .one()
        )
        return operation_from_row(row)


def _snapshot_receipt(snapshot) -> SnapshotReceipt:
    return SnapshotReceipt(
        tenant_id=snapshot["tenant_id"],
        object_key=snapshot["object_key"],
        source_uri=snapshot["source_uri"],
        fetched_at=snapshot["fetched_at"],
        encryption_key_id=snapshot["encryption_key_id"],
        content_sha256=snapshot["content_sha256"],
        byte_length=snapshot["byte_length"],
        version_id=snapshot["object_version_id"],
        physical_key=f"tenants/{snapshot['tenant_id']}/{snapshot['object_key']}",
        retain_until=snapshot["retain_until"],
        legal_hold=snapshot["legal_hold"],
    )
