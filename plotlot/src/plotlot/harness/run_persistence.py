from __future__ import annotations

from pydantic import JsonValue

from plotlot.harness.job_models import JobRecord, LeaseInvariantError
from plotlot.harness.job_queue_storage import PostgresJobQueueStorage


async def persist_engine_result(
    storage: PostgresJobQueueStorage,
    leased_job: JobRecord,
    *,
    engine_run_id: str,
    engine_revision_id: str,
    notification: dict[str, JsonValue],
) -> JobRecord:
    if leased_job.lease_token is None:
        raise LeaseInvariantError("leased job has no fencing token")
    return await storage.complete(
        tenant_id=leased_job.tenant_id,
        job_id=leased_job.job_id,
        lease_token=leased_job.lease_token,
        engine_run_id=engine_run_id,
        engine_revision_id=engine_revision_id,
        notification=notification,
    )
