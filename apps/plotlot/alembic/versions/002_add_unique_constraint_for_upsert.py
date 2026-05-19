"""add unique constraint for idempotent upsert ingestion

Revision ID: 002
Revises: 001
Create Date: 2026-03-09

Adds a unique constraint on (municipality, municode_node_id, chunk_index)
so that re-ingesting a municipality performs ON CONFLICT UPDATE instead of
creating duplicate rows. Also adds an updated_at column to track when
chunks were last refreshed.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add updated_at column (nullable so existing rows stay valid)
    op.add_column(
        "ordinance_chunks",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )

    # Deduplicate existing rows before adding the unique constraint.
    # Keep the row with the highest id (most recent insert) for each
    # (municipality, municode_node_id, chunk_index) triple.
    op.execute("""
        DELETE FROM ordinance_chunks
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM ordinance_chunks
            GROUP BY municipality, municode_node_id, chunk_index
        )
    """)

    # Now safe to add the unique constraint
    op.create_unique_constraint(
        "uq_chunk_natural_key",
        "ordinance_chunks",
        ["municipality", "municode_node_id", "chunk_index"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_chunk_natural_key", "ordinance_chunks", type_="unique")
    op.drop_column("ordinance_chunks", "updated_at")
