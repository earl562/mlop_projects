"""Add connector_credentials table (Phase 5 SMTP).

Revision ID: d3e4f5a6b7c8
Revises: 006
Create Date: 2026-05-01

This migration was applied directly to Neon but the file was not committed.
Reconstructed here to unblock the Alembic revision chain.
The 007 migration uses IF NOT EXISTS, so re-running is safe.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.execute("DROP TABLE IF EXISTS connector_credentials")
