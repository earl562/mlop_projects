from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.storage.lifecycle import LifecycleReceipt, RetentionDecision
from plotlot.storage.lifecycle_receipts import (
    insert_receipt,
    load_receipt,
    request_from_operation,
)
from plotlot.storage.operation_repository import lock_object, set_tenant
from plotlot.storage.operations import StorageOperation
from plotlot.storage.put_saga import FailureInjector


SessionProvider = Callable[[], Awaitable[AsyncSession]]


class DeleteOperationFinalizer:
    def __init__(
        self,
        session_provider: SessionProvider,
        failure_injector: FailureInjector,
    ) -> None:
        self._session_provider = session_provider
        self._failure_injector = failure_injector

    async def receipt(self, tenant_id: str, request_id: str) -> LifecycleReceipt | None:
        session = await self._session_provider()
        async with session:
            await set_tenant(session, tenant_id)
            return await load_receipt(session, tenant_id, request_id)

    async def delete(self, operation: StorageOperation) -> LifecycleReceipt:
        session = await self._session_provider()
        async with session:
            async with session.begin():
                await set_tenant(session, operation.tenant_id)
                await lock_object(session, operation.tenant_id, operation.object_key)
                request = request_from_operation(operation)
                existing = await load_receipt(session, operation.tenant_id, request.request_id)
                if existing is not None:
                    return existing
                deleted = await session.scalar(
                    text(
                        """SELECT plotlot.delete_expired_snapshot(
                          :tenant_id, :object_key, :version_id, :operation_id, :requested_at
                        )"""
                    ),
                    _function_parameters(operation),
                )
                if deleted is not True:
                    raise RuntimeError("database lifecycle delete was not applied")
                receipt = await insert_receipt(
                    session,
                    request,
                    operation.object_version_id,
                    RetentionDecision.DELETE,
                    "tenant_payload_deleted",
                )
                await _finalize_operation(session, operation)
                self._failure_injector("delete_finalize_transaction")
                return receipt

    async def cancel_for_hold(self, operation: StorageOperation) -> LifecycleReceipt:
        session = await self._session_provider()
        async with session:
            async with session.begin():
                await set_tenant(session, operation.tenant_id)
                cancelled = await session.scalar(
                    text(
                        """SELECT plotlot.cancel_snapshot_deleting(
                          :tenant_id, :object_key, :version_id, :operation_id
                        )"""
                    ),
                    _function_parameters(operation),
                )
                if cancelled is not True:
                    raise RuntimeError("snapshot delete tombstone was not cancelled")
                receipt = await insert_receipt(
                    session,
                    request_from_operation(operation),
                    operation.object_version_id,
                    RetentionDecision.HOLD,
                    "object_legal_hold",
                )
                await _finalize_operation(session, operation)
                return receipt


async def _finalize_operation(
    session: AsyncSession,
    operation: StorageOperation,
) -> None:
    finalized = await session.scalar(
        text(
            """SELECT plotlot.finalize_storage_operation(
              :tenant_id, :operation_id
            )"""
        ),
        {"tenant_id": operation.tenant_id, "operation_id": operation.operation_id},
    )
    if finalized is not True:
        raise RuntimeError("delete operation was not finalized")


def _function_parameters(operation: StorageOperation) -> dict[str, object]:
    return {
        "tenant_id": operation.tenant_id,
        "object_key": operation.object_key,
        "version_id": operation.object_version_id,
        "operation_id": operation.operation_id,
        "requested_at": operation.requested_at,
    }
