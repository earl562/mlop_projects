from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plotlot.storage.archive import ObjectArchiveService
from plotlot.storage.object_snapshots import SnapshotMetadata
from plotlot.storage.runtime import _active_bucket, build_storage_runtime
from plotlot.storage.s3_objects import S3ImmutableObjectStore, S3ObjectStoreConfig
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
async def test_archive_restores_versions_metadata_and_hold_for_application_read(
    tmp_path: Path,
) -> None:
    source = await build_storage_runtime(_config(f"plotlot-source-{uuid4().hex}"))
    tenant_id = f"tenant-{uuid4().hex}"
    now = datetime.now(UTC)
    receipt = await source.store_snapshot(
        f"snapshot-{uuid4().hex}",
        SnapshotMetadata(
            tenant_id=tenant_id,
            object_key="evidence/held-source.json",
            source_uri="https://example.invalid/source/archive",
            fetched_at=now,
            encryption_key_id="kms/test/key",
            retain_until=now + timedelta(minutes=1),
            legal_hold=True,
        ),
        b'{"restorable":true}',
    )
    archive_path = tmp_path / "objects.tar"
    exported = await ObjectArchiveService(source.object_store).export(archive_path)

    destination = await build_storage_runtime(_config(f"plotlot-destination-{uuid4().hex}"))
    version_map = await ObjectArchiveService(destination.object_store).restore(archive_path)
    mapping = next(
        item
        for item in version_map
        if item["physical_key"].endswith("/evidence/held-source.json")
        and item["source_version_id"] == receipt.version_id
    )
    restored_receipt = receipt.with_version(mapping["destination_version_id"])
    restored_archive = tmp_path / "restored-objects.tar"
    restored_export = await ObjectArchiveService(destination.object_store).export(restored_archive)

    assert exported.version_count == 1
    assert restored_export.version_count == 1
    assert await destination.object_store.get_verified(restored_receipt) == b'{"restorable":true}'
    assert await destination.object_store.is_legal_hold_enabled(restored_receipt)
    restored_payload = await S3VersionArchive(destination.object_store).export_version(
        restored_receipt.physical_key,
        restored_receipt.version_id,
    )
    assert restored_payload.retention_mode == "GOVERNANCE"


