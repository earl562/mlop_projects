from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.exc import NoResultFound

from plotlot.storage.lifecycle import LifecycleRequest, RetentionDecision
from plotlot.storage.object_snapshots import ObjectConflictError, SnapshotMetadata
from plotlot.storage.runtime import build_storage_runtime
from plotlot.storage.s3_types import S3ObjectStoreConfig
from plotlot.storage.s3_versions import S3VersionArchive


pytestmark = pytest.mark.skipif(
    os.environ.get("PLOTLOT_STORAGE_INTEGRATION") != "true",
    reason="requires disposable PostgreSQL and MinIO",
)


class InjectedFailure(RuntimeError):
    pass


@dataclass
class FailOnce:
    target: str
    fired: bool = False

    def __call__(self, boundary: str) -> None:
        if boundary == self.target and not self.fired:
            self.fired = True
            raise InjectedFailure(boundary)


def _config(bucket: str) -> S3ObjectStoreConfig:
    return S3ObjectStoreConfig(
        endpoint_url=os.environ["PLOTLOT_OBJECT_STORE_ENDPOINT"],
        bucket=bucket,
        access_key_id=os.environ["PLOTLOT_OBJECT_STORE_ACCESS_KEY"],
        secret_access_key=os.environ["PLOTLOT_OBJECT_STORE_SECRET_KEY"],
        region="us-east-1",
    )


def _metadata(tenant_id: str, object_key: str, *, expired: bool = False) -> SnapshotMetadata:
    now = datetime.now(UTC)
    return SnapshotMetadata(
        tenant_id=tenant_id,
        object_key=object_key,
        source_uri="https://example.invalid/durable-saga",
        fetched_at=now,
        encryption_key_id="kms/test/saga",
        retain_until=now - timedelta(seconds=1) if expired else now + timedelta(minutes=5),
    )


async def _database_value(query: str, *arguments: object) -> object:
    connection = await asyncpg.connect(
        "postgresql://storage_admin:storage_test_password@127.0.0.1:55432/plotlot_storage"
    )
    try:
        return await connection.fetchval(query, *arguments)
    finally:
        await connection.close()


