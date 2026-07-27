from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.storage.delete_finalize import DeleteOperationFinalizer
from plotlot.storage.delete_prepare import DeleteOperationPreparer
from plotlot.storage.lifecycle import LifecycleReceipt, LifecycleRequest
from plotlot.storage.operation_repository import StorageOperationRepository
from plotlot.storage.operations import StorageOperation, operation_id
from plotlot.storage.put_saga import FailureInjector, no_failure
from plotlot.storage.s3_objects import S3ImmutableObjectStore
from plotlot.storage.s3_types import ObjectLegalHoldError


SessionProvider = Callable[[], Awaitable[AsyncSession]]


class LifecycleExecutor:
    def __init__(
        self,
        session_provider: SessionProvider,
        object_store: S3ImmutableObjectStore,
        operations: StorageOperationRepository,
        failure_injector: FailureInjector = no_failure,
    ) -> None:
        self._object_store = object_store
        self._operations = operations
        self._preparer = DeleteOperationPreparer(session_provider, object_store)
        self._finalizer = DeleteOperationFinalizer(session_provider, failure_injector)
        self._failure_injector = failure_injector

    async def execute(self, request: LifecycleRequest) -> LifecycleReceipt:
        existing = await self._finalizer.receipt(
            request.requesting_tenant_id,
            request.request_id,
        )
        if existing is not None:
            return existing
        identity = operation_id("delete", request.request_id)
        operation = await self._operations.load(request.requesting_tenant_id, identity)
        if operation is None:
            prepared = await self._preparer.prepare(request, identity)
            if isinstance(prepared, LifecycleReceipt):
                return prepared
            operation = prepared
            self._failure_injector("delete_intent_committed")
        return await self._resume(operation)

    async def recover(self, operation: StorageOperation) -> bool:
        if operation.operation_type != "DELETE":
            raise ValueError("delete recovery requires a DELETE operation")
        await self._resume(operation)
        return True

    async def _resume(self, operation: StorageOperation) -> LifecycleReceipt:
        request_id = operation.request_id
        if request_id is None:
            raise RuntimeError("delete operation has no request id")
        existing = await self._finalizer.receipt(operation.tenant_id, request_id)
        if existing is not None:
            return existing
        try:
            await self._object_store.delete_version(operation.receipt())
        except ObjectLegalHoldError:
            return await self._finalizer.cancel_for_hold(operation)
        self._failure_injector("delete_object_deleted")
        receipt = await self._finalizer.delete(operation)
        self._failure_injector("delete_finalized")
        return receipt
