"""Add tenant-owned leased jobs and transactional outbox.

Revision ID: 015_leased_jobs_outbox
Revises: 014_tenant_authorization_rls
Create Date: 2026-07-29
"""

from typing import Sequence, Union

from alembic import op


revision: str = "015_leased_jobs_outbox"
down_revision: Union[str, None] = "014_tenant_authorization_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    statements = (
        """CREATE TABLE plotlot.jobs (
        tenant_id varchar(120) NOT NULL,
        job_id uuid NOT NULL,
        idempotency_key varchar(200) NOT NULL,
        body_sha256 char(64) NOT NULL,
        body jsonb NOT NULL,
        status varchar(24) NOT NULL DEFAULT 'queued',
        attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
        max_attempts integer NOT NULL CHECK (max_attempts BETWEEN 1 AND 20),
        available_at timestamptz NOT NULL DEFAULT now(),
        lease_owner varchar(200),
        lease_token uuid,
        lease_expires_at timestamptz,
        replay_of_job_id uuid,
        last_error text,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, job_id),
        UNIQUE (tenant_id, idempotency_key),
        CHECK (status IN (
          'queued', 'leased', 'running', 'retry_wait', 'completed',
          'cancelled', 'dead_lettered')),
        CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL)))""",
        """CREATE INDEX jobs_claimable_idx
        ON plotlot.jobs (available_at, created_at)
        WHERE status IN ('queued', 'retry_wait', 'leased', 'running')""",
        """CREATE TABLE plotlot.job_events (
        cursor bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        tenant_id varchar(120) NOT NULL,
        job_id uuid NOT NULL,
        event_type varchar(80) NOT NULL,
        payload jsonb NOT NULL DEFAULT '{}',
        created_at timestamptz NOT NULL DEFAULT now(),
        FOREIGN KEY (tenant_id, job_id)
          REFERENCES plotlot.jobs (tenant_id, job_id))""",
        """CREATE INDEX job_events_stream_idx
        ON plotlot.job_events (tenant_id, job_id, cursor)""",
        """CREATE TABLE plotlot.job_terminal_results (
        tenant_id varchar(120) NOT NULL,
        job_id uuid NOT NULL,
        engine_run_id varchar(120) NOT NULL,
        engine_revision_id varchar(120) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, job_id),
        UNIQUE (tenant_id, engine_run_id, engine_revision_id),
        FOREIGN KEY (tenant_id, job_id)
          REFERENCES plotlot.jobs (tenant_id, job_id))""",
        """CREATE TABLE plotlot.job_outbox (
        tenant_id varchar(120) NOT NULL,
        outbox_id uuid NOT NULL,
        job_id uuid NOT NULL,
        receipt_key varchar(300) NOT NULL,
        payload jsonb NOT NULL,
        status varchar(24) NOT NULL DEFAULT 'pending',
        attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
        max_attempts integer NOT NULL DEFAULT 8 CHECK (max_attempts BETWEEN 1 AND 20),
        available_at timestamptz NOT NULL DEFAULT now(),
        lease_owner varchar(200),
        lease_token uuid,
        lease_expires_at timestamptz,
        last_error text,
        sent_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, outbox_id),
        UNIQUE (tenant_id, receipt_key),
        FOREIGN KEY (tenant_id, job_id)
          REFERENCES plotlot.jobs (tenant_id, job_id),
        CHECK (status IN ('pending', 'leased', 'retry_wait', 'sent', 'dead_lettered')),
        CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL)))""",
        """CREATE INDEX job_outbox_claimable_idx
        ON plotlot.job_outbox (available_at, created_at)
        WHERE status IN ('pending', 'retry_wait', 'leased')""",
        """CREATE TABLE plotlot.notification_receipts (
        tenant_id varchar(120) NOT NULL,
        outbox_id uuid NOT NULL,
        job_id uuid NOT NULL,
        provider_receipt_id varchar(300) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, outbox_id),
        UNIQUE (tenant_id, provider_receipt_id),
        FOREIGN KEY (tenant_id, outbox_id)
          REFERENCES plotlot.job_outbox (tenant_id, outbox_id))""",
    )
    for statement in statements:
        op.execute(statement)
    for table_name in (
        "jobs",
        "job_events",
        "job_terminal_results",
        "job_outbox",
        "notification_receipts",
    ):
        op.execute(f"ALTER TABLE plotlot.{table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE plotlot.{table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""CREATE POLICY tenant_isolation ON plotlot.{table_name}
            USING (tenant_id = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"""
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON plotlot.{table_name} TO plotlot_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE plotlot.job_events_cursor_seq TO plotlot_app")


def downgrade() -> None:
    for table_name in (
        "notification_receipts",
        "job_outbox",
        "job_terminal_results",
        "job_events",
        "jobs",
    ):
        op.execute(f"DROP TABLE IF EXISTS plotlot.{table_name}")
