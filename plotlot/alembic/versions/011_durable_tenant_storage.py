"""Add tenant-owned immutable storage and database role boundaries.

Revision ID: 011_durable_tenant_storage
Revises: 010_harness_source_authority_events
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op


revision: str = "011_durable_tenant_storage"
down_revision: Union[str, None] = "010_source_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    statements = (
        """DO $roles$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'plotlot_app') THEN
            CREATE ROLE plotlot_app NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'byright_engine') THEN
            CREATE ROLE byright_engine NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
          END IF;
        END
        $roles$""",
        "CREATE SCHEMA IF NOT EXISTS plotlot",
        "CREATE SCHEMA IF NOT EXISTS byright",
        "REVOKE ALL ON SCHEMA plotlot FROM PUBLIC",
        "REVOKE ALL ON SCHEMA byright FROM PUBLIC",
        "GRANT USAGE ON SCHEMA plotlot TO plotlot_app",
        "GRANT USAGE ON SCHEMA byright TO byright_engine",
        """CREATE TABLE plotlot.host_engine_links (
          tenant_id varchar(120) NOT NULL,
          host_analysis_id varchar(120) NOT NULL,
          engine_run_id varchar(120) NOT NULL,
          engine_revision_id varchar(120) NOT NULL,
          protocol_version varchar(40) NOT NULL,
          projection_sha256 varchar(64) NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (tenant_id, host_analysis_id),
          UNIQUE (tenant_id, engine_run_id, engine_revision_id)
        )""",
        """CREATE TABLE plotlot.immutable_events (
          tenant_id varchar(120) NOT NULL,
          event_id varchar(120) NOT NULL,
          aggregate_id varchar(120) NOT NULL,
          sequence bigint NOT NULL CHECK (sequence > 0),
          event_type varchar(120) NOT NULL,
          payload jsonb NOT NULL,
          payload_sha256 varchar(64) NOT NULL,
          occurred_at timestamptz NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (tenant_id, event_id),
          UNIQUE (tenant_id, aggregate_id, sequence)
        )""",
        """CREATE TABLE plotlot.evidence_records (
          tenant_id varchar(120) NOT NULL,
          evidence_id varchar(120) NOT NULL,
          object_key varchar(500) NOT NULL,
          content_sha256 varchar(64) NOT NULL,
          source_uri text NOT NULL,
          fetched_at timestamptz NOT NULL,
          parser_version varchar(80) NOT NULL,
          encryption_algorithm varchar(40) NOT NULL,
          encryption_key_id varchar(200) NOT NULL,
          retain_until timestamptz NOT NULL,
          legal_hold boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (tenant_id, evidence_id),
          UNIQUE (tenant_id, object_key)
        )""",
        """CREATE TABLE plotlot.raw_snapshots (
          tenant_id varchar(120) NOT NULL,
          snapshot_id varchar(120) NOT NULL,
          object_key varchar(500) NOT NULL,
          content_sha256 varchar(64) NOT NULL,
          byte_length bigint NOT NULL CHECK (byte_length >= 0),
          source_uri text NOT NULL,
          fetched_at timestamptz NOT NULL,
          encryption_algorithm varchar(40) NOT NULL,
          encryption_key_id varchar(200) NOT NULL,
          retain_until timestamptz NOT NULL,
          legal_hold boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (tenant_id, snapshot_id),
          UNIQUE (tenant_id, object_key)
        )""",
        """CREATE TABLE plotlot.report_records (
          tenant_id varchar(120) NOT NULL,
          report_id varchar(120) NOT NULL,
          host_analysis_id varchar(120) NOT NULL,
          version integer NOT NULL CHECK (version > 0),
          projection jsonb NOT NULL,
          projection_sha256 varchar(64) NOT NULL,
          encryption_algorithm varchar(40) NOT NULL,
          encryption_key_id varchar(200) NOT NULL,
          retain_until timestamptz NOT NULL,
          legal_hold boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (tenant_id, report_id),
          UNIQUE (tenant_id, host_analysis_id, version)
        )""",
        """CREATE TABLE plotlot.approval_records (
          tenant_id varchar(120) NOT NULL,
          approval_id varchar(120) NOT NULL,
          host_analysis_id varchar(120) NOT NULL,
          status varchar(40) NOT NULL,
          decision jsonb NOT NULL,
          decision_sha256 varchar(64) NOT NULL,
          decided_by varchar(120) NOT NULL,
          decided_at timestamptz NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (tenant_id, approval_id)
        )""",
        """CREATE TABLE plotlot.lifecycle_tombstones (
          tenant_id varchar(120) NOT NULL,
          object_key varchar(500) NOT NULL,
          requested_by varchar(120) NOT NULL,
          requested_at timestamptz NOT NULL,
          approved_by varchar(120),
          approved_at timestamptz,
          deletion_due_at timestamptz NOT NULL,
          legal_hold boolean NOT NULL DEFAULT false,
          deleted_at timestamptz,
          PRIMARY KEY (tenant_id, object_key)
        )""",
        """CREATE FUNCTION plotlot.reject_immutable_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'immutable_record';
        END;
        $$""",
        """CREATE TRIGGER immutable_events_guard
          BEFORE UPDATE OR DELETE ON plotlot.immutable_events
          FOR EACH ROW EXECUTE FUNCTION plotlot.reject_immutable_mutation()""",
        """CREATE TRIGGER evidence_records_guard
          BEFORE UPDATE OR DELETE ON plotlot.evidence_records
          FOR EACH ROW EXECUTE FUNCTION plotlot.reject_immutable_mutation()""",
        """CREATE TRIGGER raw_snapshots_guard
          BEFORE UPDATE OR DELETE ON plotlot.raw_snapshots
          FOR EACH ROW EXECUTE FUNCTION plotlot.reject_immutable_mutation()""",
        """CREATE TRIGGER report_records_guard
          BEFORE UPDATE OR DELETE ON plotlot.report_records
          FOR EACH ROW EXECUTE FUNCTION plotlot.reject_immutable_mutation()""",
        """CREATE TRIGGER approval_records_guard
          BEFORE UPDATE OR DELETE ON plotlot.approval_records
          FOR EACH ROW EXECUTE FUNCTION plotlot.reject_immutable_mutation()""",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA plotlot TO plotlot_app",
        "REVOKE UPDATE, DELETE ON plotlot.immutable_events FROM plotlot_app",
        "REVOKE UPDATE, DELETE ON plotlot.evidence_records FROM plotlot_app",
        "REVOKE UPDATE, DELETE ON plotlot.raw_snapshots FROM plotlot_app",
        "REVOKE UPDATE, DELETE ON plotlot.report_records FROM plotlot_app",
        "REVOKE UPDATE, DELETE ON plotlot.approval_records FROM plotlot_app",
        """DO $rls$
        DECLARE table_name text;
        BEGIN
          FOREACH table_name IN ARRAY ARRAY[
            'host_engine_links', 'immutable_events', 'evidence_records',
            'raw_snapshots', 'report_records', 'approval_records', 'lifecycle_tombstones'
          ]
          LOOP
            EXECUTE format('ALTER TABLE plotlot.%I ENABLE ROW LEVEL SECURITY', table_name);
            EXECUTE format('ALTER TABLE plotlot.%I FORCE ROW LEVEL SECURITY', table_name);
            EXECUTE format(
              'CREATE POLICY tenant_isolation ON plotlot.%I
               USING (tenant_id = current_setting(''app.tenant_id'', true))
               WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true))',
              table_name
            );
          END LOOP;
        END
        $rls$""",
        """ALTER DEFAULT PRIVILEGES IN SCHEMA plotlot
          GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO plotlot_app""",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    for statement in (
        "DROP SCHEMA IF EXISTS byright CASCADE",
        "DROP SCHEMA IF EXISTS plotlot CASCADE",
    ):
        op.execute(statement)
