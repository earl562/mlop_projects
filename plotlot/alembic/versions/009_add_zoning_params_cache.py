"""Add zoning_params_cache table for L2 DB persistence of zoning params.

Revision ID: 009
Revises: 008a,008b
Create Date: 2026-06-19

Persists NumericZoningParams (JSONB) keyed by cache_key with 24h TTL.
Serves as L2 fallback when L1 in-memory cache is cold after restart.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009"
down_revision: Union[Sequence[str], str, None] = ("008a", "008b")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "zoning_params_cache",
        sa.Column("cache_key", sa.String(), primary_key=True),
        sa.Column("params_json", postgresql.JSONB(), nullable=False),
        sa.Column("text_fields_json", postgresql.JSONB(), nullable=True),
        sa.Column("chunk_ids", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("zoning_params_cache")
