#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "asyncpg>=0.29",
#   "sqlalchemy[asyncio]>=2",
# ]
# ///
# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run: imported by job_crash_matrix.py; it is not a standalone command.
# ──────────────────

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import asyncpg
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from job_crash_errors import CrashHarnessError
from job_crash_infrastructure import (
    available_port,
    external_effects,
    restart_database,
)
from job_crash_processes import (
    ActorSpec,
    ApiSpec,
    ProcessLaunch,
    ProcessRestart,
    launch_actor,
    launch_api,
    terminate,
    wait_http,
)
from job_crash_types import (
    EngineObservable,
    KillPoint,
    NotificationPayload,
    OutboxObservable,
    Runtime,
    ScenarioResult,
    StageSignal,
    TerminalObservable,
    WebhookObservable,
)
from plotlot.harness.job_models import JobCreate, JobId
from plotlot.harness.job_queue_storage import PostgresJobQueueStorage


def new_store(database_url: str) -> tuple[PostgresJobQueueStorage, AsyncEngine]:
    engine = create_async_engine(database_url, pool_size=4, max_overflow=4)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_provider() -> AsyncSession:
        return factory()

    return PostgresJobQueueStorage(session_provider), engine


def clear_ledger(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM engine_effects")
        connection.execute("DELETE FROM webhook_effects")


def worker_arguments(runtime: Runtime, kill_point: str, stage_path: Path) -> list[str]:
    return [
        runtime.container.database_url,
        "tenant_crash_matrix",
        kill_point,
        str(stage_path),
        runtime.engine_url,
        runtime.webhook_url,
    ]


def wait_stage(
    launches: list[ProcessLaunch],
    stage_path: Path,
    expected: KillPoint,
) -> int:
    for _ in range(160):
        if stage_path.exists():
            observed = StageSignal.model_validate_json(stage_path.read_text(encoding="utf-8"))
            contender_pids = {launch.process.pid for launch in launches}
            assert observed.pid in contender_pids
            assert observed.stage == expected
            return int(observed.pid)
        for launch in launches:
            if launch.process.poll() is not None:
                details = launch.log_path.read_text(encoding="utf-8")
                raise CrashHarnessError(f"worker exited before {expected}: {details}")
        time.sleep(0.1)
    raise TimeoutError(f"worker did not reach {expected}")


async def stored_observables(
    database_url: str,
    tenant_id: str,
    job_id: JobId,
) -> tuple[TerminalObservable, OutboxObservable]:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        terminal = await connection.fetchrow(
            """SELECT count(*) OVER () AS result_count, engine_run_id, engine_revision_id
               FROM plotlot.job_terminal_results
               WHERE tenant_id=$1 AND job_id=$2""",
            tenant_id,
            job_id,
        )
        outbox = await connection.fetchrow(
            """SELECT item.payload, count(receipt.*) OVER () AS receipt_count,
                      receipt.provider_receipt_id
               FROM plotlot.job_outbox AS item
               JOIN plotlot.notification_receipts AS receipt
                 ON receipt.tenant_id=item.tenant_id AND receipt.outbox_id=item.outbox_id
               WHERE item.tenant_id=$1 AND item.job_id=$2""",
            tenant_id,
            job_id,
        )
    finally:
        await connection.close()
    assert terminal is not None
    assert outbox is not None
    notification = NotificationPayload.model_validate_json(outbox["payload"])
    return (
        TerminalObservable(
            results=terminal["result_count"],
            engine_run_id=terminal["engine_run_id"],
            engine_revision_id=terminal["engine_revision_id"],
        ),
        OutboxObservable(
            receipts=outbox["receipt_count"],
            provider_receipt_id=outbox["provider_receipt_id"],
            host_link=notification.host_link,
        ),
    )


async def run_scenario(runtime: Runtime, kill_point: KillPoint) -> ScenarioResult:
    tenant_id = "tenant_crash_matrix"
    store, engine = new_store(runtime.container.database_url)
    launches: list[ProcessLaunch] = []
    try:
        await store.clear_for_tests()
        clear_ledger(runtime.ledger_path)
        created = await store.enqueue(
            JobCreate(
                tenant_id=tenant_id,
                idempotency_key=f"matrix-{kill_point}-00000001",
                body={"subject": "synthetic-crash-subject"},
                max_attempts=4,
            )
        )
        api_port = available_port()
        api_before = launch_api(
            ApiSpec(
                root=runtime.root,
                database_url=runtime.container.database_url,
                port=api_port,
                log_path=runtime.temporary / f"{kill_point}-api-before.log",
            )
        )
        launches.append(api_before)
        health_before = wait_http(f"http://127.0.0.1:{api_port}/health", api_before.process)
        stage_path = runtime.temporary / f"{kill_point}.stage"
        contenders = [
            launch_actor(
                ActorSpec(
                    role="worker",
                    arguments=worker_arguments(runtime, kill_point, stage_path),
                    root=runtime.root,
                    log_path=runtime.temporary / f"{kill_point}-worker-{index}.log",
                )
            )
            for index in range(runtime.workers)
        ]
        launches.extend(contenders)
        winner_pid = wait_stage(contenders, stage_path, kill_point)
        worker_exits = [terminate(contender) for contender in contenders]
        terminate(api_before)
        database = await restart_database(runtime.container)
        api_after = launch_api(
            ApiSpec(
                root=runtime.root,
                database_url=runtime.container.database_url,
                port=api_port,
                log_path=runtime.temporary / f"{kill_point}-api-after.log",
            )
        )
        launches.append(api_after)
        health_after = wait_http(f"http://127.0.0.1:{api_port}/health", api_after.process)
        worker_after = launch_actor(
            ActorSpec(
                role="worker",
                arguments=worker_arguments(runtime, "recover", runtime.temporary / "unused.stage"),
                root=runtime.root,
                log_path=runtime.temporary / f"{kill_point}-worker-after.log",
            )
        )
        launches.append(worker_after)
        if worker_after.process.wait(timeout=30) != 0:
            details = worker_after.log_path.read_text(encoding="utf-8")
            raise CrashHarnessError(f"recovery worker failed: {details}")
        terminal, outbox = await stored_observables(
            runtime.container.database_url,
            tenant_id,
            created.job_id,
        )
        engine_effect = external_effects(
            runtime.ledger_path,
            "engine_effects",
            str(created.job_id),
        )
        webhook_effect = external_effects(
            runtime.ledger_path,
            "webhook_effects",
            f"job-terminal:{created.job_id}",
        )
        engine_observable = EngineObservable(
            effects=engine_effect.effects,
            attempts=engine_effect.attempts,
            run_id=engine_effect.effect_id,
            revision_id=str(engine_effect.revision_id),
            host_link=str(engine_effect.host_link),
        )
        webhook_observable = WebhookObservable(
            effects=webhook_effect.effects,
            attempts=webhook_effect.attempts,
            receipt_id=webhook_effect.effect_id,
        )
        assert database.connection_severed
        assert database.before_start_time != database.after_start_time
        assert engine_observable.effects == 1
        assert engine_observable.attempts == (2 if kill_point == "engine-returned" else 1)
        assert webhook_observable.effects == 1
        assert webhook_observable.attempts == (2 if kill_point == "webhook-sent" else 1)
        assert terminal.engine_run_id == engine_observable.run_id
        assert terminal.engine_revision_id == engine_observable.revision_id
        assert outbox.host_link == engine_observable.host_link
        assert outbox.provider_receipt_id == webhook_observable.receipt_id
        return ScenarioResult(
            kill_point=kill_point,
            api=ProcessRestart(
                before_pid=api_before.process.pid,
                after_pid=api_after.process.pid,
                health_before=health_before,
                health_after=health_after,
            ),
            worker=ProcessRestart(
                before_pid=winner_pid,
                after_pid=worker_after.process.pid,
                contender_pids=tuple(contender.process.pid for contender in contenders),
                killed=all(exit_code < 0 for exit_code in worker_exits),
            ),
            database=database,
            engine=engine_observable,
            webhook=webhook_observable,
            terminal=terminal,
            outbox=outbox,
        )
    finally:
        await engine.dispose()
        for launch in launches:
            if launch.process.poll() is None:
                terminate(launch)
