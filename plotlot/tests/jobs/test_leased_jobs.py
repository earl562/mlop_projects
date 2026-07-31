from __future__ import annotations

from datetime import timedelta

import anyio

from plotlot.harness.job_models import JobCreate, JobStatus
from plotlot.harness.job_queue_storage import PostgresJobQueueStorage


TENANT = "tenant_jobs_a"


def command(key: str, *, max_attempts: int = 3) -> JobCreate:
    return JobCreate(
        tenant_id=TENANT,
        idempotency_key=key,
        body={"subject": "synthetic-job-subject", "analysis_type": "acquisition"},
        max_attempts=max_attempts,
    )


async def test_four_workers_atomically_claim_one_job(
    job_store: PostgresJobQueueStorage,
) -> None:
    job = await job_store.enqueue(command("atomic-claim-key"))
    claims = []

    async def claim(worker: str) -> None:
        claims.append(
            await job_store.claim(
                tenant_id=TENANT,
                worker_id=worker,
                lease_for=timedelta(seconds=30),
            )
        )

    async with anyio.create_task_group() as group:
        for index in range(4):
            group.start_soon(claim, f"worker-{index}")

    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1
    assert winners[0].job_id == job.job_id
    assert winners[0].attempts == 1


async def test_expired_lease_is_reacquired_and_heartbeat_fences_old_worker(
    job_store: PostgresJobQueueStorage,
) -> None:
    await job_store.enqueue(command("lease-expiry-key"))
    first = await job_store.claim(
        tenant_id=TENANT,
        worker_id="worker-old",
        lease_for=timedelta(milliseconds=1),
    )
    assert first is not None
    await anyio.sleep(0.02)

    second = await job_store.claim(
        tenant_id=TENANT,
        worker_id="worker-new",
        lease_for=timedelta(seconds=30),
    )
    assert second is not None
    assert second.job_id == first.job_id
    assert second.lease_token != first.lease_token
    assert not await job_store.heartbeat(
        TENANT,
        first.job_id,
        first.lease_token,
        lease_for=timedelta(seconds=30),
    )
    assert await job_store.heartbeat(
        TENANT,
        second.job_id,
        second.lease_token,
        lease_for=timedelta(seconds=30),
    )


async def test_bounded_retry_dead_letters_and_admin_requeue_recovers(
    job_store: PostgresJobQueueStorage,
) -> None:
    await job_store.enqueue(command("bounded-retry-key", max_attempts=2))
    first = await job_store.claim(
        tenant_id=TENANT,
        worker_id="worker-1",
        lease_for=timedelta(seconds=30),
    )
    assert first is not None
    retried = await job_store.fail(
        TENANT,
        first.job_id,
        first.lease_token,
        "temporary",
    )
    assert retried.status is JobStatus.RETRY_WAIT
    await job_store.make_retry_ready_for_tests(first.job_id)

    second = await job_store.claim(
        tenant_id=TENANT,
        worker_id="worker-2",
        lease_for=timedelta(seconds=30),
    )
    assert second is not None
    dead = await job_store.fail(
        TENANT,
        second.job_id,
        second.lease_token,
        "still broken",
    )
    assert dead.status is JobStatus.DEAD_LETTERED
    assert dead.last_error == "still broken"
    assert [job.job_id for job in await job_store.dead_letters(TENANT)] == [dead.job_id]

    requeued = await job_store.requeue_dead_letter(
        tenant_id=TENANT,
        job_id=dead.job_id,
        actor_id="admin-1",
    )
    assert requeued.status is JobStatus.QUEUED
    assert requeued.attempts == 0
