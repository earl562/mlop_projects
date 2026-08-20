from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import asyncpg

from plotlot.storage.archive import ObjectArchiveService
from plotlot.storage.backup_crypto import encrypt
from plotlot.storage.s3_objects import S3ImmutableObjectStore
from plotlot.storage.s3_types import S3ObjectStoreConfig


LOCK_SQL = "SELECT pg_advisory_lock(hashtextextended('plotlot-storage-backup', 0))"
UNLOCK_SQL = "SELECT pg_advisory_unlock(hashtextextended('plotlot-storage-backup', 0))"


async def create_backup(output_dir: Path) -> Path:
    database_url = os.environ["TEST_DATABASE_URL"]
    connection = await asyncpg.connect(
        database_url.replace("postgresql+asyncpg://", "postgresql://")
    )
    try:
        await connection.execute(LOCK_SQL)
        pending = await connection.fetchval(
            "SELECT count(*) FROM plotlot.storage_operations WHERE status <> 'FINALIZED'"
        )
        if pending:
            raise RuntimeError("backup refused while storage operations are pending")
        return await _export_locked(output_dir, database_url)
    finally:
        await connection.execute(UNLOCK_SQL)
        await connection.close()


async def _export_locked(output_dir: Path, database_url: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        work_dir = Path(temporary)
        database_dump = work_dir / "database.dump"
        objects_archive = work_dir / "objects.tar"
        result = subprocess.run(
            ["pg_dump", "--format=custom", "--no-owner", f"--file={database_dump}", database_url],
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr)
        store = S3ImmutableObjectStore(_object_store_config())
        await store.initialize()
        receipt = await ObjectArchiveService(store).export(objects_archive)
        (work_dir / "object-export.json").write_text(
            json.dumps(
                {
                    "version_count": receipt.version_count,
                    "manifest_sha256": receipt.manifest_sha256,
                },
                sort_keys=True,
            )
            + "\n"
        )
        manifest = {
            "version": "2",
            "created_at": datetime.now(UTC).isoformat(),
            "rpo_minutes": 15,
            "rto_hours": 4,
            "database_sha256": sha256(database_dump.read_bytes()).hexdigest(),
            "objects_sha256": sha256(objects_archive.read_bytes()).hexdigest(),
        }
        (work_dir / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
        )
        package = work_dir / "storage-backup.tar"
        with tarfile.open(package, "w") as archive:
            for name in ("database.dump", "objects.tar", "object-export.json", "manifest.json"):
                archive.add(work_dir / name, arcname=name)
        destination = output_dir / "storage-backup.tar.aead"
        destination.write_bytes(
            encrypt(package.read_bytes(), os.environ["STORAGE_BACKUP_PASSPHRASE"])
        )
        (output_dir / "storage-backup.tar.aead.sha256").write_text(
            sha256(destination.read_bytes()).hexdigest() + "\n"
        )
        return destination


def _object_store_config() -> S3ObjectStoreConfig:
    return S3ObjectStoreConfig(
        endpoint_url=os.environ["PLOTLOT_OBJECT_STORE_ENDPOINT"],
        bucket=os.environ["PLOTLOT_OBJECT_STORE_BUCKET"],
        access_key_id=os.environ["PLOTLOT_OBJECT_STORE_ACCESS_KEY"],
        secret_access_key=os.environ["PLOTLOT_OBJECT_STORE_SECRET_KEY"],
        region=os.environ.get("PLOTLOT_OBJECT_STORE_REGION", "us-east-1"),
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    arguments = parser.parse_args()
    print(asyncio.run(create_backup(arguments.output_dir)))


if __name__ == "__main__":
    main()
