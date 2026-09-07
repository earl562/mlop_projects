"""Add source authorities, snapshots, harness events tables (Phase 1).

Revision ID: 010_harness_source_authority_events
Revises: 009_ordinance_sections
Create Date: 2026-06-26

Master spec §7: jurisdiction_source_authorities, ordinance_source_snapshots,
harness_events. Also extends ordinance_sections + ordinance_chunks with
source_authority_id / snapshot_id / chunk_kind / quality_flags.
Idempotent (CREATE TABLE IF NOT EXISTS) — safe to re-run.
"""

revision = "010_source_events"
down_revision = "009_ordinance_sections"
branch_labels = None
depends_on = None

from alembic import op  # noqa: E402


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS jurisdiction_source_authorities (
        id VARCHAR(120) PRIMARY KEY,
        state VARCHAR(2) NOT NULL,
        county VARCHAR(100) NOT NULL,
        municipality VARCHAR(200),
        jurisdiction_type VARCHAR(40) NOT NULL,
        authority_scope VARCHAR(40) NOT NULL,
        provider VARCHAR(40) NOT NULL,
        canonical_url TEXT NOT NULL,
        source_url TEXT NOT NULL,
        source_title VARCHAR(500) NOT NULL,
        official_status VARCHAR(40) NOT NULL DEFAULT 'unknown',
        legal_caveat TEXT NOT NULL,
        freshness_policy VARCHAR(20) NOT NULL DEFAULT 'monthly',
        last_checked_at TIMESTAMPTZ,
        last_ingested_at TIMESTAMPTZ,
        source_version VARCHAR(200),
        supplement_number VARCHAR(100),
        effective_date VARCHAR(40),
        ingestion_status VARCHAR(40) NOT NULL DEFAULT 'pending',
        coverage_score FLOAT,
        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    );
    """)
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_jurisdiction_source_authority_natural_key
        ON jurisdiction_source_authorities (state, county, municipality, authority_scope, provider)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_jsa_state ON jurisdiction_source_authorities (state)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_jsa_authority_scope "
        "ON jurisdiction_source_authorities (authority_scope)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_jsa_provider ON jurisdiction_source_authorities (provider)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_jsa_municipality "
        "ON jurisdiction_source_authorities (municipality)"
    )
    op.execute("""
    CREATE TABLE IF NOT EXISTS ordinance_source_snapshots (
        id VARCHAR(120) PRIMARY KEY,
        source_authority_id VARCHAR(120) NOT NULL
            REFERENCES jurisdiction_source_authorities(id),
        source_url TEXT NOT NULL,
        final_url TEXT,
        fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        http_status INTEGER,
        content_type VARCHAR(200),
        content_hash VARCHAR(64) NOT NULL,
        raw_storage_url TEXT,
        raw_text_excerpt TEXT,
        etag VARCHAR(500),
        last_modified VARCHAR(200),
        source_version VARCHAR(200),
        metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
    )
    """)
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_ordinance_source_snapshot_natural_key
        ON ordinance_source_snapshots (source_authority_id, content_hash)""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_oss_source_authority "
        "ON ordinance_source_snapshots (source_authority_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_oss_content_hash "
        "ON ordinance_source_snapshots (content_hash)"
    )
    op.execute("""
    CREATE TABLE IF NOT EXISTS harness_events (
        id VARCHAR(120) PRIMARY KEY,
        type VARCHAR(60) NOT NULL,
        timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
        correlation_id VARCHAR(120) NOT NULL,
        severity VARCHAR(10) NOT NULL DEFAULT 'info',
        workspace_id VARCHAR(120),
        project_id VARCHAR(120),
        site_id VARCHAR(120),
        analysis_id VARCHAR(120),
        analysis_run_id VARCHAR(120),
        ingestion_run_id VARCHAR(120),
        source_authority_id VARCHAR(120),
        tool_run_id VARCHAR(120),
        payload JSONB NOT NULL DEFAULT '{}'::jsonb
    )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_he_type ON harness_events (type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_he_timestamp ON harness_events (timestamp)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_he_analysis_run ON harness_events (analysis_run_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_he_ingestion_run ON harness_events (ingestion_run_id)"
    )
    op.execute("""
    ALTER TABLE ordinance_chunks
        ADD COLUMN IF NOT EXISTS source_authority_id VARCHAR(120),
        ADD COLUMN IF NOT EXISTS snapshot_id VARCHAR(120),
        ADD COLUMN IF NOT EXISTS chunk_kind VARCHAR(40) DEFAULT 'narrative',
        ADD COLUMN IF NOT EXISTS quality_flags JSONB DEFAULT '{}'::jsonb,
        ADD COLUMN IF NOT EXISTS table_row_key VARCHAR(200),
        ADD COLUMN IF NOT EXISTS source_page INTEGER
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_oc_source_authority "
        "ON ordinance_chunks (source_authority_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_oc_chunk_kind ON ordinance_chunks (chunk_kind)"
    )
    op.execute("""
    ALTER TABLE ordinance_sections
        ADD COLUMN IF NOT EXISTS source_authority_id VARCHAR(120),
        ADD COLUMN IF NOT EXISTS snapshot_id VARCHAR(120),
        ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64),
        ADD COLUMN IF NOT EXISTS parser_version VARCHAR(40),
        ADD COLUMN IF NOT EXISTS quality_flags JSONB DEFAULT '{}'::jsonb
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS harness_events")
    op.execute("DROP TABLE IF EXISTS ordinance_source_snapshots")
    op.execute("DROP TABLE IF EXISTS jurisdiction_source_authorities")
    op.execute("""
    ALTER TABLE ordinance_chunks
        DROP COLUMN IF EXISTS source_authority_id,
        DROP COLUMN IF EXISTS snapshot_id,
        DROP COLUMN IF EXISTS chunk_kind,
        DROP COLUMN IF EXISTS quality_flags,
        DROP COLUMN IF EXISTS table_row_key,
        DROP COLUMN IF EXISTS source_page
    """)
    op.execute("""
    ALTER TABLE ordinance_sections
        DROP COLUMN IF EXISTS source_authority_id,
        DROP COLUMN IF EXISTS snapshot_id,
        DROP COLUMN IF EXISTS content_hash,
        DROP COLUMN IF EXISTS parser_version,
        DROP COLUMN IF EXISTS quality_flags
    """)
