from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import asyncpg
import anyio
import boto3
import pytest
from botocore.config import Config
from cryptography.exceptions import InvalidTag
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plotlot.storage.backup_crypto import decrypt, encrypt
from plotlot.storage.backup import LOCK_SQL, UNLOCK_SQL
from plotlot.storage.object_snapshots import SnapshotMetadata
from plotlot.storage.restore import _load_version_map, remap_restored_object_versions
from plotlot.storage.restore_database import promote
from plotlot.storage.restore_attempt import clean_ready, list_recovery
from plotlot.storage.runtime import _active_bucket, build_storage_runtime
from plotlot.storage.s3_types import S3ObjectStoreConfig


def test_authenticated_backup_rejects_tampering_and_wrong_passphrase() -> None:
    encrypted = encrypt(b"durable backup", "correct-passphrase")
    tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 1])

    with pytest.raises(InvalidTag):
        decrypt(tampered, "correct-passphrase")
    with pytest.raises(InvalidTag):
        decrypt(encrypted, "incorrect-passphrase")


def test_composite_version_map_allows_same_source_version_across_keys(
    tmp_path: Path,
) -> None:
    path = tmp_path / "version-map.json"
    path.write_text(
        json.dumps(
            {
                "schema": "PlotLotVersionMapV2",
                "versions": [
                    {
                        "physical_key": "tenants/one/a.json",
                        "source_version_id": "shared",
                        "destination_version_id": "destination-a",
                    },
                    {
                        "physical_key": "tenants/one/b.json",
                        "source_version_id": "shared",
                        "destination_version_id": "destination-b",
                    },
                ],
            }
        )
    )

    assert len(_load_version_map(path)) == 2


def test_composite_version_map_rejects_ambiguous_duplicate_identity(tmp_path: Path) -> None:
    path = tmp_path / "ambiguous-version-map.json"
    entry = {
        "physical_key": "tenants/one/a.json",
        "source_version_id": "shared",
        "destination_version_id": "destination",
    }
    path.write_text(json.dumps({"schema": "PlotLotVersionMapV2", "versions": [entry, entry]}))

    with pytest.raises(RuntimeError, match="duplicate restore version identity"):
        _load_version_map(path)


@pytest.mark.asyncio
async def test_tampered_restore_leaves_database_and_bucket_unchanged(tmp_path: Path) -> None:
    database_name = f"poison_{uuid4().hex}"
    database_url = await _create_database(database_name)
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute("CREATE TABLE restore_marker (value text NOT NULL)")
        await connection.execute("INSERT INTO restore_marker VALUES ('unchanged')")
    finally:
        await connection.close()
    bucket = f"plotlot-poison-{uuid4().hex}"
    poisoned = tmp_path / "poisoned.aead"
    payload = encrypt(b"not-a-backup", "integration-test-passphrase")
    poisoned.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))

    result = subprocess.run(
        ["scripts/storage/restore_storage.sh", str(poisoned), str(tmp_path / "restore")],
        cwd=Path(__file__).resolve().parents[2],
        env=_script_environment(database_url, bucket),
        capture_output=True,
        check=False,
        text=True,
    )
    connection = await asyncpg.connect(database_url)
    try:
        marker = await connection.fetchval("SELECT value FROM restore_marker")
    finally:
        await connection.close()
    buckets = _s3_client().list_buckets().get("Buckets", [])

    assert result.returncode != 0
    assert marker == "unchanged"
    assert bucket not in {item["Name"] for item in buckets}


