"""add portfolio_entries table

Revision ID: 004
Revises: 002
Create Date: 2026-03-09

Persists saved zoning analyses in PostgreSQL instead of an in-memory dict.
The user_id column is nullable — once Supabase auth is wired in, it will
enable per-user portfolio filtering.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=False),
        sa.Column("municipality", sa.String(), nullable=False),
        sa.Column("county", sa.String(), nullable=False),
        sa.Column("zoning_district", sa.String(), nullable=True),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_portfolio_entries_user_id"),
        "portfolio_entries",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_portfolio_entries_user_id"), table_name="portfolio_entries")
    op.drop_table("portfolio_entries")
