#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "asyncpg>=0.29",
#   "httpx>=0.27",
# ]
# ///
# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run: imported by job_crash_matrix.py; it is not a standalone command.
# ──────────────────

from __future__ import annotations

import os
import secrets
import socket
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import anyio


@dataclass(frozen=True, slots=True)
class DatabaseContainer:
    name: str
    database_url: str


@dataclass(frozen=True, slots=True)
class DatabaseRestart:
    before_backend_pid: int
    after_backend_pid: int
    before_start_time: str
    after_start_time: str
    connection_severed: bool


@dataclass(frozen=True, slots=True)
class ExternalEffects:
    effects: int
    attempts: int
    effect_id: str
    revision_id: str | None = None
    host_link: str | None = None


def available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def docker(*arguments: str) -> str:
    result = subprocess.run(
        ["docker", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def wait_database(container_name: str) -> None:
    for _ in range(60):
        result = subprocess.run(
            [
                "docker",
                "exec",
                container_name,
                "pg_isready",
                "-U",
                "task11_admin",
                "-d",
                "plotlot_task11",
            ],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            return
        time.sleep(0.25)
    raise TimeoutError(f"PostgreSQL container {container_name} was not ready")


def create_database_container() -> DatabaseContainer:
    name = f"plotlot-task11-crash-{os.getpid()}"
    password = secrets.token_urlsafe(24)
    port = available_port()
    docker(
        "run",
        "-d",
        "--name",
        name,
        "-e",
        "POSTGRES_USER=task11_admin",
        "-e",
        f"POSTGRES_PASSWORD={password}",
        "-e",
        "POSTGRES_DB=plotlot_task11",
        "-p",
        f"127.0.0.1:{port}:5432",
        "pgvector/pgvector:pg16",
    )
    wait_database(name)
    return DatabaseContainer(
        name=name,
        database_url=(
            f"postgresql+asyncpg://task11_admin:{password}@127.0.0.1:{port}/plotlot_task11"
        ),
    )


def migrate_database(container: DatabaseContainer, root: Path) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = container.database_url
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
    )


async def restart_database(container: DatabaseContainer) -> DatabaseRestart:
    connection = await asyncpg.connect(container.database_url.replace("+asyncpg", ""))
    before = await connection.fetchrow(
        "SELECT pg_backend_pid() AS pid, pg_postmaster_start_time()::text AS started"
    )
    assert before is not None
    docker("stop", "--time", "2", container.name)
    severed = False
    try:
        await connection.fetchval("SELECT 1")
    except (
        asyncpg.PostgresConnectionError,
        asyncpg.InterfaceError,
        ConnectionError,
        OSError,
    ):
        severed = True
    await connection.close()
    docker("start", container.name)
    wait_database(container.name)
    recovered: asyncpg.Connection | None = None
    for _ in range(40):
        try:
            recovered = await asyncpg.connect(container.database_url.replace("+asyncpg", ""))
        except (asyncpg.PostgresConnectionError, OSError):
            await anyio.sleep(0.1)
            continue
        break
    if recovered is None:
        raise TimeoutError(f"published PostgreSQL port for {container.name} was not ready")
    try:
        after = await recovered.fetchrow(
            "SELECT pg_backend_pid() AS pid, pg_postmaster_start_time()::text AS started"
        )
    finally:
        await recovered.close()
    assert after is not None
    return DatabaseRestart(
        before_backend_pid=before["pid"],
        after_backend_pid=after["pid"],
        before_start_time=before["started"],
        after_start_time=after["started"],
        connection_severed=severed,
    )


def external_effects(
    ledger_path: Path,
    table: str,
    effect_key: str,
) -> ExternalEffects:
    columns = (
        "run_id, revision_id, host_link, attempts"
        if table == "engine_effects"
        else "receipt_id, NULL, NULL, attempts"
    )
    with sqlite3.connect(ledger_path) as connection:
        row = connection.execute(
            f"SELECT {columns} FROM {table} WHERE effect_key=?",  # noqa: S608
            (effect_key,),
        ).fetchone()
        effects = connection.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
    assert row is not None
    assert effects is not None
    return ExternalEffects(
        effects=effects[0],
        attempts=row[3],
        effect_id=row[0],
        revision_id=row[1],
        host_link=row[2],
    )
