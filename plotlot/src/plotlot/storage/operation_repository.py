from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.storage.object_snapshots import ObjectConflictError, SnapshotMetadata
from plotlot.storage.operations import StorageOperation


SessionProvider = Callable[[], Awaitable[AsyncSession]]
OPERATION_COLUMNS = """tenant_id, operation_id, operation_type, status, object_key,
snapshot_id, content_sha256, byte_length, source_uri, fetched_at, encryption_algorithm,
encryption_key_id, retain_until, legal_hold, object_version_id, request_id,
requested_by, requested_at"""


class StorageOperationRepository:
    def __init__(self, session_provider: SessionProvider) -> None:
        self._session_provider = session_provider

    async def session(self) -> AsyncSession:
        return await self._session_provider()

    async def begin_put(
        self,
        identity: str,
        snapshot_id: str,
        metadata: SnapshotMetadata,
        digest: str,
        byte_length: int,
        encryption_algorithm: str,
    ) -> StorageOperation:
        session = await self._session_provider()
        async with session:
            async with session.begin():
                await set_tenant(session, metadata.tenant_id)
                await lock_object(session, metadata.tenant_id, metadata.object_key)
                existing = await load_in_session(session, metadata.tenant_id, identity)
                if existing is not None:
                    if (
                        existing.operation_type != "PUT"
                        or existing.snapshot_id != snapshot_id
                        or existing.object_key != metadata.object_key
                        or existing.content_sha256 != digest
                        or existing.byte_length != byte_length
                    ):
                        raise ObjectConflictError(metadata.tenant_id, metadata.object_key)
                    return existing
                active = await session.scalar(
                    text(
                        """SELECT EXISTS(
                          SELECT 1 FROM plotlot.raw_snapshots
                          WHERE tenant_id=:tenant_id AND object_key=:object_key
                        )"""
                    ),
                    {"tenant_id": metadata.tenant_id, "object_key": metadata.object_key},
                )
                if active:
                    raise ObjectConflictError(metadata.tenant_id, metadata.object_key)
                pending = await session.scalar(
                    text(
                        """SELECT EXISTS(
                          SELECT 1 FROM plotlot.storage_operations
                          WHERE tenant_id=:tenant_id AND object_key=:object_key
                            AND status <> 'FINALIZED'
                        )"""
                    ),
                    {"tenant_id": metadata.tenant_id, "object_key": metadata.object_key},
                )
                if pending:
                    raise ObjectConflictError(metadata.tenant_id, metadata.object_key)
                row = (
                    (
                        await session.execute(
                            text(
                                f"""INSERT INTO plotlot.storage_operations
                                (tenant_id, operation_id, operation_type, status, object_key,
                                 snapshot_id, content_sha256, byte_length, source_uri, fetched_at,
                                 encryption_algorithm, encryption_key_id, retain_until, legal_hold,
                                 requested_by, requested_at)
                                VALUES (:tenant_id, :operation_id, 'PUT', 'INTENT', :object_key,
                                 :snapshot_id, :digest, :byte_length, :source_uri, :fetched_at,
                                 :algorithm, :key_id, :retain_until, :legal_hold,
                                 'storage-runtime', now()) RETURNING {OPERATION_COLUMNS}"""
                            ),
                            {
                                "tenant_id": metadata.tenant_id,
                                "operation_id": identity,
                                "object_key": metadata.object_key,
                                "snapshot_id": snapshot_id,
                                "digest": digest,
                                "byte_length": byte_length,
                                "source_uri": metadata.source_uri,
                                "fetched_at": metadata.fetched_at,
                                "algorithm": encryption_algorithm,
                                "key_id": metadata.encryption_key_id,
                                "retain_until": metadata.retain_until,
                                "legal_hold": metadata.legal_hold,
                            },
                        )
                    )
                    .mappings()
                    .one()
                )
                return operation_from_row(row)

    async def record_version(
        self,
        tenant_id: str,
        identity: str,
        version_id: str,
    ) -> StorageOperation:
        session = await self._session_provider()
        async with session:
            async with session.begin():
                await set_tenant(session, tenant_id)
                recorded = await session.scalar(
                    text(
                        """SELECT plotlot.record_storage_version(
                          :tenant_id, :operation_id, :version_id
                        )"""
                    ),
                    {
                        "tenant_id": tenant_id,
                        "operation_id": identity,
                        "version_id": version_id,
                    },
                )
                if recorded is not True:
                    raise RuntimeError("object version was not recorded")
                operation = await load_in_session(session, tenant_id, identity)
                if operation is None:
                    raise RuntimeError("storage operation disappeared")
                return operation

    async def load(self, tenant_id: str, identity: str) -> StorageOperation | None:
        session = await self._session_provider()
        async with session:
            await set_tenant(session, tenant_id)
            return await load_in_session(session, tenant_id, identity)

    async def pending(self, tenant_id: str, limit: int) -> list[StorageOperation]:
        if limit < 1 or limit > 100:
            raise ValueError("recovery limit must be between 1 and 100")
        session = await self._session_provider()
        async with session:
            await set_tenant(session, tenant_id)
            rows = (
                (
                    await session.execute(
                        text(
                            f"""SELECT {OPERATION_COLUMNS}
                            FROM plotlot.storage_operations
                            WHERE tenant_id=:tenant_id AND status <> 'FINALIZED'
                            ORDER BY created_at, operation_id LIMIT :limit"""
                        ),
                        {"tenant_id": tenant_id, "limit": limit},
                    )
                )
                .mappings()
                .all()
            )
            return [operation_from_row(row) for row in rows]


async def load_in_session(
    session: AsyncSession,
    tenant_id: str,
    identity: str,
) -> StorageOperation | None:
    row = (
        (
            await session.execute(
                text(
                    f"""SELECT {OPERATION_COLUMNS} FROM plotlot.storage_operations
                    WHERE tenant_id=:tenant_id AND operation_id=:operation_id"""
                ),
                {"tenant_id": tenant_id, "operation_id": identity},
            )
        )
        .mappings()
        .one_or_none()
    )
    return operation_from_row(row) if row is not None else None


async def set_tenant(session: AsyncSession, tenant_id: str) -> None:
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": tenant_id},
    )


async def lock_object(session: AsyncSession, tenant_id: str, object_key: str) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock_shared(hashtextextended('plotlot-storage-backup', 0))")
    )
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 0))"),
        {"identity": f"{tenant_id}|{object_key}"},
    )


def operation_from_row(row) -> StorageOperation:
    return StorageOperation(**dict(row))
