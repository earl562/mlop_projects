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
# DATABASE_URL=<redacted-postgres-url> uv run python scripts/test/job_crash_matrix.py \
#   --workers 4 --kill-points claimed,started,engine-returned,outbox-written,webhook-sent \
#   --restart api,worker,database

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import timedelta

import anyio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from plotlot.harness.job_models import JobCreate, JobRecord
from plotlot.harness.job_queue_storage import PostgresJobQueueStorage


@dataclass(frozen=True, slots=True)
class MatrixArguments:
    workers: int
    kill_points: tuple[str, ...]
    restarts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StoreRuntime:
    store: PostgresJobQueueStorage
    engine: AsyncEngine


@dataclass(frozen=True, slots=True)
class MatrixInvariantError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


def parse_arguments(arguments: list[str]) -> MatrixArguments:
    values = dict(zip(arguments[::2], arguments[1::2], strict=True))
    return MatrixArguments(
        workers=int(values["--workers"]),
        kill_points=tuple(values["--kill-points"].split(",")),
        restarts=tuple(values["--restart"].split(",")),
    )


def new_runtime(database_url: str) -> StoreRuntime:
    engine = create_async_engine(database_url, pool_size=8, max_overflow=8)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_provider() -> AsyncSession:
        return factory()

    return StoreRuntime(
        store=PostgresJobQueueStorage(session_provider),
        engine=engine,
    )


async def restart_runtime(runtime: StoreRuntime, database_url: str) -> StoreRuntime:
    await runtime.engine.dispose()
    return new_runtime(database_url)


async def restart_components(
    runtime: StoreRuntime,
    database_url: str,
    components: tuple[str, ...],
) -> StoreRuntime:
    for component in components:
        if component not in {"api", "worker", "database"}:
            raise MatrixInvariantError(f"unsupported restart component: {component}")
        runtime = await restart_runtime(runtime, database_url)
    return runtime


async def claim_with_workers(
    store: PostgresJobQueueStorage,
    tenant_id: str,
    workers: int,
) -> tuple[JobRecord, int]:
    claims: list[JobRecord | None] = []

    async def claim(index: int) -> None:
        claims.append(
            await store.claim(
                tenant_id=tenant_id,
                worker_id=f"matrix-worker-{index}",
                lease_for=timedelta(seconds=30),
            )
        )

    async with anyio.create_task_group() as group:
        for index in range(workers):
            group.start_soon(claim, index)
    winners = [claim for claim in claims if claim is not None]
    if len(winners) != 1:
        raise MatrixInvariantError(f"atomic claim expected one winner, observed {len(winners)}")
    return winners[0], max(0, len(winners) - 1)


async def finish_job(
    runtime: StoreRuntime,
    database_url: str,
    restarts: tuple[str, ...],
    tenant_id: str,
    claimed: JobRecord,
    kill_point: str,
) -> StoreRuntime:
    if claimed.lease_token is None:
        raise MatrixInvariantError("claimed job has no lease token")
    if kill_point in {"started", "engine-returned"}:
        await runtime.store.mark_started(tenant_id, claimed.job_id, claimed.lease_token)
    if kill_point in {"claimed", "started", "engine-returned"}:
        await runtime.store.expire_job_lease_for_tests(claimed.job_id)
        runtime = await restart_components(runtime, database_url, restarts)
        reacquired = await runtime.store.claim(
            tenant_id=tenant_id,
            worker_id="matrix-recovery-worker",
            lease_for=timedelta(seconds=30),
        )
        if reacquired is None or reacquired.lease_token is None:
            raise MatrixInvariantError(f"{kill_point} was not recovered after restart")
        claimed = await runtime.store.mark_started(
            tenant_id,
            reacquired.job_id,
            reacquired.lease_token,
        )
    if claimed.lease_token is None:
        raise MatrixInvariantError("running job has no lease token")
    if kill_point not in {"outbox-written", "webhook-sent"}:
        await runtime.store.complete(
            tenant_id=tenant_id,
            job_id=claimed.job_id,
            lease_token=claimed.lease_token,
            engine_run_id="engrun_crash_matrix",
            engine_revision_id="engrev_crash_matrix",
            notification={"kind": "release"},
        )
    return runtime


