from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256

from sqlalchemy import text

from plotlot.storage.object_snapshots import SnapshotMetadata, SnapshotReceipt
from plotlot.storage.operation_repository import (
    StorageOperationRepository,
    load_in_session,
    lock_object,
    set_tenant,
)
from plotlot.storage.operations import StorageOperation, operation_id
from plotlot.storage.s3_saga import S3OperationWriter


FailureInjector = Callable[[str], None]


def no_failure(_: str) -> None:
    return None


class PutOperationSaga:
    def __init__(
        self,
        repository: StorageOperationRepository,
        writer: S3OperationWriter,
        failure_injector: FailureInjector = no_failure,
    ) -> None:
        self._repository = repository
        self._writer = writer
        self._failure_injector = failure_injector

    async def store(
        self,
        snapshot_id: str,
        metadata: SnapshotMetadata,
        content: bytes,
        encryption_algorithm: str,
    ) -> SnapshotReceipt:
        identity = operation_id("put", snapshot_id)
        digest = sha256(content).hexdigest()
        operation = await self._repository.begin_put(
            identity,
            snapshot_id,
            metadata,
            digest,
            len(content),
            encryption_algorithm,
        )
        if operation.status == "FINALIZED":
            return operation.receipt()
        self._failure_injector("put_intent_committed")
        operation = await self._ensure_version(operation, content)
        operation = await self._finalize(operation)
        self._failure_injector("put_finalized")
        return operation.receipt()

    async def recover(self, operation: StorageOperation) -> bool:
        if operation.operation_type != "PUT":
            raise ValueError("put recovery requires a PUT operation")
        if operation.object_version_id is None:
            adopted = await self._writer.adopt_existing(
                operation.operation_id,
                operation.metadata(),
                operation.content_sha256,
                operation.byte_length,
            )
            if adopted is None:
                return False
            operation = await self._repository.record_version(
                operation.tenant_id,
                operation.operation_id,
                adopted.version_id,
            )
        await self._finalize(operation)
        return True

    async def _ensure_version(
        self,
        operation: StorageOperation,
        content: bytes,
    ) -> StorageOperation:
        if operation.object_version_id is not None:
            return operation
        receipt = await self._writer.put_or_adopt(
            operation.operation_id,
            operation.metadata(),
            content,
        )
        self._failure_injector("put_object_written")
        operation = await self._repository.record_version(
            operation.tenant_id,
            operation.operation_id,
            receipt.version_id,
        )
        self._failure_injector("put_version_persisted")
        return operation

    async def _finalize(self, operation: StorageOperation) -> StorageOperation:
        session = await self._repository.session()
        async with session:
            async with session.begin():
                await set_tenant(session, operation.tenant_id)
                await lock_object(session, operation.tenant_id, operation.object_key)
                current = await load_in_session(
                    session,
                    operation.tenant_id,
                    operation.operation_id,
                )
                if current is None or current.object_version_id is None:
                    raise RuntimeError("put operation is not ready to finalize")
                if current.status == "FINALIZED":
                    return current
                await session.execute(
                    text(
                        """INSERT INTO plotlot.raw_snapshots
                        (tenant_id, snapshot_id, object_key, object_version_id,
                         content_sha256, byte_length, source_uri, fetched_at,
                         encryption_algorithm, encryption_key_id, retain_until,
                         legal_hold, lifecycle_state)
                        VALUES (:tenant_id, :snapshot_id, :object_key, :object_version_id,
                         :content_sha256, :byte_length, :source_uri, :fetched_at,
                         :encryption_algorithm, :encryption_key_id, :retain_until,
                         :legal_hold, 'ACTIVE')"""
                    ),
                    _operation_parameters(current),
                )
                finalized_result = await session.scalar(
                    text(
                        """SELECT plotlot.finalize_storage_operation(
                          :tenant_id, :operation_id
                        )"""
                    ),
                    {
                        "tenant_id": current.tenant_id,
                        "operation_id": current.operation_id,
                    },
                )
                if finalized_result is not True:
                    raise RuntimeError("put operation was not finalized")
                finalized = await load_in_session(
                    session,
                    current.tenant_id,
                    current.operation_id,
                )
                if finalized is None:
                    raise RuntimeError("finalized put operation disappeared")
                self._failure_injector("put_finalize_transaction")
                return finalized


def _operation_parameters(operation: StorageOperation) -> dict[str, object]:
    return {
        "tenant_id": operation.tenant_id,
        "snapshot_id": operation.snapshot_id,
        "object_key": operation.object_key,
        "object_version_id": operation.object_version_id,
        "content_sha256": operation.content_sha256,
        "byte_length": operation.byte_length,
        "source_uri": operation.source_uri,
        "fetched_at": operation.fetched_at,
        "encryption_algorithm": operation.encryption_algorithm,
        "encryption_key_id": operation.encryption_key_id,
        "retain_until": operation.retain_until,
        "legal_hold": operation.legal_hold,
    }
