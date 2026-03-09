"""add report_cache table for LLM cost savings

Revision ID: 003
Revises: 002
Create Date: 2026-03-09

Caches full ZoningReportResponse JSON per normalized address with a TTL.
Avoids redundant LLM pipeline runs for repeated queries on the same address.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("address", sa.String(), nullable=False, index=True),
        sa.Column("address_normalized", sa.String(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hit_count", sa.Integer(), server_default=sa.text("0")),
    )
    op.create_index(
        "ix_report_cache_address_normalized",
        "report_cache",
        ["address_normalized"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_report_cache_address_normalized", table_name="report_cache")
    op.drop_table("report_cache")