async def deliver_notification(
    runtime: StoreRuntime,
    database_url: str,
    restarts: tuple[str, ...],
    tenant_id: str,
    kill_point: str,
) -> StoreRuntime:
    delivery = await runtime.store.claim_outbox(
        tenant_id=tenant_id,
        worker_id="matrix-delivery-worker",
        lease_for=timedelta(seconds=30),
    )
    if delivery is None or delivery.lease_token is None:
        raise MatrixInvariantError("outbox was not claimable")
    if kill_point == "webhook-sent":
        await runtime.store.expire_outbox_lease_for_tests(delivery.outbox_id)
        runtime = await restart_components(runtime, database_url, restarts)
        delivery = await runtime.store.claim_outbox(
            tenant_id=tenant_id,
            worker_id="matrix-delivery-recovery",
            lease_for=timedelta(seconds=30),
        )
        if delivery is None or delivery.lease_token is None:
            raise MatrixInvariantError("sent webhook lease was not recovered")
    await runtime.store.acknowledge_outbox(
        tenant_id=tenant_id,
        outbox_id=delivery.outbox_id,
        lease_token=delivery.lease_token,
        provider_receipt_id="provider-crash-matrix-receipt",
    )
    return runtime


async def run_scenario(
    database_url: str,
    arguments: MatrixArguments,
    kill_point: str,
) -> dict[str, int | str]:
    tenant_id = "tenant_crash_matrix"
    runtime = new_runtime(database_url)
    await runtime.store.clear_for_tests()
    created = await runtime.store.enqueue(
        JobCreate(
            tenant_id=tenant_id,
            idempotency_key=f"matrix-{kill_point}-00000001",
            body={"subject": "redacted-test-subject"},
            max_attempts=4,
        )
    )
    claimed, double_claims = await claim_with_workers(
        runtime.store,
        tenant_id,
        arguments.workers,
    )
    if kill_point in {"outbox-written", "webhook-sent"}:
        if claimed.lease_token is None:
            raise MatrixInvariantError("claimed job has no lease token")
        claimed = await runtime.store.mark_started(
            tenant_id,
            claimed.job_id,
            claimed.lease_token,
        )
        if claimed.lease_token is None:
            raise MatrixInvariantError("running job has no lease token")
        await runtime.store.complete(
            tenant_id=tenant_id,
            job_id=claimed.job_id,
            lease_token=claimed.lease_token,
            engine_run_id="engrun_crash_matrix",
            engine_revision_id="engrev_crash_matrix",
            notification={"kind": "release"},
        )
        runtime = await restart_components(runtime, database_url, arguments.restarts)
    else:
        runtime = await finish_job(
            runtime,
            database_url,
            arguments.restarts,
            tenant_id,
            claimed,
            kill_point,
        )
    runtime = await deliver_notification(
        runtime,
        database_url,
        arguments.restarts,
        tenant_id,
        kill_point,
    )
    result = {
        "kill_point": kill_point,
        "terminal_results": await runtime.store.count_terminal_results(
            tenant_id,
            created.job_id,
        ),
        "notification_receipts": await runtime.store.count_notification_receipts(
            tenant_id,
            created.job_id,
        ),
        "double_claims": double_claims,
    }
    await runtime.engine.dispose()
    return result


async def main(arguments: MatrixArguments) -> None:
    database_url = os.environ["DATABASE_URL"]
    results = [
        await run_scenario(database_url, arguments, kill_point)
        for kill_point in arguments.kill_points
    ]
    if any(
        result["terminal_results"] != 1
        or result["notification_receipts"] != 1
        or result["double_claims"] != 0
        for result in results
    ):
        raise MatrixInvariantError("crash matrix invariant failed")
    print(
        json.dumps(
            {
                "workers": arguments.workers,
                "restarts": list(arguments.restarts),
                "terminal_results": 1,
                "notification_receipts": 1,
                "double_claims": 0,
                "scenarios": results,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    anyio.run(main, parse_arguments(sys.argv[1:]))
