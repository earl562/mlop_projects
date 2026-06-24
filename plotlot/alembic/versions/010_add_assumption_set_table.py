"""Add assumption_sets table for versioned underwriting assumptions.

Revision ID: 010
Revises: 009
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[Sequence[str], str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assumption_sets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("inputs_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("labels_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("supersedes_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"]),
        sa.ForeignKeyConstraint(["supersedes_id"], ["assumption_sets.id"]),
    )
    op.create_index(op.f("ix_assumption_sets_workspace_id"), "assumption_sets", ["workspace_id"])
    op.create_index(op.f("ix_assumption_sets_analysis_id"), "assumption_sets", ["analysis_id"])
    op.create_index(op.f("ix_assumption_sets_supersedes_id"), "assumption_sets", ["supersedes_id"])


def downgrade() -> None:
    op.drop_table("assumption_sets")
