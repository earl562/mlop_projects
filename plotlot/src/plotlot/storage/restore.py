from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import asyncpg


def _asyncpg_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def remap_restored_object_versions(
    database_url: str,
    version_map_path: Path,
) -> int:
    version_map = json.loads(version_map_path.read_text())
    if not isinstance(version_map, dict) or not all(
        isinstance(source, str) and isinstance(destination, str)
        for source, destination in version_map.items()
    ):
        raise RuntimeError("restore version map is invalid")
    connection = await asyncpg.connect(_asyncpg_url(database_url))
    try:
        async with connection.transaction():
            await connection.execute("SELECT set_config('app.restore_mode', 'on', true)")
            updated = 0
            for source_version, destination_version in version_map.items():
                result = await connection.execute(
                    """UPDATE plotlot.raw_snapshots
                    SET object_version_id = $1
                    WHERE object_version_id = $2""",
                    destination_version,
                    source_version,
                )
                updated += int(result.rsplit(" ", 1)[-1])
    finally:
        await connection.close()
    return updated


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
