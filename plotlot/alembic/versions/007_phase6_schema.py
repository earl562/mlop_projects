"""Phase 6 schema changes.

Revision ID: 007
Revises: 006
Create Date: 2026-05-08

1. report_cache: drop old unique index on address_normalized,
   add analysis_type column (default 'residential'),
   add composite unique constraint on (address_normalized, analysis_type).

2. connector_credentials: create table for Phase 5 SMTP connector
   (may already exist if manually created — migration is idempotent via
   op.create_table with checkfirst=True not available in Alembic, so we
   use raw SQL with IF NOT EXISTS).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "007_phase6"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── report_cache: drop old unique-on-address_normalized ────────────
    # The old index enforced uniqueness only on address_normalized.
    # Phase 6 introduces a second analysis_type dimension.
    op.execute("DROP INDEX IF EXISTS ix_report_cache_address_normalized")

    # Add analysis_type column if not exists
    op.execute(
        """
        ALTER TABLE report_cache
        ADD COLUMN IF NOT EXISTS analysis_type VARCHAR(50)
            NOT NULL DEFAULT 'residential'
        """
    )

    # Add composite unique constraint
    op.execute(
        """
        ALTER TABLE report_cache
        DROP CONSTRAINT IF EXISTS uq_report_cache_key
        """
    )
    op.execute(
        """
        ALTER TABLE report_cache
        ADD CONSTRAINT uq_report_cache_key
        UNIQUE (address_normalized, analysis_type)
        """
    )

    # ── connector_credentials ───────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_credentials (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(128) NOT NULL,
            smtp_host VARCHAR(255) NOT NULL,
            smtp_port INTEGER NOT NULL DEFAULT 587,
            smtp_username VARCHAR(255) NOT NULL,
            smtp_password_enc TEXT NOT NULL,
            from_name VARCHAR(255),
            daily_send_count INTEGER NOT NULL DEFAULT 0,
            send_count_reset_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            CONSTRAINT uq_connector_session UNIQUE (session_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_connector_credentials_session_id
        ON connector_credentials (session_id)
        """
    )


def downgrade() -> None:
    # Remove analysis_type from report_cache and restore old unique index
    op.execute("ALTER TABLE report_cache DROP CONSTRAINT IF EXISTS uq_report_cache_key")
    op.execute("ALTER TABLE report_cache DROP COLUMN IF EXISTS analysis_type")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_report_cache_address_normalized
        ON report_cache (address_normalized)
        """
    )

    # Drop connector_credentials
    op.execute("DROP TABLE IF EXISTS connector_credentials")
