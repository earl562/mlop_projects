"""Add missing lineage and state columns to ordinance_chunks.

Revision ID: 008_lineage
Revises: 007_phase6
Create Date: 2026-05-14

NOTE: revision id renamed from "008" to "008_lineage" (and down_revision from
"007" to "007_phase6") to resolve a duplicate-id collision with
008_add_harness_artifact_connector_eval_tables. This keeps the phase6 branch
(connector -> phase6 -> lineage) distinct from the harness branch.

Migration 005 was defined but skipped in the applied revision chain due to
a merge-head branch anomaly (88d5f65b958d). The ordinance_chunks table is
missing source_url, scraped_at, embedding_model, and state columns.

Using raw SQL with ADD COLUMN IF NOT EXISTS (PostgreSQL 9.6+) so this
migration is safe to re-run even if some columns were partially applied.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "008_lineage"
down_revision: Union[str, None] = "007_phase6"
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
    op.execute("ALTER TABLE ordinance_chunks DROP COLUMN IF EXISTS state")
    op.execute("ALTER TABLE ordinance_chunks DROP COLUMN IF EXISTS embedding_model")
    op.execute("ALTER TABLE ordinance_chunks DROP COLUMN IF EXISTS scraped_at")
    op.execute("ALTER TABLE ordinance_chunks DROP COLUMN IF EXISTS source_url")
