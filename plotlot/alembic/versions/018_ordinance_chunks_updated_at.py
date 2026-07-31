"""Add ordinance_chunks.updated_at.

Revision ID: 018_ordinance_chunks_updated_at
Revises: 017_assessor_parcel_cache
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

Idempotent by design. The Phat and production-MVP branches were reconciled after
both had already been applied to the live database, so this revision must run
against a database where these objects may ALREADY exist (created earlier under
different revision ids) or may not exist at all (a fresh database). Guarding each
object keeps a single migration correct for both, instead of requiring an
out-of-band stamp that would desync the two histories again.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018_ordinance_chunks_updated_at"
down_revision: Union[str, None] = "017_assessor_parcel_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    # See module docstring: may already exist from the pre-reconciliation history.
    if _has_column("ordinance_chunks", "updated_at"):
        return
    op.add_column(
        "ordinance_chunks",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Set the default separately so existing rows stay NULL rather than being
    # backfilled with the migration's own timestamp.
    op.execute("ALTER TABLE ordinance_chunks ALTER COLUMN updated_at SET DEFAULT now()")


def downgrade() -> None:
    op.drop_column("ordinance_chunks", "updated_at")
