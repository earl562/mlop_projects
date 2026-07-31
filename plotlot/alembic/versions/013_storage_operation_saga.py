"""Add durable cross-system storage operation state.

Revision ID: 013_storage_operation_saga
Revises: 012_storage_runtime_lifecycle
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op


revision: str = "013_storage_operation_saga"
down_revision: Union[str, None] = "012_storage_runtime_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    statements = (
        """CREATE TABLE plotlot.restore_attempts (
          attempt_id uuid PRIMARY KEY,
          stage_bucket varchar(255) NOT NULL UNIQUE,
          stage_database varchar(255) NOT NULL,
          archive_sha256 char(64) NOT NULL,
          state varchar(24) NOT NULL CHECK
            (state IN ('REGISTERED','OBJECTS_RESTORED','RECOVERY_REQUIRED','PROMOTED','CLEANED')),
          cleanup_after timestamptz NOT NULL,
          last_error text,
          updated_at timestamptz NOT NULL DEFAULT now()
        )""",
        """CREATE TABLE plotlot.storage_generation (
          singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
          bucket varchar(255) NOT NULL,
          restore_attempt_id uuid NOT NULL UNIQUE
            REFERENCES plotlot.restore_attempts(attempt_id),
          updated_at timestamptz NOT NULL DEFAULT now()
        )""",
        """CREATE FUNCTION plotlot.guard_storage_generation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM plotlot.restore_attempts attempt
            WHERE attempt.attempt_id=NEW.restore_attempt_id
              AND attempt.state='PROMOTED'
              AND attempt.stage_bucket=NEW.bucket
          ) THEN
            RAISE EXCEPTION 'storage_generation_requires_promoted_attempt';
          END IF;
          RETURN NEW;
        END;
        $$""",
        """CREATE TRIGGER storage_generation_guard
          BEFORE INSERT OR UPDATE ON plotlot.storage_generation
          FOR EACH ROW EXECUTE FUNCTION plotlot.guard_storage_generation()""",
        """CREATE VIEW plotlot.active_storage_generation
          WITH (security_barrier=true) AS
          SELECT generation.bucket
          FROM plotlot.storage_generation generation
          JOIN plotlot.restore_attempts attempt
            ON attempt.attempt_id=generation.restore_attempt_id
           AND attempt.stage_bucket=generation.bucket
          WHERE generation.singleton=true AND attempt.state='PROMOTED'""",
        "REVOKE ALL ON plotlot.active_storage_generation FROM PUBLIC",
        "GRANT SELECT ON plotlot.active_storage_generation TO plotlot_app",
        "GRANT SELECT ON plotlot.storage_generation TO plotlot_app",
        "REVOKE INSERT, UPDATE, DELETE ON plotlot.storage_generation FROM plotlot_app",
        "REVOKE ALL ON plotlot.restore_attempts FROM plotlot_app",
        """ALTER TABLE plotlot.raw_snapshots
          ADD COLUMN lifecycle_state varchar(16) NOT NULL DEFAULT 'ACTIVE'
          CHECK (lifecycle_state IN ('ACTIVE', 'DELETING'))""",
        """CREATE TABLE plotlot.storage_operations (
          tenant_id varchar(120) NOT NULL,
          operation_id varchar(120) NOT NULL,
          operation_type varchar(10) NOT NULL CHECK (operation_type IN ('PUT', 'DELETE')),
          status varchar(24) NOT NULL
            CHECK (status IN ('INTENT', 'OBJECT_WRITTEN', 'FINALIZED')),
          object_key varchar(500) NOT NULL,
          snapshot_id varchar(120) NOT NULL,
          content_sha256 char(64) NOT NULL,
          byte_length bigint NOT NULL CHECK (byte_length >= 0),
          source_uri text NOT NULL,
          fetched_at timestamptz NOT NULL,
          encryption_algorithm varchar(32) NOT NULL,
          encryption_key_id varchar(255) NOT NULL,
          retain_until timestamptz NOT NULL,
          legal_hold boolean NOT NULL DEFAULT false,
          object_version_id varchar(240),
          request_id varchar(120),
          requested_by varchar(120) NOT NULL,
          requested_at timestamptz NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (tenant_id, operation_id),
          CHECK (operation_type <> 'DELETE' OR object_version_id IS NOT NULL),
          CHECK (status <> 'OBJECT_WRITTEN'
            OR (operation_type = 'PUT' AND object_version_id IS NOT NULL)),
          CHECK (status <> 'FINALIZED' OR object_version_id IS NOT NULL)
        )""",
        """CREATE UNIQUE INDEX one_active_storage_operation_per_object
          ON plotlot.storage_operations (tenant_id, object_key)
          WHERE status <> 'FINALIZED'""",
        """CREATE INDEX storage_operations_recovery
          ON plotlot.storage_operations (tenant_id, status, created_at)
          WHERE status <> 'FINALIZED'""",
        """CREATE FUNCTION plotlot.guard_storage_operation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'INSERT' THEN
            IF NEW.status <> 'INTENT'
               OR (NEW.operation_type = 'PUT' AND NEW.object_version_id IS NOT NULL)
               OR (NEW.operation_type = 'DELETE' AND NEW.object_version_id IS NULL) THEN
              RAISE EXCEPTION 'invalid_storage_operation_insert';
            END IF;
            RETURN NEW;
          END IF;
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'immutable_storage_operation';
          END IF;
          IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
             OR NEW.operation_id IS DISTINCT FROM OLD.operation_id
             OR NEW.operation_type IS DISTINCT FROM OLD.operation_type
             OR NEW.object_key IS DISTINCT FROM OLD.object_key
             OR NEW.snapshot_id IS DISTINCT FROM OLD.snapshot_id
             OR NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256
             OR NEW.byte_length IS DISTINCT FROM OLD.byte_length
             OR NEW.source_uri IS DISTINCT FROM OLD.source_uri
             OR NEW.fetched_at IS DISTINCT FROM OLD.fetched_at
             OR NEW.encryption_algorithm IS DISTINCT FROM OLD.encryption_algorithm
             OR NEW.encryption_key_id IS DISTINCT FROM OLD.encryption_key_id
             OR NEW.retain_until IS DISTINCT FROM OLD.retain_until
             OR NEW.legal_hold IS DISTINCT FROM OLD.legal_hold
             OR NEW.request_id IS DISTINCT FROM OLD.request_id
             OR NEW.requested_by IS DISTINCT FROM OLD.requested_by
             OR NEW.requested_at IS DISTINCT FROM OLD.requested_at
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'immutable_storage_operation';
          END IF;
          IF OLD.status = 'FINALIZED' AND (
               current_setting('app.restore_mode', true) IS DISTINCT FROM 'on'
               OR NEW.status IS DISTINCT FROM OLD.status
               OR NEW.object_version_id IS NOT DISTINCT FROM OLD.object_version_id
             ) THEN
            RAISE EXCEPTION 'invalid_storage_operation_transition';
          END IF;
          IF OLD.status <> 'FINALIZED'
             AND NOT (
               NEW.status = OLD.status
               OR (OLD.operation_type='PUT' AND OLD.status='INTENT'
                   AND NEW.status='OBJECT_WRITTEN'
                   AND OLD.object_version_id IS NULL
                   AND NEW.object_version_id IS NOT NULL)
               OR (OLD.operation_type='PUT' AND OLD.status='OBJECT_WRITTEN'
                   AND NEW.status='FINALIZED')
               OR (OLD.operation_type='DELETE' AND OLD.status='INTENT'
                   AND NEW.status='FINALIZED')
             ) THEN
            RAISE EXCEPTION 'invalid_storage_operation_transition';
          END IF;
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$""",
        """INSERT INTO plotlot.storage_operations
          (tenant_id, operation_id, operation_type, status, object_key, snapshot_id,
           content_sha256, byte_length, source_uri, fetched_at, encryption_algorithm,
           encryption_key_id, retain_until, legal_hold, object_version_id,
           requested_by, requested_at)
          SELECT tenant_id, 'legacy-put-' || md5(snapshot_id), 'PUT', 'FINALIZED',
           object_key, snapshot_id, content_sha256, byte_length, source_uri, fetched_at,
           encryption_algorithm, encryption_key_id, retain_until, legal_hold,
           object_version_id, 'migration-013', fetched_at
          FROM plotlot.raw_snapshots WHERE object_version_id IS NOT NULL""",
        """CREATE TRIGGER storage_operations_guard
          BEFORE INSERT OR UPDATE OR DELETE ON plotlot.storage_operations
          FOR EACH ROW EXECUTE FUNCTION plotlot.guard_storage_operation()""",
        "GRANT SELECT, INSERT ON plotlot.storage_operations TO plotlot_app",
        "REVOKE UPDATE, DELETE ON plotlot.storage_operations FROM plotlot_app",
        "REVOKE UPDATE, DELETE ON plotlot.raw_snapshots FROM plotlot_app",
        "REVOKE UPDATE, DELETE ON plotlot.lifecycle_receipts FROM plotlot_app",
        "ALTER TABLE plotlot.storage_operations ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE plotlot.storage_operations FORCE ROW LEVEL SECURITY",
        """CREATE POLICY tenant_isolation ON plotlot.storage_operations
          USING (tenant_id = current_setting('app.tenant_id', true))
          WITH CHECK (tenant_id = current_setting('app.tenant_id', true))""",
        "DROP TRIGGER lifecycle_receipts_guard ON plotlot.lifecycle_receipts",
        """CREATE FUNCTION plotlot.guard_lifecycle_receipt() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'UPDATE'
             AND current_setting('app.restore_mode', true) = 'on'
             AND NEW.tenant_id = OLD.tenant_id
             AND NEW.request_id = OLD.request_id
             AND NEW.object_key = OLD.object_key
             AND NEW.object_version_id IS DISTINCT FROM OLD.object_version_id
             AND NEW.decision = OLD.decision
             AND NEW.reason = OLD.reason
             AND NEW.requested_by = OLD.requested_by
             AND NEW.requested_at = OLD.requested_at
             AND NEW.completed_at = OLD.completed_at THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'immutable_record';
        END;
        $$""",
        """CREATE TRIGGER lifecycle_receipts_guard
          BEFORE UPDATE OR DELETE ON plotlot.lifecycle_receipts
          FOR EACH ROW EXECUTE FUNCTION plotlot.guard_lifecycle_receipt()""",
        "DROP TRIGGER raw_snapshots_guard ON plotlot.raw_snapshots",
        "DROP FUNCTION plotlot.reject_raw_snapshot_mutation()",
        """CREATE FUNCTION plotlot.reject_raw_snapshot_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE'
             AND current_setting('app.lifecycle_delete', true) = 'on' THEN
            RETURN OLD;
          END IF;
          IF TG_OP = 'UPDATE'
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
             AND NEW.created_at = OLD.created_at
             AND ((current_setting('app.restore_mode', true) = 'on'
                   AND NEW.lifecycle_state = OLD.lifecycle_state)
               OR (current_setting('app.lifecycle_delete', true) = 'on'
                   AND OLD.lifecycle_state = 'ACTIVE' AND NEW.lifecycle_state = 'DELETING'
                   AND NEW.object_version_id = OLD.object_version_id)
               OR (current_setting('app.lifecycle_cancel', true) = 'on'
                   AND OLD.lifecycle_state = 'DELETING' AND NEW.lifecycle_state = 'ACTIVE'
                   AND NEW.object_version_id = OLD.object_version_id)) THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'immutable_record';
        END;
        $$""",
        """CREATE TRIGGER raw_snapshots_guard
          BEFORE UPDATE OR DELETE ON plotlot.raw_snapshots
          FOR EACH ROW EXECUTE FUNCTION plotlot.reject_raw_snapshot_mutation()""",
        "DROP FUNCTION plotlot.delete_expired_snapshot",
        _mark_deleting_function(),
        _cancel_deleting_function(),
        _delete_snapshot_function(),
        _record_version_function(),
        _finalize_operation_function(),
        "REVOKE ALL ON FUNCTION plotlot.mark_snapshot_deleting FROM PUBLIC",
        "REVOKE ALL ON FUNCTION plotlot.cancel_snapshot_deleting FROM PUBLIC",
        "REVOKE ALL ON FUNCTION plotlot.delete_expired_snapshot FROM PUBLIC",
        "REVOKE ALL ON FUNCTION plotlot.record_storage_version FROM PUBLIC",
        "REVOKE ALL ON FUNCTION plotlot.finalize_storage_operation FROM PUBLIC",
        "GRANT EXECUTE ON FUNCTION plotlot.mark_snapshot_deleting TO plotlot_app",
        "GRANT EXECUTE ON FUNCTION plotlot.cancel_snapshot_deleting TO plotlot_app",
        "GRANT EXECUTE ON FUNCTION plotlot.delete_expired_snapshot TO plotlot_app",
        "GRANT EXECUTE ON FUNCTION plotlot.record_storage_version TO plotlot_app",
        "GRANT EXECUTE ON FUNCTION plotlot.finalize_storage_operation TO plotlot_app",
    )
    for statement in statements:
        op.execute(statement)


def _mark_deleting_function() -> str:
    return """CREATE FUNCTION plotlot.mark_snapshot_deleting(
      requested_tenant_id varchar, requested_object_key varchar,
      requested_version_id varchar, requested_operation_id varchar
    ) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
    SET search_path = pg_catalog, plotlot AS $$
    DECLARE changed integer;
    BEGIN
      IF current_setting('app.tenant_id', true) IS DISTINCT FROM requested_tenant_id
         OR NOT EXISTS (
           SELECT 1 FROM plotlot.storage_operations
           WHERE tenant_id=requested_tenant_id AND operation_id=requested_operation_id
             AND operation_type='DELETE' AND status='INTENT'
             AND object_key=requested_object_key
             AND object_version_id=requested_version_id
         ) THEN RAISE insufficient_privilege; END IF;
      PERFORM set_config('app.lifecycle_delete', 'on', true);
      UPDATE plotlot.raw_snapshots SET lifecycle_state='DELETING'
      WHERE tenant_id=requested_tenant_id AND object_key=requested_object_key
        AND object_version_id=requested_version_id AND lifecycle_state='ACTIVE';
      GET DIAGNOSTICS changed = ROW_COUNT;
      RETURN changed = 1;
    END;
    $$"""


def _cancel_deleting_function() -> str:
    return """CREATE FUNCTION plotlot.cancel_snapshot_deleting(
      requested_tenant_id varchar, requested_object_key varchar,
      requested_version_id varchar, requested_operation_id varchar
    ) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
    SET search_path = pg_catalog, plotlot AS $$
    DECLARE changed integer;
    BEGIN
      IF current_setting('app.tenant_id', true) IS DISTINCT FROM requested_tenant_id
         OR NOT EXISTS (
           SELECT 1 FROM plotlot.storage_operations
           WHERE tenant_id=requested_tenant_id AND operation_id=requested_operation_id
             AND operation_type='DELETE' AND status='INTENT'
             AND object_key=requested_object_key
             AND object_version_id=requested_version_id
         ) THEN RAISE insufficient_privilege; END IF;
      PERFORM set_config('app.lifecycle_cancel', 'on', true);
      UPDATE plotlot.raw_snapshots SET lifecycle_state='ACTIVE'
      WHERE tenant_id=requested_tenant_id AND object_key=requested_object_key
        AND object_version_id=requested_version_id AND lifecycle_state='DELETING';
      GET DIAGNOSTICS changed = ROW_COUNT;
      RETURN changed = 1;
    END;
    $$"""


def _delete_snapshot_function() -> str:
    return """CREATE FUNCTION plotlot.delete_expired_snapshot(
      requested_tenant_id varchar, requested_object_key varchar,
      requested_version_id varchar, requested_operation_id varchar,
      requested_at timestamptz
    ) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
    SET search_path = pg_catalog, plotlot AS $$
    DECLARE deleted_count integer;
    BEGIN
      IF current_setting('app.tenant_id', true) IS DISTINCT FROM requested_tenant_id
         OR NOT EXISTS (
           SELECT 1 FROM plotlot.storage_operations
           WHERE tenant_id=requested_tenant_id AND operation_id=requested_operation_id
             AND operation_type='DELETE' AND status='INTENT'
             AND object_key=requested_object_key
             AND object_version_id=requested_version_id
         ) THEN RAISE insufficient_privilege; END IF;
      PERFORM set_config('app.lifecycle_delete', 'on', true);
      DELETE FROM plotlot.raw_snapshots
      WHERE tenant_id=requested_tenant_id AND object_key=requested_object_key
        AND object_version_id=requested_version_id AND lifecycle_state='DELETING'
        AND legal_hold=false AND retain_until <= requested_at;
      GET DIAGNOSTICS deleted_count = ROW_COUNT;
      RETURN deleted_count = 1;
    END;
    $$"""


def _record_version_function() -> str:
    return """CREATE FUNCTION plotlot.record_storage_version(
      requested_tenant_id varchar, requested_operation_id varchar,
      requested_version_id varchar
    ) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
    SET search_path = pg_catalog, plotlot AS $$
    DECLARE changed integer;
    BEGIN
      IF current_setting('app.tenant_id', true) IS DISTINCT FROM requested_tenant_id
      THEN RAISE insufficient_privilege; END IF;
      UPDATE plotlot.storage_operations
      SET object_version_id=COALESCE(object_version_id, requested_version_id),
          status='OBJECT_WRITTEN'
      WHERE tenant_id=requested_tenant_id AND operation_id=requested_operation_id
        AND operation_type='PUT' AND status IN ('INTENT', 'OBJECT_WRITTEN')
        AND (object_version_id IS NULL OR object_version_id=requested_version_id);
      GET DIAGNOSTICS changed = ROW_COUNT;
      RETURN changed = 1;
    END;
    $$"""


def _finalize_operation_function() -> str:
    return """CREATE FUNCTION plotlot.finalize_storage_operation(
      requested_tenant_id varchar, requested_operation_id varchar
    ) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
    SET search_path = pg_catalog, plotlot AS $$
    DECLARE changed integer;
    BEGIN
      IF current_setting('app.tenant_id', true) IS DISTINCT FROM requested_tenant_id
      THEN RAISE insufficient_privilege; END IF;
      UPDATE plotlot.storage_operations operation SET status='FINALIZED'
      WHERE operation.tenant_id=requested_tenant_id
        AND operation.operation_id=requested_operation_id
        AND (
          (operation.operation_type='PUT' AND operation.status='OBJECT_WRITTEN'
           AND EXISTS (
             SELECT 1 FROM plotlot.raw_snapshots snapshot
             WHERE snapshot.tenant_id=operation.tenant_id
               AND snapshot.object_key=operation.object_key
               AND snapshot.object_version_id=operation.object_version_id
               AND snapshot.lifecycle_state='ACTIVE'
           ))
          OR
          (operation.operation_type='DELETE' AND operation.status='INTENT'
           AND EXISTS (
             SELECT 1 FROM plotlot.lifecycle_receipts receipt
             WHERE receipt.tenant_id=operation.tenant_id
               AND receipt.request_id=operation.request_id
               AND receipt.object_key=operation.object_key
               AND receipt.object_version_id=operation.object_version_id
               AND (
                 (receipt.decision='delete' AND NOT EXISTS (
                   SELECT 1 FROM plotlot.raw_snapshots snapshot
                   WHERE snapshot.tenant_id=operation.tenant_id
                     AND snapshot.object_key=operation.object_key
                 ))
                 OR
                 (receipt.decision='hold' AND EXISTS (
                   SELECT 1 FROM plotlot.raw_snapshots snapshot
                   WHERE snapshot.tenant_id=operation.tenant_id
                     AND snapshot.object_key=operation.object_key
                     AND snapshot.object_version_id=operation.object_version_id
                     AND snapshot.lifecycle_state='ACTIVE'
                 ))
               )
           ))
        );
      GET DIAGNOSTICS changed = ROW_COUNT;
      RETURN changed = 1;
    END;
    $$"""


def downgrade() -> None:
    for statement in (
        """DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM plotlot.storage_operations WHERE status <> 'FINALIZED'
          ) OR EXISTS (
            SELECT 1 FROM plotlot.raw_snapshots WHERE lifecycle_state='DELETING'
          ) THEN RAISE EXCEPTION 'pending_storage_operations_block_downgrade'; END IF;
        END $$""",
        "DROP FUNCTION IF EXISTS plotlot.finalize_storage_operation",
        "DROP FUNCTION IF EXISTS plotlot.record_storage_version",
        "DROP FUNCTION plotlot.delete_expired_snapshot",
        "DROP FUNCTION plotlot.cancel_snapshot_deleting",
        "DROP FUNCTION plotlot.mark_snapshot_deleting",
        "DROP TRIGGER raw_snapshots_guard ON plotlot.raw_snapshots",
        "DROP FUNCTION plotlot.reject_raw_snapshot_mutation()",
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
        """CREATE TRIGGER raw_snapshots_guard BEFORE UPDATE OR DELETE
          ON plotlot.raw_snapshots FOR EACH ROW
          EXECUTE FUNCTION plotlot.reject_raw_snapshot_mutation()""",
        "DROP TRIGGER lifecycle_receipts_guard ON plotlot.lifecycle_receipts",
        "DROP FUNCTION IF EXISTS plotlot.guard_lifecycle_receipt()",
        """CREATE TRIGGER lifecycle_receipts_guard
          BEFORE UPDATE OR DELETE ON plotlot.lifecycle_receipts
          FOR EACH ROW EXECUTE FUNCTION plotlot.reject_immutable_mutation()""",
        "DROP TABLE plotlot.storage_operations",
        "DROP VIEW IF EXISTS plotlot.active_storage_generation",
        "DROP TRIGGER IF EXISTS storage_generation_guard ON plotlot.storage_generation",
        "DROP FUNCTION IF EXISTS plotlot.guard_storage_generation()",
        "DROP TABLE IF EXISTS plotlot.storage_generation",
        "DROP TABLE IF EXISTS plotlot.restore_attempts",
        "DROP FUNCTION plotlot.guard_storage_operation()",
        "ALTER TABLE plotlot.raw_snapshots DROP COLUMN lifecycle_state",
        """CREATE FUNCTION plotlot.delete_expired_snapshot(
          requested_tenant_id varchar, requested_object_key varchar,
          requested_version_id varchar, requested_at timestamptz
        ) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, plotlot AS $$
        DECLARE deleted_count integer; BEGIN
          IF current_setting('app.tenant_id', true)
             IS DISTINCT FROM requested_tenant_id THEN RAISE insufficient_privilege; END IF;
          PERFORM set_config('app.lifecycle_delete', 'on', true);
          DELETE FROM plotlot.raw_snapshots
          WHERE tenant_id=requested_tenant_id AND object_key=requested_object_key
            AND object_version_id=requested_version_id
            AND legal_hold=false AND retain_until <= requested_at;
          GET DIAGNOSTICS deleted_count = ROW_COUNT;
          RETURN deleted_count = 1;
        END; $$""",
        "REVOKE ALL ON FUNCTION plotlot.delete_expired_snapshot FROM PUBLIC",
        "GRANT EXECUTE ON FUNCTION plotlot.delete_expired_snapshot TO plotlot_app",
    ):
        op.execute(statement)
