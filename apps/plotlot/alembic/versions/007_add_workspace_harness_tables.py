"""Add workspace harness tables.

Revision ID: 007
Revises: 006
Create Date: 2026-05-02

Adds the first durable harness objects: workspaces, projects, sites,
analysis runs, evidence items, reports, and approval requests. These tables
are intentionally additive so the existing lookup/chat/report contracts keep
working while the workspace-native harness is introduced.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspaces_slug", "workspaces", ["slug"], unique=True)

    op.create_table(
        "workspace_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="owner"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member_user"),
    )
    op.create_index("ix_workspace_members_workspace_id", "workspace_members", ["workspace_id"])
    op.create_index("ix_workspace_members_user_id", "workspace_members", ["user_id"])

    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("project_type", sa.String(length=64), nullable=False, server_default="zoning_research"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("criteria_json", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])

    op.create_table(
        "sites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("parcel_id", sa.String(length=128), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("site_type", sa.String(length=64), nullable=False, server_default="candidate"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sites_project_id", "sites", ["project_id"])
    op.create_index("ix_sites_parcel_id", "sites", ["parcel_id"])

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("skill_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("input_json", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("output_json", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_runs_workspace_id", "analysis_runs", ["workspace_id"])
    op.create_index("ix_analysis_runs_project_id", "analysis_runs", ["project_id"])
    op.create_index("ix_analysis_runs_site_id", "analysis_runs", ["site_id"])

    op.create_table(
        "evidence_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("analysis_run_id", sa.String(length=36), nullable=True),
        sa.Column("claim_key", sa.String(length=128), nullable=False),
        sa.Column("value_json", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_title", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_items_workspace_id", "evidence_items", ["workspace_id"])
    op.create_index("ix_evidence_items_project_id", "evidence_items", ["project_id"])
    op.create_index("ix_evidence_items_site_id", "evidence_items", ["site_id"])
    op.create_index("ix_evidence_items_analysis_run_id", "evidence_items", ["analysis_run_id"])
    op.create_index("ix_evidence_items_claim_key", "evidence_items", ["claim_key"])

    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content_json", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reports_workspace_id", "reports", ["workspace_id"])
    op.create_index("ix_reports_project_id", "reports", ["project_id"])
    op.create_index("ix_reports_site_id", "reports", ["site_id"])

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("request_json", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_requests_workspace_id", "approval_requests", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_approval_requests_workspace_id", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index("ix_reports_site_id", table_name="reports")
    op.drop_index("ix_reports_project_id", table_name="reports")
    op.drop_index("ix_reports_workspace_id", table_name="reports")
    op.drop_table("reports")
    op.drop_index("ix_evidence_items_claim_key", table_name="evidence_items")
    op.drop_index("ix_evidence_items_analysis_run_id", table_name="evidence_items")
    op.drop_index("ix_evidence_items_site_id", table_name="evidence_items")
    op.drop_index("ix_evidence_items_project_id", table_name="evidence_items")
    op.drop_index("ix_evidence_items_workspace_id", table_name="evidence_items")
    op.drop_table("evidence_items")
    op.drop_index("ix_analysis_runs_site_id", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_project_id", table_name="analysis_runs")
    op.drop_index("ix_analysis_runs_workspace_id", table_name="analysis_runs")
    op.drop_table("analysis_runs")
    op.drop_index("ix_sites_parcel_id", table_name="sites")
    op.drop_index("ix_sites_project_id", table_name="sites")
    op.drop_table("sites")
    op.drop_index("ix_projects_workspace_id", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_workspace_members_user_id", table_name="workspace_members")
    op.drop_index("ix_workspace_members_workspace_id", table_name="workspace_members")
    op.drop_table("workspace_members")
    op.drop_index("ix_workspaces_slug", table_name="workspaces")
    op.drop_table("workspaces")
