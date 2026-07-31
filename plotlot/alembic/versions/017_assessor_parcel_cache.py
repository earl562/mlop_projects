"""Add assessor_parcel_cache.

Revision ID: 017_assessor_parcel_cache
Revises: 016_county_schemas_checkpoints
Create Date: 2026-07-28

Durable cache for county-assessor parcel lookups (recorded lot area + owner).
Purely additive: a new standalone table with no foreign keys, so it cannot
affect existing data or the harness tables.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017_assessor_parcel_cache"
down_revision: Union[str, None] = "016_county_schemas_checkpoints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assessor_parcel_cache",
        sa.Column("cache_key", sa.String(length=80), primary_key=True),
        sa.Column("apn", sa.String(length=32), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("lot_sqft", sa.Float(), nullable=True),
        sa.Column("owner", sa.String(length=300), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_assessor_parcel_cache_apn"), "assessor_parcel_cache", ["apn"])


def downgrade() -> None:
    op.drop_index(op.f("ix_assessor_parcel_cache_apn"), table_name="assessor_parcel_cache")
    op.drop_table("assessor_parcel_cache")
