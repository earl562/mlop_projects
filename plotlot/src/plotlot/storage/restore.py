from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import boto3
from botocore.config import Config

from plotlot.storage.s3_types import logical_key


@dataclass(frozen=True, slots=True)
class VersionRemap:
    physical_key: str
    source_version_id: str
    destination_version_id: str


def _asyncpg_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def remap_restored_object_versions(
    database_url: str,
    version_map_path: Path,
) -> int:
    version_map = _load_version_map(version_map_path)
    connection = await asyncpg.connect(_asyncpg_url(database_url))
    try:
        async with connection.transaction():
            await connection.execute("SELECT set_config('app.restore_mode', 'on', true)")
            references = await _all_references(connection)
            mappings = {
                (remap.physical_key, remap.source_version_id): remap for remap in version_map
            }
            missing = {
                (physical_key, version_id)
                for _, _, _, physical_key, version_id in references
                if (physical_key, version_id) not in mappings
            }
            if missing:
                raise RuntimeError("restore version map omits database references")
            updated = 0
            for remap in version_map:
                tenant_id, object_key = logical_key(remap.physical_key)
                counts = await _reference_counts(connection, tenant_id, object_key, remap)
                for table in ("raw_snapshots", "storage_operations", "lifecycle_receipts"):
                    result = await connection.execute(
                        f"""UPDATE plotlot.{table}
                        SET object_version_id = $1
                        WHERE tenant_id = $2 AND object_key = $3
                          AND object_version_id = $4""",
                        remap.destination_version_id,
                        tenant_id,
                        object_key,
                        remap.source_version_id,
                    )
                    changed = int(result.rsplit(" ", 1)[-1])
                    if changed != counts[table]:
                        raise RuntimeError(f"incomplete restore remap for {table}")
                    updated += changed
                remaining = await _reference_counts(connection, tenant_id, object_key, remap)
                if any(remaining.values()):
                    raise RuntimeError("source object version remains after restore remap")
            staged_bucket = os.environ["PLOTLOT_RESTORE_STAGED_BUCKET"]
            await _validate_staged_references(connection, staged_bucket, version_map)
    finally:
        await connection.close()
    return updated


async def _all_references(
    connection: asyncpg.Connection,
) -> list[tuple[str, str, str, str, str]]:
    references: list[tuple[str, str, str, str, str]] = []
    for table in ("raw_snapshots", "storage_operations", "lifecycle_receipts"):
        rows = await connection.fetch(
            f"""SELECT tenant_id, object_key, object_version_id FROM plotlot.{table}
            WHERE object_version_id IS NOT NULL"""
        )
        references.extend(
            (
                table,
                row["tenant_id"],
                row["object_key"],
                f"tenants/{row['tenant_id']}/{row['object_key']}",
                row["object_version_id"],
            )
            for row in rows
        )
    return references


async def _validate_staged_references(
    connection: asyncpg.Connection,
    bucket: str,
    version_map: list[VersionRemap],
) -> None:
    destination_identities = {
        (remap.physical_key, remap.destination_version_id) for remap in version_map
    }
    references = await _all_references(connection)
    identities = {(physical_key, version_id) for _, _, _, physical_key, version_id in references}
    if not identities.issubset(destination_identities):
        raise RuntimeError("restored database contains unmapped object references")
    client = boto3.client(
        "s3",
        endpoint_url=os.environ["PLOTLOT_OBJECT_STORE_ENDPOINT"],
        aws_access_key_id=os.environ["PLOTLOT_OBJECT_STORE_ACCESS_KEY"],
        aws_secret_access_key=os.environ["PLOTLOT_OBJECT_STORE_SECRET_KEY"],
        region_name=os.environ.get("PLOTLOT_OBJECT_STORE_REGION", "us-east-1"),
        config=Config(s3={"addressing_style": "path"}),
    )
    for physical_key, version_id in identities:
        client.head_object(Bucket=bucket, Key=physical_key, VersionId=version_id)


def _load_version_map(path: Path) -> list[VersionRemap]:
    document = json.loads(path.read_text())
    if not isinstance(document, dict) or document.get("schema") != "PlotLotVersionMapV2":
        raise RuntimeError("restore version map is invalid")
    versions = document.get("versions")
    if not isinstance(versions, list):
        raise RuntimeError("restore version map versions are invalid")
    remaps: list[VersionRemap] = []
    identities: set[tuple[str, str]] = set()
    for value in versions:
        if not isinstance(value, dict):
            raise RuntimeError("restore version map entry is invalid")
        physical_key = value.get("physical_key")
        source_version_id = value.get("source_version_id")
        destination_version_id = value.get("destination_version_id")
        if not (
            isinstance(physical_key, str)
            and physical_key
            and isinstance(source_version_id, str)
            and source_version_id
            and isinstance(destination_version_id, str)
            and destination_version_id
        ):
            raise RuntimeError("restore version map entry is incomplete")
        remap = VersionRemap(physical_key, source_version_id, destination_version_id)
        identity = (remap.physical_key, remap.source_version_id)
        if identity in identities:
            raise RuntimeError("duplicate restore version identity")
        identities.add(identity)
        remaps.append(remap)
    return remaps


async def _reference_counts(
    connection: asyncpg.Connection,
    tenant_id: str,
    object_key: str,
    remap: VersionRemap,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in ("raw_snapshots", "storage_operations", "lifecycle_receipts"):
        counts[table] = await connection.fetchval(
            f"""SELECT count(*) FROM plotlot.{table}
            WHERE tenant_id=$1 AND object_key=$2 AND object_version_id=$3""",
            tenant_id,
            object_key,
            remap.source_version_id,
        )
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version-map", required=True, type=Path)
    arguments = parser.parse_args()
    updated = asyncio.run(
        remap_restored_object_versions(
            os.environ["PLOTLOT_RESTORE_DATABASE_URL"],
            arguments.version_map,
        )
    )
    print(json.dumps({"remapped_database_receipts": updated}, sort_keys=True))


if __name__ == "__main__":
    main()
