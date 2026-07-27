"""Add ordinance_sections table — structural index over chunks.

Revision ID: 009_ordinance_sections
Revises: 008
Create Date: 2026-06-26

Slice 3.1: `OrdinanceSection` is the structural unit over `OrdinanceChunk`
(the embedding unit). One row per municode section, keyed by
(municipality, node_id), carrying:

- `path`       — hierarchical breadcrumb, root-first (e.g. ["Chapter 47",
                 "Sec. 47-5.60"]).
- `section_type` — regulation | definition | schedule | dimensional_table
                 | use_regulation. Drives the Phase 8 AgenticRAG fast-path.
- `cross_refs` — outbound section-number references (e.g. ["47-24.3"]).
                 Drives follow_cross_ref traversal.
- `referenced_by` — reverse index (node_ids citing this section). Defaults to
                 empty; populated by the Slice 3.5 backfill.

PROVISIONING NOTE: the runtime ingestion path provisions tables via
`init_db` -> `Base.metadata.create_all` (see `storage/db.py`), so this table
is auto-created on first connect regardless of whether this migration is
applied. The migration exists for the operator-managed alembic-apply path
and is written idempotently (CREATE TABLE IF NOT EXISTS / CREATE INDEX IF
NOT EXISTS) so it is safe to re-run and safe to apply out-of-order with the
chunk tables.

GRAPH NOTE: the alembic versions dir already carries a pre-existing
duplicate-revision anomaly (two files claim revision "008", two claim "007";
`alembic heads` reports two heads both named "008"). That is a separate,
pre-existing operator-to-resolve issue and is NOT introduced by this slice.
This migration's `down_revision = "008"` references that head family; once an
operator collapses the duplicate heads, this node chains onto the single
resolved head without further edit.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "009_ordinance_sections"
down_revision: Union[str, None] = "008_lineage_backfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent raw SQL (mirrors the 008_add_missing_lineage_state_columns
    # pattern) so this migration is safe to re-run and to apply on a DB that
    # `create_all` already provisioned.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ordinance_sections (
            id SERIAL PRIMARY KEY,
            municipality VARCHAR(200) NOT NULL,
            county VARCHAR(100) NOT NULL,
            state VARCHAR(2),
            node_id VARCHAR(200),
            heading VARCHAR(1000),
            section_number VARCHAR(200),
            section_title VARCHAR(1000),
            section_type VARCHAR(40) NOT NULL DEFAULT 'regulation',
            path VARCHAR[] NOT NULL DEFAULT '{}',
            cross_refs VARCHAR[] NOT NULL DEFAULT '{}',
            referenced_by VARCHAR[] NOT NULL DEFAULT '{}',
            source_url VARCHAR,
            scraped_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_section_natural_key'
            ) THEN
                ALTER TABLE ordinance_sections
                    ADD CONSTRAINT uq_section_natural_key
                    UNIQUE (municipality, node_id);
            END IF;
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ordinance_sections_municipality "
        "ON ordinance_sections (municipality)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ordinance_sections_node_id ON ordinance_sections (node_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ordinance_sections_section_number "
        "ON ordinance_sections (section_number)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ordinance_sections_section_type "
        "ON ordinance_sections (section_type)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ordinance_sections")
