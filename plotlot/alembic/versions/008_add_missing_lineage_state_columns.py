"""Add missing lineage and state columns to ordinance_chunks.

Revision ID: 008
Revises: 007
Create Date: 2026-05-14

Migration 005 was defined but skipped in the applied revision chain due to
a merge-head branch anomaly (88d5f65b958d). The ordinance_chunks table is
missing source_url, scraped_at, embedding_model, and state columns.

Using raw SQL with ADD COLUMN IF NOT EXISTS (PostgreSQL 9.6+) so this
migration is safe to re-run even if some columns were partially applied.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "008_lineage_backfill"
down_revision: Union[str, None] = "008_harness_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ordinance_chunks ADD COLUMN IF NOT EXISTS source_url VARCHAR"
    )
    op.execute(
        "ALTER TABLE ordinance_chunks ADD COLUMN IF NOT EXISTS "
        "scraped_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "ALTER TABLE ordinance_chunks ADD COLUMN IF NOT EXISTS embedding_model VARCHAR"
    )
    op.execute(
        "ALTER TABLE ordinance_chunks ADD COLUMN IF NOT EXISTS state VARCHAR(2) DEFAULT 'FL'"
    )


def downgrade() -> None:
    pass
