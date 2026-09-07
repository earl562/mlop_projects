#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "anyio>=4",
#   "httpx>=0.27",
#   "pydantic>=2",
#   "sqlalchemy[asyncio]>=2",
#   "asyncpg>=0.29",
# ]
# ///
# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run: invoked by job_crash_matrix.py as an engine, webhook, or worker process.
# ──────────────────

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Literal, assert_never

import anyio
import httpx
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from job_crash_errors import CrashHarnessError
from plotlot.harness.job_models import JobRecord
from plotlot.harness.job_queue_storage import PostgresJobQueueStorage


ActorRole = Literal["engine", "webhook", "worker"]
KillPoint = Literal[
    "claimed",
    "started",
    "engine-returned",
    "outbox-written",
    "webhook-sent",
    "recover",
]
ROLE_ADAPTER: TypeAdapter[ActorRole] = TypeAdapter(ActorRole)
KILL_POINT_ADAPTER: TypeAdapter[KillPoint] = TypeAdapter(KillPoint)


class EngineReply(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    revision_id: str
    host_link: str


class WebhookReply(BaseModel):
    model_config = ConfigDict(frozen=True)

    receipt_id: str


class WorkerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    database_url: str
    tenant_id: str
    kill_point: KillPoint
    stage_path: Path
    engine_url: str
    webhook_url: str


def stable_id(prefix: str, key: str) -> str:
    return f"{prefix}_{hashlib.sha256(key.encode()).hexdigest()[:20]}"


def record_engine(path: Path, effect_key: str) -> EngineReply:
    values = (
        effect_key,
        stable_id("engrun", effect_key),
        stable_id("engrev", effect_key),
        f"plotlot://host-engine/{stable_id('link', effect_key)}",
    )
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """INSERT INTO engine_effects
               (effect_key, run_id, revision_id, host_link, attempts)
               VALUES (?, ?, ?, ?, 1)
               ON CONFLICT(effect_key) DO UPDATE SET attempts=attempts + 1
               RETURNING run_id, revision_id, host_link""",
            values,
        ).fetchone()
    assert row is not None
    return EngineReply(run_id=row[0], revision_id=row[1], host_link=row[2])


def record_webhook(path: Path, effect_key: str) -> WebhookReply:
    values = (effect_key, stable_id("receipt", effect_key))
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """INSERT INTO webhook_effects (effect_key, receipt_id, attempts)
               VALUES (?, ?, 1)
               ON CONFLICT(effect_key) DO UPDATE SET attempts=attempts + 1
               RETURNING receipt_id""",
            values,
        ).fetchone()
    assert row is not None
    return WebhookReply(receipt_id=row[0])


