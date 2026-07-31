#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "anyio>=4",
#   "pydantic>=2",
#   "sqlalchemy[asyncio]>=2",
#   "asyncpg>=0.29",
# ]
# ///
# ─── How to run ───
# 1. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run: uv run python scripts/test/job_crash_matrix.py \
#      --workers 4 --kill-points claimed,started,engine-returned,outbox-written,webhook-sent \
#      --restart api,worker,database
# ──────────────────

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import anyio

from job_crash_errors import CrashHarnessError
from job_crash_infrastructure import (
    available_port,
    create_database_container,
    docker,
    migrate_database,
)
from job_crash_processes import (
    ActorSpec,
    ProcessLaunch,
    launch_actor,
    terminate,
    wait_http,
)
from job_crash_scenario import run_scenario
from job_crash_types import KillPoint, MatrixArguments, MatrixResult, Runtime, ServiceProcesses


def parse_arguments(arguments: list[str]) -> MatrixArguments:
    values = dict(zip(arguments[::2], arguments[1::2], strict=True))
    kill_points = values["--kill-points"].split(",")
    allowed: tuple[KillPoint, ...] = (
        "claimed",
        "started",
        "engine-returned",
        "outbox-written",
        "webhook-sent",
    )
    if tuple(kill_points) != allowed:
        raise CrashHarnessError("all five crash kill points are required")
    restarts = tuple(values["--restart"].split(","))
    if restarts != ("api", "worker", "database"):
        raise CrashHarnessError("api, worker, and database restarts are required")
    return MatrixArguments(
        workers=int(values["--workers"]),
        kill_points=allowed,
        restarts=restarts,
    )


async def run_matrix(arguments: MatrixArguments, root: Path, temporary: Path) -> MatrixResult:
    container = create_database_container()
    services: list[ProcessLaunch] = []
    try:
        migrate_database(container, root)
        ledger_path = temporary / "external-effects.sqlite3"
        engine_port = available_port()
        webhook_port = available_port()
        engine_service = launch_actor(
            ActorSpec(
                role="engine",
                arguments=[str(engine_port), str(ledger_path)],
                root=root,
                log_path=temporary / "engine.log",
            )
        )
        services.append(engine_service)
        webhook_service = launch_actor(
            ActorSpec(
                role="webhook",
                arguments=[str(webhook_port), str(ledger_path)],
                root=root,
                log_path=temporary / "webhook.log",
            )
        )
        services.append(webhook_service)
        wait_http(f"http://127.0.0.1:{engine_port}", engine_service.process)
        wait_http(f"http://127.0.0.1:{webhook_port}", webhook_service.process)
        runtime = Runtime(
            root=root,
            temporary=temporary,
            container=container,
            workers=arguments.workers,
            ledger_path=ledger_path,
            engine_url=f"http://127.0.0.1:{engine_port}",
            webhook_url=f"http://127.0.0.1:{webhook_port}",
        )
        scenarios = tuple(
            [await run_scenario(runtime, kill_point) for kill_point in arguments.kill_points]
        )
        return MatrixResult(
            workers=arguments.workers,
            restarts=arguments.restarts,
            services=ServiceProcesses(
                engine_pid=engine_service.process.pid,
                webhook_pid=webhook_service.process.pid,
            ),
            scenarios=scenarios,
        )
    finally:
        for service in services:
            if service.process.poll() is None:
                terminate(service)
        docker("rm", "-f", container.name)


def main(arguments: list[str]) -> None:
    root = Path(__file__).resolve().parents[2]
    parsed = parse_arguments(arguments)
    with tempfile.TemporaryDirectory(prefix="plotlot-job-crash-") as temporary:
        result = anyio.run(run_matrix, parsed, root, Path(temporary))
    print(result.model_dump_json())


if __name__ == "__main__":
    main(sys.argv[1:])
