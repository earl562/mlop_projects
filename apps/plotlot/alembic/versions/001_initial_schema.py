"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-09

Matches the existing schema created by Base.metadata.create_all() so that
existing databases can `alembic stamp 001` without re-creating tables.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import TSVECTOR

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pgvector extension is available
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "ordinance_chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("municipality", sa.String(length=200), nullable=False),
        sa.Column("county", sa.String(length=100), nullable=False),
        sa.Column("chapter", sa.String(length=500), nullable=True),
        sa.Column("section", sa.String(length=200), nullable=True),
        sa.Column("section_title", sa.String(length=500), nullable=True),
        sa.Column("zone_codes", sa.ARRAY(sa.String()), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("municode_node_id", sa.String(length=200), nullable=True),
        sa.Column("search_vector", TSVECTOR(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ordinance_chunks_county"), "ordinance_chunks", ["county"])
    op.create_index(
        op.f("ix_ordinance_chunks_municipality"), "ordinance_chunks", ["municipality"]
    )

    # Full-text search trigger and GIN index (mirrors init_db())
    op.execute("""
        CREATE OR REPLACE FUNCTION ordinance_chunks_search_vector_update()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector := to_tsvector('english', COALESCE(NEW.chunk_text, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger WHERE tgname = 'trg_search_vector_update'
            ) THEN
                CREATE TRIGGER trg_search_vector_update
                BEFORE INSERT OR UPDATE OF chunk_text
                ON ordinance_chunks
                FOR EACH ROW
                EXECUTE FUNCTION ordinance_chunks_search_vector_update();
            END IF;
        END $$;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_search_vector
        ON ordinance_chunks USING GIN (search_vector);
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_search_vector_update ON ordinance_chunks")
    op.execute("DROP FUNCTION IF EXISTS ordinance_chunks_search_vector_update()")
    op.drop_index("idx_search_vector", table_name="ordinance_chunks")
    op.drop_index(op.f("ix_ordinance_chunks_municipality"), table_name="ordinance_chunks")
    op.drop_index(op.f("ix_ordinance_chunks_county"), table_name="ordinance_chunks")
    op.drop_table("ordinance_chunks")
