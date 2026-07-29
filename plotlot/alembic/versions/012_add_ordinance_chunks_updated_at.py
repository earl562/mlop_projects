"""Add ordinance_chunks.updated_at.

Revision ID: 012
Revises: 011
Create Date: 2026-07-28

Closes the last known divergence between the ORM models and the live database,
so the startup drift check returns to silent and a future warning means a real
new problem rather than a known exception.

Deliberately added WITHOUT backfilling existing rows. Adding the column with
`DEFAULT now()` in a single statement would stamp all ~41k already-ingested
chunks as updated at migration time, which is a fabricated timestamp for rows
scraped months earlier; `scraped_at` already records genuine ingestion times.
Existing rows therefore keep NULL ("not known to have been updated") and the
default applies only to rows written from here on.

Both statements are catalog-only on PostgreSQL 11+ (no table rewrite), so this
is effectively instant regardless of row count.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ordinance_chunks",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Set the default separately so existing rows stay NULL rather than being
    # backfilled with the migration's own timestamp.
    op.execute("ALTER TABLE ordinance_chunks ALTER COLUMN updated_at SET DEFAULT now()")


def downgrade() -> None:
    op.drop_column("ordinance_chunks", "updated_at")
