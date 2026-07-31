"""Add harness artifact, connector, and eval tables.

Revision ID: 008
Revises: 007
Create Date: 2026-04-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "008_harness_artifacts"
down_revision: Union[str, None] = "007_harness_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("analysis_run_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
        sa.Column("report_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("evidence_ids", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("workspace_id", "project_id", "site_id", "analysis_run_id", "status"):
        op.create_index(op.f(f"ix_reports_{column}"), "reports", [column])

    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("report_id", sa.String(length=36), nullable=True),
        sa.Column("document_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
        sa.Column("storage_url", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("workspace_id", "project_id", "site_id", "report_id", "document_type", "status"):
        op.create_index(op.f(f"ix_documents_{column}"), "documents", [column])

    op.create_table(
        "connector_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("auth_type", sa.String(length=40), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="connected"),
        sa.Column("encrypted_credentials_ref", sa.String(), nullable=True),
        sa.Column("created_by_user_id", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("workspace_id", "provider", "status", "created_by_user_id"):
        op.create_index(op.f(f"ix_connector_accounts_{column}"), "connector_accounts", [column])

    op.create_table(
        "connector_datasets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("jurisdiction", sa.String(length=200), nullable=True),
        sa.Column("topic", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("endpoint_url", sa.String(), nullable=False),
        sa.Column("metadata_url", sa.String(), nullable=True),
        sa.Column("license_url", sa.String(), nullable=True),
        sa.Column("official_status", sa.String(length=40), nullable=False, server_default="unknown"),
        sa.Column("freshness_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("schema_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("workspace_id", "provider", "jurisdiction", "topic", "official_status"):
        op.create_index(op.f(f"ix_connector_datasets_{column}"), "connector_datasets", [column])

    op.create_table(
        "connector_sync_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("connector_account_id", sa.String(length=36), nullable=True),
        sa.Column("connector_dataset_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("counts_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["connector_account_id"], ["connector_accounts.id"]),
        sa.ForeignKeyConstraint(["connector_dataset_id"], ["connector_datasets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("workspace_id", "connector_account_id", "connector_dataset_id", "status"):
        op.create_index(op.f(f"ix_connector_sync_runs_{column}"), "connector_sync_runs", [column])

    op.create_table(
        "gold_set_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("suite", sa.String(length=120), nullable=False),
        sa.Column("case_id", sa.String(length=160), nullable=False),
        sa.Column("jurisdiction", sa.String(length=200), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=True),
        sa.Column("expected_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("source_urls", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id"),
    )
    for column in ("suite", "jurisdiction"):
        op.create_index(op.f(f"ix_gold_set_cases_{column}"), "gold_set_cases", [column])

    op.create_table(
        "eval_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("suite", sa.String(length=120), nullable=False),
        sa.Column("git_sha", sa.String(length=80), nullable=True),
        sa.Column("model_profile", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("suite", "git_sha", "status"):
        op.create_index(op.f(f"ix_eval_runs_{column}"), "eval_runs", [column])

    op.create_table(
        "eval_case_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("eval_run_id", sa.String(length=36), nullable=False),
        sa.Column("gold_set_case_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("diffs_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("evidence_metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("trajectory_metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["eval_run_id"], ["eval_runs.id"]),
        sa.ForeignKeyConstraint(["gold_set_case_id"], ["gold_set_cases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("eval_run_id", "gold_set_case_id", "status"):
        op.create_index(op.f(f"ix_eval_case_results_{column}"), "eval_case_results", [column])


def downgrade() -> None:
    op.drop_table("eval_case_results")
    op.drop_table("eval_runs")
    op.drop_table("gold_set_cases")
    op.drop_table("connector_sync_runs")
    op.drop_table("connector_datasets")
    op.drop_table("connector_accounts")
    op.drop_table("documents")
    op.drop_table("reports")
