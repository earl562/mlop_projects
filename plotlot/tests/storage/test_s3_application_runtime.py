from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plotlot.config import settings
from plotlot.storage.db import init_db
from plotlot.storage.lifecycle import LifecycleRequest, RetentionDecision
from plotlot.storage.object_snapshots import ObjectTamperedError, SnapshotMetadata
from plotlot.storage.runtime import build_storage_runtime, get_storage_runtime
from plotlot.storage.s3_objects import S3ObjectStoreConfig
from plotlot.storage.s3_types import ObjectVersionPayload
from plotlot.storage.s3_versions import S3VersionArchive


pytestmark = pytest.mark.skipif(
    os.environ.get("PLOTLOT_STORAGE_INTEGRATION") != "true",
    reason="requires disposable PostgreSQL and MinIO",
)


def _config(bucket: str) -> S3ObjectStoreConfig:
    return S3ObjectStoreConfig(
        endpoint_url=os.environ["PLOTLOT_OBJECT_STORE_ENDPOINT"],
        bucket=bucket,
        access_key_id=os.environ["PLOTLOT_OBJECT_STORE_ACCESS_KEY"],
        secret_access_key=os.environ["PLOTLOT_OBJECT_STORE_SECRET_KEY"],
        region="us-east-1",
    )


@pytest.mark.asyncio
async def test_application_startup_composes_configured_s3_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bucket = f"plotlot-startup-{uuid4().hex}"
    monkeypatch.setattr(settings, "object_store_enabled", True)
    monkeypatch.setattr(
        settings, "object_store_endpoint_url", os.environ["PLOTLOT_OBJECT_STORE_ENDPOINT"]
    )
    monkeypatch.setattr(settings, "object_store_bucket", bucket)
    monkeypatch.setattr(
        settings,
        "object_store_access_key_id",
        os.environ["PLOTLOT_OBJECT_STORE_ACCESS_KEY"],
    )
    monkeypatch.setattr(
        settings,
        "object_store_secret_access_key",
        os.environ["PLOTLOT_OBJECT_STORE_SECRET_KEY"],
    )

    await init_db()

    assert get_storage_runtime().object_store.config.bucket == bucket


@pytest.mark.asyncio
async def test_composed_runtime_round_trips_exact_version_and_rejects_tamper() -> None:
    runtime = await build_storage_runtime(_config(f"plotlot-runtime-{uuid4().hex}"))
    now = datetime.now(UTC)
    metadata = SnapshotMetadata(
        tenant_id=f"tenant-{uuid4().hex}",
        object_key="evidence/parcel.json",
        source_uri="https://example.invalid/source/parcel",
        fetched_at=now,
        encryption_key_id="kms/test/key",
        retain_until=now + timedelta(minutes=1),
        legal_hold=False,
    )
    receipt = await runtime.store_snapshot(f"snapshot-{uuid4().hex}", metadata, b'{"zone":"R-1"}')

    assert await runtime.read_snapshot(metadata.tenant_id, receipt.object_key) == b'{"zone":"R-1"}'
    altered = b'{"zone":"altered"}'
    altered_version = await S3VersionArchive(runtime.object_store).restore_version(
        ObjectVersionPayload(
            physical_key=receipt.physical_key,
            version_id="source-tampered-version",
            content=altered,
            metadata={
                "tenant-id": receipt.tenant_id,
                "object-key": receipt.object_key,
                "source-uri": receipt.source_uri,
                "fetched-at": receipt.fetched_at.isoformat(),
                "encryption-key-id": receipt.encryption_key_id,
                "content-sha256": "0" * 64,
            },
            content_type="application/octet-stream",
            legal_hold=False,
            retention_mode=None,
            retain_until=None,
            last_modified=now,
        )
    )
    with pytest.raises(ObjectTamperedError):
        await runtime.object_store.get_verified(
            receipt.with_version(altered_version),
        )
    assert await runtime.object_store.get_verified(receipt) == b'{"zone":"R-1"}'