async def _version_count(runtime, physical_key: str) -> int:
    records = await S3VersionArchive(runtime.object_store).list_version_records()
    return sum(record.get("Key") == physical_key for record in records)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boundary",
    [
        "put_intent_committed",
        "put_object_written",
        "put_version_persisted",
        "put_finalize_transaction",
        "put_finalized",
    ],
)
async def test_put_retry_adopts_one_owned_version_after_every_failure_boundary(
    boundary: str,
) -> None:
    bucket = f"plotlot-put-saga-{uuid4().hex}"
    tenant_id = f"tenant-{uuid4().hex}"
    snapshot_id = f"snapshot-{uuid4().hex}"
    metadata = _metadata(tenant_id, "raw/restart-safe.json")
    failed_runtime = await build_storage_runtime(
        _config(bucket), failure_injector=FailOnce(boundary)
    )

    with pytest.raises(InjectedFailure, match=boundary):
        await failed_runtime.store_snapshot(snapshot_id, metadata, b"durable-content")
    if boundary != "put_finalized":
        assert not await failed_runtime.snapshot_exists(tenant_id, metadata.object_key)

    restarted = await build_storage_runtime(_config(bucket))
    receipt = await restarted.store_snapshot(snapshot_id, metadata, b"durable-content")

    assert await restarted.read_snapshot(tenant_id, metadata.object_key) == b"durable-content"
    assert await _version_count(restarted, receipt.physical_key) == 1
    assert (
        await _database_value(
            """SELECT count(*) FROM plotlot.raw_snapshots
            WHERE tenant_id=$1 AND snapshot_id=$2""",
            tenant_id,
            snapshot_id,
        )
        == 1
    )
    assert (
        await _database_value(
            """SELECT count(*) FROM plotlot.storage_operations
            WHERE tenant_id=$1 AND snapshot_id=$2 AND operation_type='PUT'
              AND status='FINALIZED' AND object_version_id=$3""",
            tenant_id,
            snapshot_id,
            receipt.version_id,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_put_retry_rejects_changed_content_without_creating_another_version() -> None:
    bucket = f"plotlot-put-hash-{uuid4().hex}"
    tenant_id = f"tenant-{uuid4().hex}"
    snapshot_id = f"snapshot-{uuid4().hex}"
    metadata = _metadata(tenant_id, "raw/hash-bound.json")
    runtime = await build_storage_runtime(
        _config(bucket),
        failure_injector=FailOnce("put_object_written"),
    )
    with pytest.raises(InjectedFailure):
        await runtime.store_snapshot(snapshot_id, metadata, b"original")

    restarted = await build_storage_runtime(_config(bucket))
    with pytest.raises(ObjectConflictError):
        await restarted.store_snapshot(snapshot_id, metadata, b"changed")
    receipt = await restarted.store_snapshot(snapshot_id, metadata, b"original")
    assert await _version_count(restarted, receipt.physical_key) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boundary",
    [
        "delete_intent_committed",
        "delete_object_deleted",
        "delete_finalize_transaction",
        "delete_finalized",
    ],
)
async def test_delete_retry_never_exposes_a_pointer_to_a_missing_version(boundary: str) -> None:
    bucket = f"plotlot-delete-saga-{uuid4().hex}"
    tenant_id = f"tenant-{uuid4().hex}"
    snapshot_id = f"snapshot-{uuid4().hex}"
    request_id = f"delete-{uuid4().hex}"
    metadata = _metadata(tenant_id, "raw/delete-restart-safe.json", expired=True)
    initial = await build_storage_runtime(_config(bucket))
    receipt = await initial.store_snapshot(snapshot_id, metadata, b"expired")
    failed_runtime = await build_storage_runtime(
        _config(bucket), failure_injector=FailOnce(boundary)
    )
    request = LifecycleRequest(
        request_id=request_id,
        requesting_tenant_id=tenant_id,
        object_key=metadata.object_key,
        requested_by="saga-test",
        requested_at=datetime.now(UTC),
    )

    with pytest.raises(InjectedFailure, match=boundary):
        await failed_runtime.lifecycle.execute(request)
    assert not await failed_runtime.snapshot_exists(tenant_id, metadata.object_key)
    with pytest.raises(NoResultFound):
        await failed_runtime.read_snapshot(tenant_id, metadata.object_key)
    if boundary != "delete_finalized":
        assert (
            await _database_value(
                """SELECT lifecycle_state FROM plotlot.raw_snapshots
                WHERE tenant_id=$1 AND object_key=$2""",
                tenant_id,
                metadata.object_key,
            )
            == "DELETING"
        )

    restarted = await build_storage_runtime(_config(bucket))
    result = await restarted.lifecycle.execute(request)
    assert result.decision is RetentionDecision.DELETE
    assert not await restarted.object_store.version_exists(receipt)
    assert not await restarted.snapshot_exists(tenant_id, metadata.object_key)
    assert (
        await _database_value(
            """SELECT count(*) FROM plotlot.lifecycle_receipts
            WHERE tenant_id=$1 AND request_id=$2""",
            tenant_id,
            request_id,
        )
        == 1
    )
    assert (
        await _database_value(
            """SELECT count(*) FROM plotlot.storage_operations
            WHERE tenant_id=$1 AND request_id=$2 AND operation_type='DELETE'
              AND status='FINALIZED' AND object_version_id=$3""",
            tenant_id,
            request_id,
            receipt.version_id,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_recovery_adopts_written_put_and_finishes_deleted_object() -> None:
    bucket = f"plotlot-recovery-{uuid4().hex}"
    tenant_id = f"tenant-{uuid4().hex}"
    put_metadata = _metadata(tenant_id, "raw/recover-put.json")
    put_runtime = await build_storage_runtime(
        _config(bucket),
        failure_injector=FailOnce("put_object_written"),
    )
    with pytest.raises(InjectedFailure):
        await put_runtime.store_snapshot("recover-put", put_metadata, b"recoverable")

    restarted = await build_storage_runtime(_config(bucket))
    assert await restarted.recover_pending_operations(tenant_id, limit=10) == 1
    assert await restarted.read_snapshot(tenant_id, put_metadata.object_key) == b"recoverable"

    delete_metadata = _metadata(tenant_id, "raw/recover-delete.json", expired=True)
    delete_receipt = await restarted.store_snapshot("recover-delete", delete_metadata, b"delete")
    delete_runtime = await build_storage_runtime(
        _config(bucket),
        failure_injector=FailOnce("delete_object_deleted"),
    )
    with pytest.raises(InjectedFailure):
        await delete_runtime.lifecycle.execute(
            LifecycleRequest(
                request_id="recover-delete-request",
                requesting_tenant_id=tenant_id,
                object_key=delete_metadata.object_key,
                requested_by="recovery-test",
                requested_at=datetime.now(UTC),
            )
        )

    restarted_again = await build_storage_runtime(_config(bucket))
    assert await restarted_again.recover_pending_operations(tenant_id, limit=10) == 1
    assert not await restarted_again.object_store.version_exists(delete_receipt)
    assert not await restarted_again.snapshot_exists(tenant_id, delete_metadata.object_key)
    assert (
        await _database_value(
            """SELECT count(*) FROM plotlot.storage_operations
            WHERE tenant_id=$1 AND status <> 'FINALIZED'""",
            tenant_id,
        )
        == 0
    )


@pytest.mark.asyncio
async def test_held_and_other_tenant_requests_never_start_external_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bucket = f"plotlot-no-mutation-{uuid4().hex}"
    tenant_id = f"tenant-{uuid4().hex}"
    runtime = await build_storage_runtime(_config(bucket))
    metadata = _metadata(tenant_id, "raw/held-without-mutation.json", expired=True)
    receipt = await runtime.store_snapshot("held-without-mutation", metadata, b"held")
    await runtime.object_store.set_legal_hold(receipt, True)

    async def forbidden_delete(_: object) -> None:
        raise AssertionError("lifecycle attempted an external delete")

    monkeypatch.setattr(runtime.object_store, "delete_version", forbidden_delete)
    held = await runtime.lifecycle.execute(
        LifecycleRequest(
            request_id=f"held-{uuid4().hex}",
            requesting_tenant_id=tenant_id,
            object_key=metadata.object_key,
            requested_by="hold-test",
            requested_at=datetime.now(UTC),
        )
    )
    other_tenant = f"tenant-{uuid4().hex}"
    denied = await runtime.lifecycle.execute(
        LifecycleRequest(
            request_id=f"denied-{uuid4().hex}",
            requesting_tenant_id=other_tenant,
            object_key=metadata.object_key,
            requested_by="other-tenant-test",
            requested_at=datetime.now(UTC),
        )
    )

    assert held.decision is RetentionDecision.HOLD
    assert denied.decision is RetentionDecision.DENY
    assert (
        await _database_value(
            """SELECT count(*) FROM plotlot.storage_operations
            WHERE operation_type='DELETE'
              AND tenant_id IN ($1, $2) AND object_key=$3""",
            tenant_id,
            other_tenant,
            metadata.object_key,
        )
        == 0
    )


@pytest.mark.asyncio
async def test_application_role_cannot_bypass_finalized_operation_immutability() -> None:
    tenant_id = f"tenant-{uuid4().hex}"
    runtime = await build_storage_runtime(_config(f"plotlot-role-boundary-{uuid4().hex}"))
    receipt = await runtime.store_snapshot(
        f"snapshot-{uuid4().hex}",
        _metadata(tenant_id, "raw/role-boundary.json"),
        b"immutable",
    )
    admin = await asyncpg.connect(
        "postgresql://storage_admin:storage_test_password@127.0.0.1:55432/postgres"
    )
    try:
        await admin.execute(
            """DO $$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='plotlot_runtime_test') THEN
                CREATE ROLE plotlot_runtime_test LOGIN PASSWORD 'runtime_test_password' INHERIT;
              END IF;
            END $$"""
        )
        await admin.execute("GRANT plotlot_app TO plotlot_runtime_test")
    finally:
        await admin.close()
    application = await asyncpg.connect(
        "postgresql://plotlot_runtime_test:runtime_test_password@127.0.0.1:55432/plotlot_storage"
    )
    try:
        async with application.transaction():
            await application.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            await application.execute("SELECT set_config('app.restore_mode', 'on', true)")
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await application.execute(
                    """UPDATE plotlot.storage_operations SET object_version_id='forged'
                    WHERE tenant_id=$1 AND object_version_id=$2""",
                    tenant_id,
                    receipt.version_id,
                )
    finally:
        await application.close()
