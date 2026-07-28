"""Enforce tenant authorization across application-owned records.

Revision ID: 014_tenant_authorization_rls
Revises: 013_storage_operation_saga
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op


revision: str = "014_tenant_authorization_rls"
down_revision: Union[str, None] = "013_storage_operation_saga"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WORKSPACE_TABLES = (
    "workspace_members",
    "service_principals",
    "projects",
    "project_branches",
    "sites",
    "analyses",
    "analysis_runs",
    "evidence_items",
    "tool_runs",
    "model_runs",
    "approval_requests",
    "reports",
    "documents",
    "connector_accounts",
    "connector_datasets",
    "connector_sync_runs",
    "portfolio_entries",
    "report_cache",
    "connector_credentials",
)


def _enable_workspace_rls(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""CREATE POLICY tenant_isolation ON {table_name}
        USING (workspace_id = current_setting('app.tenant_id', true))
        WITH CHECK (workspace_id = current_setting('app.tenant_id', true))"""
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table_name} TO plotlot_app"
    )


def upgrade() -> None:
    op.execute("ALTER ROLE plotlot_app NOBYPASSRLS NOSUPERUSER")
    op.execute(
        """CREATE TABLE IF NOT EXISTS service_principals (
        id varchar(120) PRIMARY KEY,
        workspace_id varchar(36) NOT NULL REFERENCES workspaces(id),
        name varchar(200) NOT NULL,
        allowed_actions varchar[] NOT NULL DEFAULT '{}',
        expires_at timestamptz NOT NULL,
        revoked_at timestamptz,
        created_by_user_id varchar NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
        )"""
    )
    for table_name in ("portfolio_entries", "report_cache", "connector_credentials"):
        op.execute(
            f"ALTER TABLE {table_name} ADD COLUMN workspace_id varchar(36)"
        )

    op.execute("ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workspaces FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY tenant_isolation ON workspaces
        USING (id = current_setting('app.tenant_id', true))
        WITH CHECK (id = current_setting('app.tenant_id', true))"""
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON workspaces TO plotlot_app"
    )
    for table_name in _WORKSPACE_TABLES:
        _enable_workspace_rls(table_name)

    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO plotlot_app")
    op.execute(
        "ALTER TABLE report_cache DROP CONSTRAINT IF EXISTS uq_report_cache_key"
    )
    op.execute(
        """ALTER TABLE report_cache
        ADD CONSTRAINT uq_report_cache_tenant_key
        UNIQUE (workspace_id, address_normalized, analysis_type)"""
    )
    op.execute(
        """ALTER TABLE connector_credentials
        DROP CONSTRAINT IF EXISTS connector_credentials_session_id_key"""
    )
    op.execute(
        """ALTER TABLE connector_credentials
        ADD CONSTRAINT uq_connector_credentials_tenant_session
        UNIQUE (workspace_id, session_id)"""
    )
    op.execute(
        """CREATE TABLE plotlot.analysis_revision_heads (
        tenant_id varchar(120) NOT NULL,
        analysis_id varchar(120) NOT NULL,
        revision_id varchar(120) NOT NULL,
        revision_sha256 char(64) NOT NULL,
        is_clean boolean NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, analysis_id),
        UNIQUE (tenant_id, revision_id, revision_sha256)
        )"""
    )
    op.execute(
        """CREATE TABLE plotlot.external_release_requests (
        tenant_id varchar(120) NOT NULL,
        request_id uuid NOT NULL,
        analysis_id varchar(120) NOT NULL,
        revision_id varchar(120) NOT NULL,
        revision_sha256 char(64) NOT NULL,
        requested_by varchar(120) NOT NULL,
        reviewed_by varchar(120),
        status varchar(20) NOT NULL CHECK (status IN ('pending', 'released')),
        released_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (tenant_id, request_id),
        UNIQUE (tenant_id, revision_id)
        )"""
    )
    for table_name in ("analysis_revision_heads", "external_release_requests"):
        op.execute(f"ALTER TABLE plotlot.{table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE plotlot.{table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""CREATE POLICY tenant_isolation ON plotlot.{table_name}
            USING (tenant_id = current_setting('app.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('app.tenant_id', true))"""
        )
        op.execute(
            f"""GRANT SELECT, INSERT, UPDATE
            ON plotlot.{table_name} TO plotlot_app"""
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plotlot.external_release_requests")
    op.execute("DROP TABLE IF EXISTS plotlot.analysis_revision_heads")
    for table_name in _WORKSPACE_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table_name}")
        op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON workspaces")
    op.execute("ALTER TABLE workspaces DISABLE ROW LEVEL SECURITY")
    op.execute(
        """ALTER TABLE connector_credentials
        DROP CONSTRAINT IF EXISTS uq_connector_credentials_tenant_session"""
    )
    op.execute(
        """ALTER TABLE connector_credentials
        ADD CONSTRAINT connector_credentials_session_id_key UNIQUE (session_id)"""
    )
    op.execute(
        "ALTER TABLE report_cache DROP CONSTRAINT IF EXISTS uq_report_cache_tenant_key"
    )
    op.execute(
        """ALTER TABLE report_cache
        ADD CONSTRAINT uq_report_cache_key
        UNIQUE (address_normalized, analysis_type)"""
    )
    for table_name in ("portfolio_entries", "report_cache", "connector_credentials"):
        op.execute(f"ALTER TABLE {table_name} DROP COLUMN workspace_id")
    op.execute("DROP TABLE IF EXISTS service_principals")
