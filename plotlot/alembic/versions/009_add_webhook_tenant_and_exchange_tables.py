"""Add webhook_tenant and webhook_exchange tables (Phase 5 webhook harness).

Revision ID: 009
Revises: d3e4f5a6b7c8
Create Date: 2026-06-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_tenants",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("shared_secret_enc", sa.Text(), nullable=False),
        sa.Column("callback_url", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_tenants_tenant_id", "webhook_tenants", ["tenant_id"], unique=True
    )

    op.create_table(
        "webhook_exchanges",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("analysis_run_id", sa.String(36), nullable=False),
        sa.Column("inbound_webhook_id", sa.String(100), nullable=True),
        sa.Column("outbound_webhook_id", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["webhook_tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_exchanges_tenant_id", "webhook_exchanges", ["tenant_id"])
    op.create_index(
        "ix_webhook_exchanges_analysis_run_id",
        "webhook_exchanges",
        ["analysis_run_id"],
    )
    op.create_index(
        "ix_webhook_exchanges_status", "webhook_exchanges", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_exchanges_status", table_name="webhook_exchanges")
    op.drop_index("ix_webhook_exchanges_analysis_run_id", table_name="webhook_exchanges")
    op.drop_index("ix_webhook_exchanges_tenant_id", table_name="webhook_exchanges")
    op.drop_table("webhook_exchanges")

    op.drop_index("ix_webhook_tenants_tenant_id", table_name="webhook_tenants")
    op.drop_table("webhook_tenants")