@pytest.mark.asyncio
async def test_backup_refuses_pending_storage_operation(tmp_path: Path) -> None:
    database_name = f"pending_{uuid4().hex}"
    database_url = await _create_database(database_name)
    _migrate_database(database_url)
    engine = create_async_engine(database_url.replace("postgresql://", "postgresql+asyncpg://"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def session():
        return sessions()

    bucket = f"plotlot-pending-{uuid4().hex}"
    runtime = await build_storage_runtime(_store_config(bucket), session, _fail_after_intent)
    now = datetime.now(UTC)
    with pytest.raises(RuntimeError, match="injected pending operation"):
        await runtime.store_snapshot(
            f"snapshot-{uuid4().hex}",
            SnapshotMetadata(
                tenant_id=f"tenant-{uuid4().hex}",
                object_key="backup/pending.json",
                source_uri="https://example.invalid/pending",
                fetched_at=now,
                encryption_key_id="kms/test/pending",
                retain_until=now + timedelta(minutes=5),
            ),
            b"pending",
        )
    output = tmp_path / "backup"
    result = subprocess.run(
        ["scripts/storage/backup_storage.sh", str(output)],
        cwd=Path(__file__).resolve().parents[2],
        env=_script_environment(database_url, bucket),
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert "backup refused while storage operations are pending" in result.stderr
    assert not (output / "storage-backup.tar.aead").exists()
    await engine.dispose()


@pytest.mark.asyncio
async def test_backup_barrier_blocks_concurrent_snapshot_intent() -> None:
    database_name = f"barrier_{uuid4().hex}"
    database_url = await _create_database(database_name)
    _migrate_database(database_url)
    engine = create_async_engine(database_url.replace("postgresql://", "postgresql+asyncpg://"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def session():
        return sessions()

    runtime = await build_storage_runtime(_store_config(f"plotlot-barrier-{uuid4().hex}"), session)
    metadata = SnapshotMetadata(
        tenant_id=f"tenant-{uuid4().hex}",
        object_key="backup/barrier.json",
        source_uri="https://example.invalid/barrier",
        fetched_at=datetime.now(UTC),
        encryption_key_id="kms/test/barrier",
        retain_until=datetime.now(UTC) + timedelta(minutes=5),
    )
    lock_connection = await asyncpg.connect(database_url)
    try:
        await lock_connection.execute(LOCK_SQL)
        with pytest.raises(TimeoutError):
            with anyio.fail_after(0.2):
                await runtime.store_snapshot(f"snapshot-{uuid4().hex}", metadata, b"blocked")
    finally:
        await lock_connection.execute(UNLOCK_SQL)
        await lock_connection.close()
    await engine.dispose()
    receipt = await runtime.store_snapshot(f"snapshot-{uuid4().hex}", metadata, b"released")

    assert receipt.object_key == metadata.object_key
    await engine.dispose()


@pytest.mark.asyncio
async def test_failed_database_promotion_restores_original_target() -> None:
    database_name = f"promotion_{uuid4().hex}"
    database_url = await _create_database(database_name)
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute("CREATE TABLE promotion_marker (value text NOT NULL)")
        await connection.execute("INSERT INTO promotion_marker VALUES ('original')")
    finally:
        await connection.close()

    with pytest.raises(asyncpg.InvalidCatalogNameError):
        await promote(database_url, f"missing_{uuid4().hex}")
    connection = await asyncpg.connect(database_url)
    try:
        marker = await connection.fetchval("SELECT value FROM promotion_marker")
    finally:
        await connection.close()

    assert marker == "original"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("required_table", "removed_tables"),
    [
        ("raw_snapshots", ("storage_operations", "lifecycle_receipts")),
        ("storage_operations", ("raw_snapshots", "lifecycle_receipts")),
        ("lifecycle_receipts", ("raw_snapshots", "storage_operations")),
    ],
)
async def test_restore_refuses_map_omitting_each_required_reference_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    required_table: str,
    removed_tables: tuple[str, str],
) -> None:
    database_url = await _create_database(f"remap_{uuid4().hex}")
    _migrate_database(database_url)
    engine = create_async_engine(database_url.replace("postgresql://", "postgresql+asyncpg://"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def session():
        return sessions()

    runtime = await build_storage_runtime(_store_config(f"plotlot-remap-{uuid4().hex}"), session)
    now = datetime.now(UTC)
    tenant_id = f"tenant-{uuid4().hex}"
    object_key = "restore/required.json"
    receipt = await runtime.store_snapshot(
        f"snapshot-{uuid4().hex}",
        SnapshotMetadata(
            tenant_id=tenant_id,
            object_key=object_key,
            source_uri="https://example.invalid/required",
            fetched_at=now,
            encryption_key_id="kms/test/required",
            retain_until=now + timedelta(minutes=5),
        ),
        b"required",
    )
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute(
            """INSERT INTO plotlot.lifecycle_receipts
            (tenant_id, request_id, object_key, object_version_id, decision,
             reason, requested_by, requested_at)
            VALUES ($1, $2, $3, $4, 'keep', 'required-reference', 'test', $5)""",
            tenant_id,
            f"request-{uuid4().hex}",
            object_key,
            receipt.version_id,
            now,
        )
        await connection.execute("SET session_replication_role=replica")
        for table in removed_tables:
            await connection.execute(f"DELETE FROM plotlot.{table}")
        await connection.execute("SET session_replication_role=origin")
    finally:
        await connection.close()
    map_path = tmp_path / f"{required_table}.json"
    map_path.write_text('{"schema":"PlotLotVersionMapV2","versions":[]}')
    monkeypatch.setenv("PLOTLOT_RESTORE_STAGED_BUCKET", "unreachable-stage")

    with pytest.raises(RuntimeError, match="omits database references"):
        await remap_restored_object_versions(database_url, map_path)
    await engine.dispose()


@pytest.mark.asyncio
async def test_application_role_cannot_forge_storage_generation() -> None:
    database_url = await _create_database(f"generation_{uuid4().hex}")
    _migrate_database(database_url)
    for statement in (
        """INSERT INTO plotlot.restore_attempts
        (attempt_id, stage_bucket, stage_database, archive_sha256, state, cleanup_after)
        VALUES (gen_random_uuid(), 'plotlot-restore-attacker', 'attacker',
        repeat('0', 64), 'PROMOTED', now())""",
        """INSERT INTO plotlot.storage_generation
        (singleton, bucket, restore_attempt_id)
        VALUES (true, 'plotlot-restore-attacker', gen_random_uuid())""",
        "UPDATE plotlot.storage_generation SET bucket='plotlot-restore-attacker'",
        "DELETE FROM plotlot.storage_generation",
    ):
        connection = await asyncpg.connect(database_url)
        try:
            await connection.execute("SET ROLE plotlot_app")
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await connection.execute(statement)
        finally:
            await connection.close()
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute("SET ROLE plotlot_app")
        await connection.execute("SELECT set_config('app.restore_mode', 'on', false)")
        generation = await connection.fetchval(
            "SELECT bucket FROM plotlot.storage_generation WHERE singleton=true"
        )
    finally:
        await connection.close()
    assert generation is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    ("REGISTERED", "OBJECTS_RESTORED", "RECOVERY_REQUIRED", "CLEANED"),
)
async def test_non_promoted_attempt_cannot_bind_generation_or_activate_bucket(
    state: str,
) -> None:
    database_url = await _create_database(f"generation_state_{uuid4().hex}")
    _migrate_database(database_url)
    attempt_id = uuid4()
    stage_bucket = f"plotlot-restore-{uuid4().hex}"
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute(
            """INSERT INTO plotlot.restore_attempts
            (attempt_id, stage_bucket, stage_database, archive_sha256, state, cleanup_after)
            VALUES ($1, $2, 'stage-db', repeat('0',64), $3, now())""",
            attempt_id,
            stage_bucket,
            state,
        )
        with pytest.raises(
            asyncpg.RaiseError,
            match="storage_generation_requires_promoted_attempt",
        ):
            await connection.execute(
                """INSERT INTO plotlot.storage_generation
                (singleton, bucket, restore_attempt_id) VALUES (true, $1, $2)""",
                stage_bucket,
                attempt_id,
            )
        await connection.execute("SET session_replication_role=replica")
        await connection.execute(
            """INSERT INTO plotlot.storage_generation
            (singleton, bucket, restore_attempt_id) VALUES (true, $1, $2)""",
            stage_bucket,
            attempt_id,
        )
        await connection.execute("SET session_replication_role=origin")
    finally:
        await connection.close()
    engine = create_async_engine(database_url.replace("postgresql://", "postgresql+asyncpg://"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def session_provider():
        return sessions()

    configured_bucket = f"plotlot-live-{uuid4().hex}"
    assert await _active_bucket(session_provider, configured_bucket) == configured_bucket
    await engine.dispose()


@pytest.mark.asyncio
async def test_generation_cannot_be_updated_to_non_promoted_attempt() -> None:
    database_url = await _create_database(f"generation_update_{uuid4().hex}")
    _migrate_database(database_url)
    promoted_attempt = uuid4()
    non_promoted_attempt = uuid4()
    connection = await asyncpg.connect(database_url)
    try:
        await connection.executemany(
            """INSERT INTO plotlot.restore_attempts
            (attempt_id, stage_bucket, stage_database, archive_sha256, state, cleanup_after)
            VALUES ($1, $2, 'stage-db', repeat('0',64), $3, now())""",
            (
                (promoted_attempt, "plotlot-promoted", "PROMOTED"),
                (non_promoted_attempt, "plotlot-registered", "REGISTERED"),
            ),
        )
        await connection.execute(
            """INSERT INTO plotlot.storage_generation
            (singleton, bucket, restore_attempt_id)
            VALUES (true, 'plotlot-promoted', $1)""",
            promoted_attempt,
        )
        with pytest.raises(
            asyncpg.RaiseError,
            match="storage_generation_requires_promoted_attempt",
        ):
            await connection.execute(
                """UPDATE plotlot.storage_generation
                SET bucket='plotlot-registered', restore_attempt_id=$1""",
                non_promoted_attempt,
            )
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_recovery_list_discovers_attempt_and_cleanup_waits_for_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = await _create_database(f"recovery_{uuid4().hex}")
    _migrate_database(database_url)
    attempt_id = uuid4()
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute(
            """INSERT INTO plotlot.restore_attempts
            (attempt_id, stage_bucket, stage_database, archive_sha256, state, cleanup_after)
            VALUES ($1, $2, 'stage-db', repeat('0',64), 'RECOVERY_REQUIRED',
            now() + interval '1 day')""",
            attempt_id,
            f"plotlot-restore-{uuid4().hex}",
        )
    finally:
        await connection.close()
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)

    attempts = await list_recovery()
    with pytest.raises(RuntimeError, match="not eligible for cleanup"):
        await clean_ready(attempt_id)

    assert [row["attempt_id"] for row in attempts] == [attempt_id]


async def _create_database(database_name: str) -> str:
    connection = await asyncpg.connect(
        "postgresql://storage_admin:storage_test_password@127.0.0.1:55432/postgres"
    )
    try:
        await connection.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await connection.close()
    return f"postgresql://storage_admin:storage_test_password@127.0.0.1:55432/{database_name}"


def _script_environment(database_url: str, bucket: str) -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    return {
        **os.environ,
        "TEST_DATABASE_URL": database_url,
        "STORAGE_BACKUP_PASSPHRASE": "integration-test-passphrase",
        "PLOTLOT_OBJECT_STORE_ENDPOINT": os.environ["PLOTLOT_OBJECT_STORE_ENDPOINT"],
        "PLOTLOT_OBJECT_STORE_BUCKET": bucket,
        "PLOTLOT_OBJECT_STORE_ACCESS_KEY": os.environ["PLOTLOT_OBJECT_STORE_ACCESS_KEY"],
        "PLOTLOT_OBJECT_STORE_SECRET_KEY": os.environ["PLOTLOT_OBJECT_STORE_SECRET_KEY"],
        "PLOTLOT_PYTHON": str(root / ".venv" / "bin" / "python"),
    }


def _migrate_database(database_url: str) -> None:
    result = subprocess.run(
        [".venv/bin/alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)


def _store_config(bucket: str) -> S3ObjectStoreConfig:
    return S3ObjectStoreConfig(
        endpoint_url=os.environ["PLOTLOT_OBJECT_STORE_ENDPOINT"],
        bucket=bucket,
        access_key_id=os.environ["PLOTLOT_OBJECT_STORE_ACCESS_KEY"],
        secret_access_key=os.environ["PLOTLOT_OBJECT_STORE_SECRET_KEY"],
        region="us-east-1",
    )


def _fail_after_intent(boundary: str) -> None:
    if boundary == "put_intent_committed":
        raise RuntimeError("injected pending operation")


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["PLOTLOT_OBJECT_STORE_ENDPOINT"],
        aws_access_key_id=os.environ["PLOTLOT_OBJECT_STORE_ACCESS_KEY"],
        aws_secret_access_key=os.environ["PLOTLOT_OBJECT_STORE_SECRET_KEY"],
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )
