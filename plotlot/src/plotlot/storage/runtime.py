from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

import anyio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.config import settings
from plotlot.storage.lifecycle import LifecycleExecutor
from plotlot.storage.object_snapshots import SnapshotMetadata, SnapshotReceipt
from plotlot.storage.s3_objects import S3ImmutableObjectStore, S3ObjectStoreConfig


SessionProvider = Callable[[], Awaitable[AsyncSession]]


@dataclass(frozen=True, slots=True)
class StorageRuntime:
    object_store: S3ImmutableObjectStore
    lifecycle: LifecycleExecutor
    session_provider: SessionProvider

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
        receipt = await self.object_store.put_immutable(complete_metadata, content)
        session = await self.session_provider()
        async with session:
            async with session.begin():
                await session.execute(
                    text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                    {"tenant_id": metadata.tenant_id},
                )
                await session.execute(
                    text(
                        """INSERT INTO plotlot.raw_snapshots
                        (tenant_id, snapshot_id, object_key, object_version_id, content_sha256,
                         byte_length, source_uri, fetched_at, encryption_algorithm,
                         encryption_key_id, retain_until, legal_hold)
                        VALUES
                        (:tenant_id, :snapshot_id, :object_key, :object_version_id,
                         :content_sha256, :byte_length, :source_uri, :fetched_at,
                         :encryption_algorithm, :encryption_key_id, :retain_until, :legal_hold)"""
                    ),
                    {
                        "tenant_id": metadata.tenant_id,
                        "snapshot_id": snapshot_id,
                        "object_key": metadata.object_key,
                        "object_version_id": receipt.version_id,
                        "content_sha256": receipt.content_sha256,
                        "byte_length": receipt.byte_length,
                        "source_uri": metadata.source_uri,
                        "fetched_at": metadata.fetched_at,
                        "encryption_algorithm": (
                            "SSE-KMS"
                            if self.object_store.config.sse_kms_key_id is not None
                            else "S3-OBJECT-LOCK"
                        ),
                        "encryption_key_id": metadata.encryption_key_id,
                        "retain_until": retain_until,
                        "legal_hold": metadata.legal_hold,
                    },
                )
        return receipt

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
                            """SELECT tenant_id, object_key, object_version_id, content_sha256,
                        byte_length, source_uri, fetched_at, encryption_key_id,
                        retain_until, legal_hold
                        FROM plotlot.raw_snapshots
                        WHERE tenant_id = :tenant_id AND object_key = :object_key"""
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
        )


_runtime: StorageRuntime | None = None
_runtime_lock = anyio.Lock()


async def build_storage_runtime(
    object_config: S3ObjectStoreConfig,
    session_provider: SessionProvider | None = None,
) -> StorageRuntime:
    if session_provider is None:
        from plotlot.storage.db import get_session

        session_provider = get_session
    object_store = S3ImmutableObjectStore(object_config)
    await object_store.initialize()
    return StorageRuntime(
        object_store=object_store,
        lifecycle=LifecycleExecutor(session_provider, object_store),
        session_provider=session_provider,
    )


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
