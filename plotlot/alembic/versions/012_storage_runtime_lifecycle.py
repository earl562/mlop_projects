"""Add object versions and immutable lifecycle execution receipts.

Revision ID: 012_storage_runtime_lifecycle
Revises: 011_durable_tenant_storage
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op


revision: str = "012_storage_runtime_lifecycle"
down_revision: Union[str, None] = "011_durable_tenant_storage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    statements = (
        "ALTER TABLE plotlot.raw_snapshots ADD COLUMN object_version_id varchar(240)",
        """CREATE TABLE plotlot.lifecycle_receipts (
          tenant_id varchar(120) NOT NULL,
          request_id varchar(120) NOT NULL,
          object_key varchar(500) NOT NULL,
          object_version_id varchar(240),
          decision varchar(20) NOT NULL
            CHECK (decision IN ('keep', 'delete', 'hold', 'deny')),
          reason varchar(120) NOT NULL,
          requested_by varchar(120) NOT NULL,
          requested_at timestamptz NOT NULL,
          completed_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (tenant_id, request_id)
        )""",
        """CREATE TRIGGER lifecycle_receipts_guard
          BEFORE UPDATE OR DELETE ON plotlot.lifecycle_receipts
          FOR EACH ROW EXECUTE FUNCTION plotlot.reject_immutable_mutation()""",
        "GRANT SELECT, INSERT ON plotlot.lifecycle_receipts TO plotlot_app",
        "ALTER TABLE plotlot.lifecycle_receipts ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE plotlot.lifecycle_receipts FORCE ROW LEVEL SECURITY",
        """CREATE POLICY tenant_isolation ON plotlot.lifecycle_receipts
          USING (tenant_id = current_setting('app.tenant_id', true))
          WITH CHECK (tenant_id = current_setting('app.tenant_id', true))""",
        "DROP TRIGGER raw_snapshots_guard ON plotlot.raw_snapshots",
        """CREATE FUNCTION plotlot.reject_raw_snapshot_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE'
             AND current_setting('app.lifecycle_delete', true) = 'on' THEN
            RETURN OLD;
          END IF;
          IF TG_OP = 'UPDATE'
             AND current_setting('app.restore_mode', true) = 'on'
             AND NEW.tenant_id = OLD.tenant_id
             AND NEW.snapshot_id = OLD.snapshot_id
             AND NEW.object_key = OLD.object_key
             AND NEW.content_sha256 = OLD.content_sha256
             AND NEW.byte_length = OLD.byte_length
             AND NEW.source_uri = OLD.source_uri
             AND NEW.fetched_at = OLD.fetched_at
             AND NEW.encryption_algorithm = OLD.encryption_algorithm
             AND NEW.encryption_key_id = OLD.encryption_key_id
             AND NEW.retain_until = OLD.retain_until
             AND NEW.legal_hold = OLD.legal_hold
             AND NEW.created_at = OLD.created_at THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'immutable_record';
        END;
        $$""",
        """CREATE TRIGGER raw_snapshots_guard
          BEFORE UPDATE OR DELETE ON plotlot.raw_snapshots
          FOR EACH ROW EXECUTE FUNCTION plotlot.reject_raw_snapshot_mutation()""",
        """CREATE FUNCTION plotlot.delete_expired_snapshot(
          requested_tenant_id varchar,
          requested_object_key varchar,
          requested_version_id varchar,
          requested_at timestamptz
        ) RETURNS boolean
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, plotlot
        AS $$
        DECLARE deleted_count integer;
        BEGIN
          IF current_setting('app.tenant_id', true) IS DISTINCT FROM requested_tenant_id THEN
            RAISE insufficient_privilege;
          END IF;
          PERFORM set_config('app.lifecycle_delete', 'on', true);
          DELETE FROM plotlot.raw_snapshots
          WHERE tenant_id = requested_tenant_id
            AND object_key = requested_object_key
            AND object_version_id = requested_version_id
            AND legal_hold = false
            AND retain_until <= requested_at;
          GET DIAGNOSTICS deleted_count = ROW_COUNT;
          RETURN deleted_count = 1;
        END;
        $$""",
        "REVOKE ALL ON FUNCTION plotlot.delete_expired_snapshot FROM PUBLIC",
        """GRANT EXECUTE ON FUNCTION plotlot.delete_expired_snapshot
          TO plotlot_app""",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    statements = (
        "DROP FUNCTION plotlot.delete_expired_snapshot",
        "DROP TRIGGER raw_snapshots_guard ON plotlot.raw_snapshots",
        "DROP FUNCTION plotlot.reject_raw_snapshot_mutation()",
        """CREATE TRIGGER raw_snapshots_guard
          BEFORE UPDATE OR DELETE ON plotlot.raw_snapshots
          FOR EACH ROW EXECUTE FUNCTION plotlot.reject_immutable_mutation()""",
        "DROP TABLE plotlot.lifecycle_receipts",
        "ALTER TABLE plotlot.raw_snapshots DROP COLUMN object_version_id",
    )
    for statement in statements:
        op.execute(statement)
