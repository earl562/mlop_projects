"""Add district_dimensional_standards table (review feedback B3).

Revision ID: 011_add_district_dimensional_standards
Revises: 010_harness_source_authority_events
Create Date: 2026-06-27

Creates district_dimensional_standards with verification_status column.
Idempotent (CREATE TABLE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS).
"""

revision = "011_add_district_dimensional_standards"
down_revision = "010_harness_source_authority_events"
branch_labels = None
depends_on = None

from alembic import op  # noqa: E402
import sqlalchemy as sa  # noqa: E402


def _execute_statements(script: str) -> None:
    for statement in script.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    _execute_statements("""
    CREATE TABLE IF NOT EXISTS district_dimensional_standards (
        id SERIAL PRIMARY KEY,
        municipality VARCHAR(200) NOT NULL,
        county VARCHAR(100) NOT NULL,
        state VARCHAR(2) DEFAULT 'FL',
        district_code VARCHAR(40) NOT NULL,
        min_lot_area_sqft FLOAT,
        min_lot_width_ft FLOAT,
        setback_front_ft FLOAT,
        setback_side_ft FLOAT,
        setback_rear_ft FLOAT,
        max_height_ft FLOAT,
        max_lot_coverage_pct FLOAT,
        far FLOAT,
        max_density_units_per_acre FLOAT,
        source_section_id VARCHAR(300) NOT NULL DEFAULT '',
        source_url TEXT,
        extracted_at TIMESTAMPTZ DEFAULT now(),
        verification_status VARCHAR(20) DEFAULT 'unverified',
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );
    CREATE UNIQUE INDEX IF NOT EXISTS uq_district_dimensional_standard
        ON district_dimensional_standards (municipality, district_code);
    CREATE INDEX IF NOT EXISTS ix_dds_verification_status
        ON district_dimensional_standards (verification_status);
    """)
    # Idempotent: if table already exists from create_all, add column if missing.
    _execute_statements("""
    ALTER TABLE district_dimensional_standards
        ADD COLUMN IF NOT EXISTS verification_status VARCHAR(20) DEFAULT 'unverified';
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS district_dimensional_standards;")
