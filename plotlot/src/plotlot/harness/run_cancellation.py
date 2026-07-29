from __future__ import annotations

from dataclasses import dataclass

from plotlot.harness.job_models import JobId, JobRecord
from plotlot.harness.job_queue_storage import PostgresJobQueueStorage


@dataclass(frozen=True, slots=True)
class CancellationRequest:
    tenant_id: str
    job_id: JobId
    actor_id: str
    reason: str


async def cancel_run(
    storage: PostgresJobQueueStorage,
    request: CancellationRequest,
) -> JobRecord:
    return await storage.cancel(
        tenant_id=request.tenant_id,
        job_id=request.job_id,
        actor_id=request.actor_id,
        reason=request.reason,
    )