def serve(role: Literal["engine", "webhook"], port: int, ledger_path: Path) -> None:
    with sqlite3.connect(ledger_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS engine_effects (
              effect_key TEXT PRIMARY KEY, run_id TEXT NOT NULL,
              revision_id TEXT NOT NULL, host_link TEXT NOT NULL,
              attempts INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS webhook_effects (
              effect_key TEXT PRIMARY KEY, receipt_id TEXT NOT NULL,
              attempts INTEGER NOT NULL
            );
            """
        )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers["content-length"])
            payload = json.loads(self.rfile.read(length))
            effect_key = str(payload["idempotency_key"])
            match role:
                case "engine":
                    body = record_engine(ledger_path, effect_key).model_dump_json()
                case "webhook":
                    body = record_webhook(ledger_path, effect_key).model_dump_json()
                case unreachable:
                    assert_never(unreachable)
            encoded = body.encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: JsonValue) -> None:
            del format, args

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


def new_store(database_url: str) -> tuple[PostgresJobQueueStorage, AsyncEngine]:
    engine = create_async_engine(database_url, pool_size=2, max_overflow=0)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_provider() -> AsyncSession:
        return factory()

    return PostgresJobQueueStorage(session_provider), engine


async def pause_at(config: WorkerConfig, stage: KillPoint) -> None:
    if config.kill_point == stage:
        config.stage_path.write_text(
            json.dumps({"pid": os.getpid(), "stage": stage}),
            encoding="utf-8",
        )
        await anyio.sleep_forever()


async def post_json(url: str, payload: dict[str, JsonValue]) -> httpx.Response:
    timeout = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
    transport = httpx.AsyncHTTPTransport(retries=3)
    async with httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        limits=limits,
        follow_redirects=True,
    ) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response


async def execute_job(
    store: PostgresJobQueueStorage,
    config: WorkerConfig,
    job: JobRecord,
) -> None:
    assert job.lease_token is not None
    await pause_at(config, "claimed")
    job = await store.mark_started(config.tenant_id, job.job_id, job.lease_token)
    await pause_at(config, "started")
    engine_response = await post_json(
        config.engine_url,
        {"idempotency_key": str(job.job_id), "body_sha256": job.body_sha256},
    )
    engine_reply = EngineReply.model_validate(engine_response.json())
    await pause_at(config, "engine-returned")
    assert job.lease_token is not None
    await store.complete(
        tenant_id=config.tenant_id,
        job_id=job.job_id,
        lease_token=job.lease_token,
        engine_run_id=engine_reply.run_id,
        engine_revision_id=engine_reply.revision_id,
        notification={"kind": "released", "host_link": engine_reply.host_link},
    )
    await pause_at(config, "outbox-written")


async def deliver_outbox(store: PostgresJobQueueStorage, config: WorkerConfig) -> bool:
    delivery = await store.claim_outbox(
        tenant_id=config.tenant_id,
        worker_id=f"worker-{os.getpid()}",
        lease_for=timedelta(seconds=2),
    )
    if delivery is None:
        return False
    assert delivery.lease_token is not None
    response = await post_json(
        config.webhook_url,
        {"idempotency_key": delivery.receipt_key, "payload": delivery.payload},
    )
    reply = WebhookReply.model_validate(response.json())
    await pause_at(config, "webhook-sent")
    await store.acknowledge_outbox(
        tenant_id=config.tenant_id,
        outbox_id=delivery.outbox_id,
        lease_token=delivery.lease_token,
        provider_receipt_id=reply.receipt_id,
    )
    return True


async def run_primary_worker(
    store: PostgresJobQueueStorage,
    config: WorkerConfig,
) -> None:
    job = await store.claim(
        tenant_id=config.tenant_id,
        worker_id=f"worker-{os.getpid()}",
        lease_for=timedelta(seconds=2),
    )
    if job is None:
        await anyio.sleep_forever()
        return
    await execute_job(store, config, job)
    await deliver_outbox(store, config)


async def run_worker(config: WorkerConfig) -> None:
    store, engine = new_store(config.database_url)
    try:
        match config.kill_point:
            case "recover":
                for _ in range(40):
                    job = await store.claim(
                        tenant_id=config.tenant_id,
                        worker_id=f"worker-{os.getpid()}",
                        lease_for=timedelta(seconds=2),
                    )
                    if job is not None:
                        await execute_job(store, config, job)
                    if await deliver_outbox(store, config):
                        return
                    await anyio.sleep(0.25)
                raise CrashHarnessError("worker recovery timed out")
            case "claimed" | "started" | "engine-returned" | "outbox-written" | "webhook-sent":
                await run_primary_worker(store, config)
            case unreachable:
                assert_never(unreachable)
    finally:
        await engine.dispose()


def main(arguments: list[str]) -> None:
    role = ROLE_ADAPTER.validate_python(arguments[0])
    match role:
        case "engine" | "webhook":
            serve(role, int(arguments[1]), Path(arguments[2]))
        case "worker":
            config = WorkerConfig(
                database_url=arguments[1],
                tenant_id=arguments[2],
                kill_point=KILL_POINT_ADAPTER.validate_python(arguments[3]),
                stage_path=Path(arguments[4]),
                engine_url=arguments[5],
                webhook_url=arguments[6],
            )
            anyio.run(run_worker, config)
        case unreachable:
            assert_never(unreachable)


if __name__ == "__main__":
    main(sys.argv[1:])
