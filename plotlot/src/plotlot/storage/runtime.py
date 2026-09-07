from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import timedelta

import anyio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.config import settings
from plotlot.storage.delete_saga import LifecycleExecutor
from plotlot.storage.object_snapshots import SnapshotMetadata, SnapshotReceipt
from plotlot.storage.operation_repository import StorageOperationRepository
from plotlot.storage.put_saga import FailureInjector, PutOperationSaga, no_failure
from plotlot.storage.s3_objects import S3ImmutableObjectStore, S3ObjectStoreConfig
from plotlot.storage.s3_saga import S3OperationWriter


SessionProvider = Callable[[], Awaitable[AsyncSession]]


@dataclass(frozen=True, slots=True)
class StorageRuntime:
    object_store: S3ImmutableObjectStore
    lifecycle: LifecycleExecutor
    session_provider: SessionProvider
    operations: StorageOperationRepository
    put_saga: PutOperationSaga

    async def store_snapshot(
        self,
        snapshot_id: str,
        metadata: SnapshotMetadata,
        content: bytes,
    ) -> SnapshotReceipt:
        retain_until = metadata.retain_until or metadata.fetched_at + timedelta(days=365)
        complete_metadata = SnapshotMetadata(
            tenant_id=metadata.tenant_id,
            object_key=metadata.object_key,
            source_uri=metadata.source_uri,
            fetched_at=metadata.fetched_at,
            encryption_key_id=metadata.encryption_key_id,
            retain_until=retain_until,
            legal_hold=metadata.legal_hold,
        )
        algorithm = (
            "SSE-KMS" if self.object_store.config.sse_kms_key_id is not None else "S3-OBJECT-LOCK"
        )
        return await self.put_saga.store(snapshot_id, complete_metadata, content, algorithm)

    async def read_snapshot(self, tenant_id: str, object_key: str) -> bytes:
        receipt = await self.load_snapshot_receipt(tenant_id, object_key)
        return await self.object_store.get_verified(receipt)

    async def snapshot_exists(self, tenant_id: str, object_key: str) -> bool:
        session = await self.session_provider()
        async with session:
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, false)"),
                {"tenant_id": tenant_id},
            )
            result = await session.execute(
                text(
                    """SELECT EXISTS(
                      SELECT 1 FROM plotlot.raw_snapshots
                      WHERE tenant_id = :tenant_id AND object_key = :object_key
                        AND lifecycle_state = 'ACTIVE'
                    )"""
                ),
                {"tenant_id": tenant_id, "object_key": object_key},
            )
            return bool(result.scalar_one())

    async def load_snapshot_receipt(
        self,
        tenant_id: str,
        object_key: str,
    ) -> SnapshotReceipt:
        session = await self.session_provider()
        async with session:
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, false)"),
                {"tenant_id": tenant_id},
            )
            row = (
                (
                    await session.execute(
                        text(
                            """SELECT r.tenant_id, r.object_key, r.object_version_id,
                        r.content_sha256, r.byte_length, r.source_uri, r.fetched_at,
                        r.encryption_key_id, r.retain_until, r.legal_hold,
                        CASE WHEN o.operation_id LIKE 'legacy-put-%'
                          THEN '' ELSE o.operation_id END AS operation_id
                        FROM plotlot.raw_snapshots r
                        JOIN plotlot.storage_operations o
                          ON o.tenant_id=r.tenant_id AND o.object_key=r.object_key
                         AND o.object_version_id=r.object_version_id
                         AND o.operation_type='PUT' AND o.status='FINALIZED'
                        WHERE r.tenant_id = :tenant_id AND r.object_key = :object_key
                          AND r.lifecycle_state = 'ACTIVE'"""
                        ),
                        {"tenant_id": tenant_id, "object_key": object_key},
                    )
                )
                .mappings()
                .one()
            )
        version_id = row["object_version_id"]
        if not isinstance(version_id, str) or not version_id:
            raise RuntimeError("snapshot database receipt has no object version")
        return SnapshotReceipt(
            tenant_id=row["tenant_id"],
            object_key=row["object_key"],
            source_uri=row["source_uri"],
            fetched_at=row["fetched_at"],
            encryption_key_id=row["encryption_key_id"],
            content_sha256=row["content_sha256"],
            byte_length=row["byte_length"],
            version_id=version_id,
            physical_key=self.object_store.physical_key(row["tenant_id"], row["object_key"]),
            retain_until=row["retain_until"],
            legal_hold=row["legal_hold"],
            operation_id=row["operation_id"],
        )

    async def recover_pending_operations(self, tenant_id: str, limit: int = 100) -> int:
        recovered = 0
        for operation in await self.operations.pending(tenant_id, limit):
            if operation.operation_type == "PUT":
                recovered += int(await self.put_saga.recover(operation))
            else:
                recovered += int(await self.lifecycle.recover(operation))
        return recovered


_runtime: StorageRuntime | None = None
_runtime_lock = anyio.Lock()


async def build_storage_runtime(
    object_config: S3ObjectStoreConfig,
    session_provider: SessionProvider | None = None,
    failure_injector: FailureInjector = no_failure,
) -> StorageRuntime:
    if session_provider is None:
        from plotlot.storage.db import get_session

        session_provider = get_session
    object_config = replace(
        object_config,
        bucket=await _active_bucket(session_provider, object_config.bucket),
    )
    object_store = S3ImmutableObjectStore(object_config)
    await object_store.initialize()
    operations = StorageOperationRepository(session_provider)
    writer = S3OperationWriter(object_store)
    put_saga = PutOperationSaga(operations, writer, failure_injector)
    return StorageRuntime(
        object_store=object_store,
        lifecycle=LifecycleExecutor(
            session_provider,
            object_store,
            operations,
            failure_injector,
        ),
        session_provider=session_provider,
        operations=operations,
        put_saga=put_saga,
    )


async def _active_bucket(session_provider: SessionProvider, configured_bucket: str) -> str:
    session = await session_provider()
    async with session:
        bucket = await session.scalar(text("SELECT bucket FROM plotlot.active_storage_generation"))
    return bucket if isinstance(bucket, str) and bucket else configured_bucket


async def initialize_configured_storage_runtime() -> StorageRuntime | None:
    global _runtime
    if not settings.object_store_enabled:
        return None
    async with _runtime_lock:
        if _runtime is None:
            _runtime = await build_storage_runtime(
                S3ObjectStoreConfig(
                    endpoint_url=settings.object_store_endpoint_url,
                    bucket=settings.object_store_bucket,
                    access_key_id=settings.object_store_access_key_id,
                    secret_access_key=settings.object_store_secret_access_key,
                    region=settings.object_store_region,
                    sse_kms_key_id=settings.object_store_sse_kms_key_id or None,
                )
            )
    return _runtime


def get_storage_runtime() -> StorageRuntime:
    if _runtime is None:
        raise RuntimeError("storage runtime is not initialized")
    return _runtime
