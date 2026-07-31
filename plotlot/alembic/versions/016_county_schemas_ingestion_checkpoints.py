"""Add county_schemas and ingestion_checkpoints to the migration chain.

Revision ID: 016_county_schemas_checkpoints
Revises: 015_leased_jobs_outbox
Create Date: 2026-07-08

These two model tables (storage.models.CountySchema and IngestionCheckpoint)
were never represented in any migration — they only ever existed on databases
built by Base.metadata.create_all. This revision brings the migration chain up
to the full model schema so `alembic upgrade head` on a fresh database
reproduces EVERY table the ORM declares.

Adoption note: on the existing create_all-built database (Neon) these tables
already exist, so that database is brought under Alembic control with
`alembic stamp head` (which records the version without running DDL) rather than
`upgrade from base`. This migration therefore only executes against a fresh
database, where the tables do not yet exist. Column-level drift on the existing
database (e.g. workspaces.owner_user_id) is handled by a separate, idempotent
reconciliation migration authored after introspecting the live schema.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016_county_schemas_checkpoints"
down_revision: Union[str, None] = "015_leased_jobs_outbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingestion_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.String(length=50), nullable=False),
        sa.Column("municipality_key", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("chunks_stored", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "batch_id", "municipality_key", name="uq_checkpoint_batch_muni"
        ),
    )
    op.create_index(
        op.f("ix_ingestion_checkpoints_batch_id"),
        "ingestion_checkpoints",
        ["batch_id"],
    )

    op.create_table(
        "county_schemas",
        sa.Column("county_key", sa.String(length=200), primary_key=True),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("parcels_dataset", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("zoning_dataset", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("field_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ttl_hours", sa.Integer(), nullable=False),
        sa.Column(
            "last_verified",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
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
    )
    op.create_index(op.f("ix_county_schemas_state"), "county_schemas", ["state"])


def downgrade() -> None:
    op.drop_index(op.f("ix_county_schemas_state"), table_name="county_schemas")
    op.drop_table("county_schemas")
    op.drop_index(
        op.f("ix_ingestion_checkpoints_batch_id"), table_name="ingestion_checkpoints"
    )
    op.drop_table("ingestion_checkpoints")
