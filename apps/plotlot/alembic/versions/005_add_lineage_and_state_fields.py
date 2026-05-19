"""Add lineage fields (source_url, scraped_at, embedding_model) and state to ordinance_chunks.

Revision ID: 005
Revises: 004
Create Date: 2026-03-09

B2: Lineage fields enable provenance tracking — every chunk records where it
    was scraped from, when, and which embedding model encoded it.
B6: State field supports multi-state expansion (FL + NC today, more later).
    Existing rows default to 'FL' via server_default.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # B2: Lineage fields
    op.add_column(
        "ordinance_chunks",
        sa.Column("source_url", sa.String(), nullable=True),
    )
    op.add_column(
        "ordinance_chunks",
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ordinance_chunks",
        sa.Column("embedding_model", sa.String(), nullable=True),
    )

    # B6: State field — default 'FL' for existing rows
    op.add_column(
        "ordinance_chunks",
        sa.Column("state", sa.String(2), nullable=True, server_default="FL"),
    )


def downgrade() -> None:
    op.drop_column("ordinance_chunks", "state")
    op.drop_column("ordinance_chunks", "embedding_model")
    op.drop_column("ordinance_chunks", "scraped_at")
    op.drop_column("ordinance_chunks", "source_url")
