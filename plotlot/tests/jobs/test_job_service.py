from __future__ import annotations

from datetime import timedelta

from pydantic import JsonValue

from plotlot.harness.job_models import JobCreate, JobStatus
from plotlot.harness.job_queue import EngineResult, HarnessJobQueue
from plotlot.harness.job_queue_storage import PostgresJobQueueStorage


class DeterministicEngine:
    async def run(
        self,
        body: dict[str, JsonValue],
        idempotency_key: str,
    ) -> EngineResult:
        del body, idempotency_key
        return EngineResult(
            engine_run_id="engrun_service",
            engine_revision_id="engrev_service",
            notification={"kind": "release"},
        )


async def test_worker_service_claims_starts_and_persists_atomically(
    job_store: PostgresJobQueueStorage,
) -> None:
    created = await job_store.enqueue(
        JobCreate(
            tenant_id="tenant_jobs_a",
            idempotency_key="service-key-000001",
            body={"subject": "redacted-test-subject"},
            max_attempts=3,
        )
    )
    queue = HarnessJobQueue(job_store, DeterministicEngine())

    completed = await queue.run_once(
        tenant_id=created.tenant_id,
        worker_id="worker-service",
        lease_for=timedelta(seconds=30),
    )

    assert completed is not None
    assert completed.status is JobStatus.COMPLETED
    assert await job_store.count_terminal_results(created.tenant_id, created.job_id) == 1
    assert await job_store.count_outbox(created.tenant_id, created.job_id) == 1
