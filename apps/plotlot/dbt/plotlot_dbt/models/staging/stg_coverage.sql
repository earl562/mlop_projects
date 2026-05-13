-- stg_coverage.sql — Aggregates ordinance_chunks to municipality-level coverage metrics
--
-- WHAT THIS DOES: The source table (ordinance_chunks) has one row per ~500-token text chunk.
-- For analytics we need one row per municipality, not one row per chunk.
-- This model aggregates from chunk-level to municipality-level.
--
-- BUSINESS CONTEXT: PlotLot's quality depends directly on how many chunks are indexed
-- for a given municipality. Miami Gardens (3,561 chunks) produces better LLM extractions
-- than Fort Lauderdale (136 chunks). This model makes that relationship queryable.
--
-- FRESHNESS TRACKING: scraped_at tells us when data was last updated.
-- mart_coverage uses days_since_ingest to flag municipalities needing re-ingestion.
-- Dagster's nightly sensor reads mart_coverage.is_stale to decide what to re-ingest.

{{ config(materialized='view') }}
-- 'view' for staging — always reflects current chunk counts in real-time
-- If new chunks are ingested, this view immediately reflects the new counts

SELECT
    municipality,           -- e.g. "Miami Gardens" — the GROUP BY key
                            -- Matches the municipality field in report_cache for JOIN in int_pipeline_health

    county,                 -- e.g. "Miami-Dade" — for geographic filtering in the dashboard

    state,                  -- e.g. "FL" — allows multi-state filtering when we expand beyond Florida

    COUNT(*) AS chunk_count,
    -- Total rows in ordinance_chunks for this municipality
    -- This is the primary coverage metric:
    --   3,561 chunks → "rich" coverage (Miami Gardens)
    --   241 chunks   → "adequate" coverage (Miramar)
    --   136 chunks   → "sparse" coverage (Fort Lauderdale)
    -- mart_coverage uses these thresholds to assign coverage_tier

    MAX(scraped_at) AS last_scraped_at,
    -- The most recent scrape timestamp for this municipality
    -- If this is > 30 days ago, Dagster should re-ingest
    -- "Most recent" because partial re-ingestion only updates some rows

    MIN(scraped_at) AS first_scraped_at,
    -- When this municipality was first added to the system
    -- Useful for showing "data has been available since X" in the UI

    COUNT(DISTINCT section) AS section_count,
    -- How many distinct zoning code sections are represented
    -- High section_count = broad coverage (many zone types indexed)
    -- Low section_count = narrow coverage (only a few sections scraped)
    -- e.g. if only "Section 33-274" is indexed, queries about "Section 33-100" return no results

    NOW() - MAX(scraped_at) AS data_age_interval
    -- How old is the most recent scrape? Stored as a PostgreSQL INTERVAL type.
    -- e.g. '14 days 06:23:11' means the last scrape was 14 days ago
    -- int_pipeline_health extracts the DAY component with EXTRACT(DAY FROM ...)
    -- mart_coverage uses this to compute the is_stale boolean flag

FROM {{ source('plotlot', 'ordinance_chunks') }}
-- {{ source('plotlot', 'ordinance_chunks') }} resolves to "public"."ordinance_chunks"

WHERE scraped_at IS NOT NULL
-- Defensive filter: exclude any chunks that somehow lack a scrape timestamp
-- In theory shouldn't happen (scraped_at has a default), but protects against data anomalies
-- This is the "never trust external data" principle applied to production analytics

GROUP BY
    municipality,           -- Aggregate: collapse all chunks for "Miami Gardens" into one row
    county,                 -- Include in GROUP BY so we can SELECT it (required in standard SQL)
    state                   -- Include in GROUP BY so we can SELECT it
