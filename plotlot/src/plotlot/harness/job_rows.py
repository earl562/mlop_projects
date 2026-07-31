from __future__ import annotations

from sqlalchemy.engine import RowMapping

from plotlot.harness.job_models import JobEvent, JobRecord, OutboxRecord


JOB_COLUMNS = """tenant_id, job_id::text AS job_id, idempotency_key, body_sha256,
body, status, attempts, max_attempts, replay_of_job_id::text AS replay_of_job_id,
last_error, lease_token::text AS lease_token, lease_expires_at, available_at,
created_at, updated_at"""

JOB_ALIAS_COLUMNS = """job.tenant_id, job.job_id::text AS job_id,
job.idempotency_key, job.body_sha256, job.body, job.status, job.attempts,
job.max_attempts, job.replay_of_job_id::text AS replay_of_job_id, job.last_error,
job.lease_token::text AS lease_token, job.lease_expires_at, job.available_at,
job.created_at, job.updated_at"""

OUTBOX_COLUMNS = """tenant_id, outbox_id::text AS outbox_id, job_id::text AS job_id,
receipt_key, payload, status, attempts, max_attempts, lease_token::text AS lease_token,
lease_expires_at, last_error, sent_at"""

OUTBOX_ALIAS_COLUMNS = """item.tenant_id, item.outbox_id::text AS outbox_id,
item.job_id::text AS job_id, item.receipt_key, item.payload, item.status,
item.attempts, item.max_attempts, item.lease_token::text AS lease_token,
item.lease_expires_at, item.last_error, item.sent_at"""

EVENT_COLUMNS = """cursor, tenant_id, job_id::text AS job_id, event_type, payload,
created_at"""


def job_from_row(row: RowMapping) -> JobRecord:
    return JobRecord.model_validate(dict(row))


def outbox_from_row(row: RowMapping) -> OutboxRecord:
    return OutboxRecord.model_validate(dict(row))


def event_from_row(row: RowMapping) -> JobEvent:
    return JobEvent.model_validate(dict(row))