@pytest.mark.asyncio
async def test_lifecycle_executes_idempotent_tenant_delete_and_denial_receipts() -> None:
    session_provider, engine = await _application_role_sessions()
    runtime = await build_storage_runtime(
        _config(f"plotlot-lifecycle-{uuid4().hex}"),
        session_provider,
    )
    tenant_id = f"tenant-{uuid4().hex}"
    now = datetime.now(UTC)
    metadata = SnapshotMetadata(
        tenant_id=tenant_id,
        object_key="raw/expired.json",
        source_uri="https://example.invalid/source/expired",
        fetched_at=now,
        encryption_key_id="kms/test/key",
        retain_until=now - timedelta(seconds=1),
        legal_hold=False,
    )
    receipt = await runtime.store_snapshot(f"snapshot-{uuid4().hex}", metadata, b"expired")
    request = LifecycleRequest(
        request_id=f"request-{uuid4().hex}",
        requesting_tenant_id=tenant_id,
        object_key=receipt.object_key,
        requested_by="test-operator",
        requested_at=now,
    )

    deleted = await runtime.lifecycle.execute(request)
    repeated = await runtime.lifecycle.execute(request)
    denied = await runtime.lifecycle.execute(
        LifecycleRequest(
            request_id=f"request-{uuid4().hex}",
            requesting_tenant_id=f"tenant-{uuid4().hex}",
            object_key=receipt.object_key,
            requested_by="other-operator",
            requested_at=now,
        )
    )

    assert deleted.decision is RetentionDecision.DELETE
    assert repeated == deleted
    assert denied.decision is RetentionDecision.DENY
    assert not await runtime.object_store.version_exists(receipt)
    assert not await runtime.snapshot_exists(tenant_id, receipt.object_key)
    await engine.dispose()


@pytest.mark.asyncio
async def test_lifecycle_preserves_held_database_and_object_records() -> None:
    runtime = await build_storage_runtime(_config(f"plotlot-hold-{uuid4().hex}"))
    tenant_id = f"tenant-{uuid4().hex}"
    now = datetime.now(UTC)
    metadata = SnapshotMetadata(
        tenant_id=tenant_id,
        object_key="raw/held.json",
        source_uri="https://example.invalid/source/held",
        fetched_at=now,
        encryption_key_id="kms/test/key",
        retain_until=now - timedelta(seconds=1),
        legal_hold=False,
    )
    receipt = await runtime.store_snapshot(f"snapshot-{uuid4().hex}", metadata, b"held")
    await runtime.object_store.set_legal_hold(receipt, True)

    result = await runtime.lifecycle.execute(
        LifecycleRequest(
            request_id=f"request-{uuid4().hex}",
            requesting_tenant_id=tenant_id,
            object_key=receipt.object_key,
            requested_by="test-operator",
            requested_at=now,
        )
    )

    assert result.decision is RetentionDecision.HOLD
    assert result.reason == "object_legal_hold"
    assert await runtime.object_store.version_exists(receipt)
    assert await runtime.snapshot_exists(tenant_id, receipt.object_key)


async def _application_role_sessions():
    admin = await asyncpg.connect(
        "postgresql://storage_admin:storage_test_password@127.0.0.1:55432/postgres"
    )
    try:
        await admin.execute(
            """DO $$
            BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'plotlot_runtime_test') THEN
                CREATE ROLE plotlot_runtime_test LOGIN PASSWORD 'runtime_test_password' INHERIT;
              END IF;
            END
            $$"""
        )
        await admin.execute("GRANT plotlot_app TO plotlot_runtime_test")
    finally:
        await admin.close()
    engine = create_async_engine(
        "postgresql+asyncpg://plotlot_runtime_test:runtime_test_password"
        "@127.0.0.1:55432/plotlot_storage"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def session_provider():
        return sessions()

    return session_provider, engine