@pytest.mark.asyncio
async def test_hard_kill_restore_windows_never_expose_non_promoted_generation(
    tmp_path: Path,
) -> None:
    source_database = f"source_{uuid4().hex}"
    destination_database = f"restore_{uuid4().hex}"
    await _create_database(source_database)
    await _create_database(destination_database)
    source_url = _database_url(source_database)
    destination_url = _database_url(destination_database)
    _migrate_database(source_url)
    _migrate_database(destination_url)
    source_engine = create_async_engine(
        source_url.replace("postgresql://", "postgresql+asyncpg://")
    )
    source_sessions = async_sessionmaker(source_engine, expire_on_commit=False)

    async def source_session():
        return source_sessions()

    source_bucket = f"plotlot-backup-{uuid4().hex}"
    source = await build_storage_runtime(_config(source_bucket), source_session)
    tenant_id = f"tenant-{uuid4().hex}"
    object_key = "evidence/blank-stack.json"
    now = datetime.now(UTC)
    receipt = await source.store_snapshot(
        f"snapshot-{uuid4().hex}",
        SnapshotMetadata(
            tenant_id=tenant_id,
            object_key=object_key,
            source_uri="https://example.invalid/source/blank-stack",
            fetched_at=now,
            encryption_key_id="kms/test/key",
            retain_until=now + timedelta(minutes=1),
            legal_hold=True,
        ),
        b'{"blank_stack_restore":true}',
    )
    source_connection = await asyncpg.connect(source_url)
    try:
        await source_connection.execute(
            """INSERT INTO plotlot.lifecycle_receipts
            (tenant_id, request_id, object_key, object_version_id, decision,
             reason, requested_by, requested_at)
            VALUES ($1, $2, $3, $4, 'keep', 'restore-reference',
             'integration-test', $5)""",
            tenant_id,
            f"request-{uuid4().hex}",
            object_key,
            receipt.version_id,
            now,
        )
    finally:
        await source_connection.close()
    backup_dir = tmp_path / "backup"
    backup_env = _script_environment(source_url, source_bucket)
    backup = subprocess.run(
        ["scripts/storage/backup_storage.sh", str(backup_dir)],
        cwd=Path(__file__).resolve().parents[2],
        env=backup_env,
        capture_output=True,
        check=False,
        text=True,
    )
    assert backup.returncode == 0, backup.stdout + backup.stderr

    destination_bucket = f"plotlot-restored-{uuid4().hex}"
    restore_dir = tmp_path / "restore"
    restore_env = _script_environment(destination_url, destination_bucket)
    destination_connection = await asyncpg.connect(destination_url)
    try:
        await destination_connection.execute("CREATE TABLE restore_marker (value text NOT NULL)")
        await destination_connection.execute("INSERT INTO restore_marker VALUES ('unchanged')")
    finally:
        await destination_connection.close()
    original_store = S3ImmutableObjectStore(_config(destination_bucket))
    await original_store.initialize()
    original_store.client.put_object(
        Bucket=destination_bucket,
        Key="preexisting/marker",
        Body=b"unchanged",
    )
    target_versions_before = await S3VersionArchive(original_store).list_version_records()
    failed_restore = subprocess.run(
        [
            "scripts/storage/restore_storage.sh",
            str(backup_dir / "storage-backup.tar.aead"),
            str(tmp_path / "failed-restore"),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**restore_env, "PLOTLOT_RESTORE_KILL_BEFORE_DB_RENAME": "true"},
        capture_output=True,
        check=False,
        text=True,
    )
    destination_connection = await asyncpg.connect(destination_url)
    try:
        marker_after_failure = await destination_connection.fetchval(
            "SELECT value FROM restore_marker"
        )
        recovery_attempt = await destination_connection.fetchrow(
            """SELECT stage_bucket, state FROM plotlot.restore_attempts
            WHERE state='OBJECTS_RESTORED'"""
        )
    finally:
        await destination_connection.close()
    target_versions_after = await S3VersionArchive(original_store).list_version_records()
    assert failed_restore.returncode == -9
    assert marker_after_failure == "unchanged"
    assert target_versions_after == target_versions_before
    assert recovery_attempt is not None
    assert recovery_attempt["stage_bucket"].startswith("plotlot-restore-")
    recovery = subprocess.run(
        [
            str(Path(__file__).resolve().parents[2] / ".venv" / "bin" / "python"),
            "-m",
            "plotlot.storage.restore_attempt",
            "list",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=restore_env,
        capture_output=True,
        check=False,
        text=True,
    )
    assert recovery.returncode == 0, recovery.stdout + recovery.stderr
    recovery_records = json.loads(recovery.stdout)
    recovery_record = next(
        record
        for record in recovery_records
        if record["stage_bucket"] == recovery_attempt["stage_bucket"]
    )
    assert recovery_record["state"] == "OBJECTS_RESTORED" and recovery_record["stage_database"]
    administration = await asyncpg.connect(
        "postgresql://storage_admin:storage_test_password@127.0.0.1:55432/postgres"
    )
    try:
        stage_database_exists = await administration.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=$1)",
            recovery_record["stage_database"],
        )
    finally:
        await administration.close()
    original_store.client.head_bucket(Bucket=recovery_record["stage_bucket"])
    assert stage_database_exists
    pre_rename_engine = create_async_engine(
        destination_url.replace("postgresql://", "postgresql+asyncpg://")
    )
    pre_rename_sessions = async_sessionmaker(pre_rename_engine, expire_on_commit=False)

    async def pre_rename_session():
        return pre_rename_sessions()

    assert await _active_bucket(pre_rename_session, destination_bucket) == destination_bucket
    await pre_rename_engine.dispose()
    restore = subprocess.run(
        [
            "scripts/storage/restore_storage.sh",
            str(backup_dir / "storage-backup.tar.aead"),
            str(restore_dir),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env={**restore_env, "PLOTLOT_RESTORE_KILL_AFTER_DB_RENAME": "true"},
        capture_output=True,
        check=False,
        text=True,
    )
    assert restore.returncode == -9, restore.stdout + restore.stderr

    destination_engine = create_async_engine(
        destination_url.replace("postgresql://", "postgresql+asyncpg://")
    )
    destination_sessions = async_sessionmaker(destination_engine, expire_on_commit=False)

    async def destination_session():
        return destination_sessions()

    destination = await build_storage_runtime(_config(destination_bucket), destination_session)
    restored_receipt = await destination.load_snapshot_receipt(tenant_id, object_key)
    destination_connection = await asyncpg.connect(destination_url)
    try:
        lifecycle_version = await destination_connection.fetchval(
            """SELECT object_version_id FROM plotlot.lifecycle_receipts
            WHERE tenant_id=$1 AND object_key=$2""",
            tenant_id,
            object_key,
        )
        promoted_binding = await destination_connection.fetchval(
            """SELECT count(*) FROM plotlot.storage_generation generation
            JOIN plotlot.restore_attempts attempt
              ON attempt.attempt_id=generation.restore_attempt_id
            WHERE attempt.state='PROMOTED'
              AND attempt.stage_bucket=generation.bucket"""
        )
    finally:
        await destination_connection.close()

    assert restored_receipt.version_id != receipt.version_id
    assert destination.object_store.config.bucket != destination_bucket
    assert lifecycle_version == restored_receipt.version_id
    assert promoted_binding == 1
    assert await destination.read_snapshot(tenant_id, object_key) == b'{"blank_stack_restore":true}'
    assert await destination.object_store.is_legal_hold_enabled(restored_receipt)
    assert (restore_dir / "database-remap.json").read_text().strip()
    assert (restore_dir / "object-restore.json").read_text().strip()
    await source_engine.dispose()
    await destination_engine.dispose()


async def _create_database(database_name: str) -> None:
    if not database_name.replace("_", "").isalnum():
        raise ValueError("unsafe test database name")
    connection = await asyncpg.connect(
        "postgresql://storage_admin:storage_test_password@127.0.0.1:55432/postgres"
    )
    try:
        await connection.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await connection.close()


def _database_url(database_name: str) -> str:
    return f"postgresql://storage_admin:storage_test_password@127.0.0.1:55432/{database_name}"


def _migrate_database(database_url: str) -> None:
    result = subprocess.run(
        [".venv/bin/alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout + result.stderr)


def _script_environment(database_url: str, bucket: str) -> dict[str, str]:
    return {
        **os.environ,
        "TEST_DATABASE_URL": database_url,
        "STORAGE_BACKUP_PASSPHRASE": "integration-test-passphrase",
        "PLOTLOT_OBJECT_STORE_ENDPOINT": os.environ["PLOTLOT_OBJECT_STORE_ENDPOINT"],
        "PLOTLOT_OBJECT_STORE_BUCKET": bucket,
        "PLOTLOT_OBJECT_STORE_ACCESS_KEY": os.environ["PLOTLOT_OBJECT_STORE_ACCESS_KEY"],
        "PLOTLOT_OBJECT_STORE_SECRET_KEY": os.environ["PLOTLOT_OBJECT_STORE_SECRET_KEY"],
        "PLOTLOT_PYTHON": str(Path(__file__).resolve().parents[2] / ".venv" / "bin" / "python"),
    }
