from __future__ import annotations

import argparse
import asyncio
import json
import os
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg


def database_name(database_url: str) -> str:
    name = urlsplit(database_url).path.removeprefix("/")
    if not name or not name.replace("_", "").isalnum():
        raise ValueError("unsafe restore database name")
    return name


def database_url(database_url: str, name: str) -> str:
    parsed = urlsplit(database_url)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{name}", parsed.query, parsed.fragment))


async def create_stage(target_url: str) -> tuple[str, str]:
    stage_name = f"plotlot_restore_{uuid4().hex}"
    connection = await asyncpg.connect(database_url(target_url, "postgres"))
    try:
        await connection.execute(f'CREATE DATABASE "{stage_name}"')
    finally:
        await connection.close()
    return stage_name, database_url(target_url, stage_name)


async def promote(target_url: str, stage_name: str) -> None:
    target_name = database_name(target_url)
    backup_name = f"plotlot_previous_{uuid4().hex}"
    connection = await asyncpg.connect(database_url(target_url, "postgres"))
    try:
        await _disconnect(connection, target_name)
        await connection.execute(f'ALTER DATABASE "{target_name}" RENAME TO "{backup_name}"')
        try:
            await _disconnect(connection, stage_name)
            await connection.execute(f'ALTER DATABASE "{stage_name}" RENAME TO "{target_name}"')
        except Exception:
            await connection.execute(f'ALTER DATABASE "{backup_name}" RENAME TO "{target_name}"')
            raise
        await connection.execute(f'DROP DATABASE "{backup_name}"')
    finally:
        await connection.close()


async def drop_stage(target_url: str, stage_name: str) -> None:
    connection = await asyncpg.connect(database_url(target_url, "postgres"))
    try:
        await _disconnect(connection, stage_name)
        await connection.execute(f'DROP DATABASE IF EXISTS "{stage_name}"')
    finally:
        await connection.close()


async def _disconnect(connection: asyncpg.Connection, name: str) -> None:
    await connection.execute(
        """SELECT pg_terminate_backend(pid) FROM pg_stat_activity
        WHERE datname=$1 AND pid <> pg_backend_pid()""",
        name,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("create", "promote", "drop"))
    parser.add_argument("--stage")
    arguments = parser.parse_args()
    target_url = os.environ["TEST_DATABASE_URL"]
    if arguments.command == "create":
        stage, url = asyncio.run(create_stage(target_url))
        print(json.dumps({"stage": stage, "url": url}, sort_keys=True))
        return
    if not arguments.stage:
        raise ValueError("--stage is required")
    if arguments.command == "promote":
        asyncio.run(promote(target_url, arguments.stage))
    else:
        asyncio.run(drop_stage(target_url, arguments.stage))


if __name__ == "__main__":
    main()
