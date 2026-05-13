-- mart_coverage.sql — Municipality coverage dashboard
--
-- WHAT THIS DOES: Final analytics-ready table for the municipality coverage dashboard.
-- This is what the /admin/data-quality API endpoint will query (Step 19 in the plan).
-- Also demo-able directly in a BI tool (Metabase, Superset) or the Dagster UI.
--
-- DATA LINEAGE:
--   ordinance_chunks (source)
--     → stg_coverage (aggregate by municipality)
--     → int_pipeline_health (join with stg_analyses, add coverage_tier)
--     → mart_coverage (add boolean flags, final consumer-ready layer)
--
-- BOOLEAN FLAGS: is_stale and is_gap are the key outputs.
-- Dagster's municipality_freshness_asset reads these flags to decide what to re-ingest.
-- The API uses is_gap and is_stale for dashboard filtering and gap analysis.
--
-- CONSUMERS:
--   1. FastAPI /admin/data-quality endpoint (replaces raw SQL in routes.py)
--   2. Dagster municipality_freshness_asset (reads is_stale to trigger re-ingestion)
--   3. BI dashboard (if connected — can point Metabase at plotlot_dbt schema)

{{ config(materialized='table') }}
-- 'table' — consumers (API, Dagster) query this directly; physical table = fast reads
-- Not a view because is_stale computation involves NOW() which should be evaluated at dbt run time
-- (If it were a view, is_stale would be recomputed on every API call, which is fine but less predictable)

SELECT
    -- ─────────────────────────────────────────────────────────────────────
    -- IDENTITY DIMENSIONS
    -- ─────────────────────────────────────────────────────────────────────
    municipality,           -- e.g. "Miami Gardens" — primary entity key for this mart
    county,                 -- e.g. "Miami-Dade" — geographic grouping dimension
    state,                  -- e.g. "FL" — for multi-state expansion filtering

    -- ─────────────────────────────────────────────────────────────────────
    -- COVERAGE METRICS — how well indexed is this municipality?
    -- ─────────────────────────────────────────────────────────────────────
    chunk_count,            -- Total ordinance chunks indexed (raw volume metric)
    section_count,          -- Distinct zoning sections covered (breadth metric)
    last_scraped_at,        -- When data was last refreshed
    days_since_ingest,      -- Age of data in days (computed in int_pipeline_health via EXTRACT)

    -- ─────────────────────────────────────────────────────────────────────
    -- USAGE SIGNAL — how often is this municipality being analyzed?
    -- ─────────────────────────────────────────────────────────────────────
    total_analyses_run,     -- Pipeline runs for this municipality (from stg_analyses via LEFT JOIN)
                            -- High total = popular municipality; worth prioritizing re-ingestion

    -- ─────────────────────────────────────────────────────────────────────
    -- QUALITY SIGNAL — is this municipality producing good analyses?
    -- ─────────────────────────────────────────────────────────────────────
    ROUND(avg_confidence_score::numeric, 2) AS avg_confidence_score,
    -- Round to 2 decimal places for display (0.00 to 1.00)
    -- ::numeric cast required before ROUND() in PostgreSQL (can't round float directly)
    -- 0.00 = all analyses low confidence (sparse coverage)
    -- 1.00 = all analyses high confidence (rich coverage)

    coverage_tier,          -- 'rich', 'adequate', or 'sparse' (computed in int_pipeline_health)
                            -- Used for dashboard badge color and filter chips

    -- ─────────────────────────────────────────────────────────────────────
    -- BOOLEAN FLAGS — the actionable outputs for Dagster and the API
    -- ─────────────────────────────────────────────────────────────────────
    CASE
        WHEN chunk_count = 0 THEN true   -- Municipality has zero chunks indexed
        ELSE false                       -- At least one chunk exists
    END AS is_gap,
    -- True: municipality is discoverable on Municode but has NEVER been ingested
    -- 88 municipalities are discoverable; currently only 5 are indexed = 83 gaps
    -- Dashboard uses this for the "gap count" stat (how many municipalities need work)
    -- Dagster uses this to trigger ingestion for newly discovered municipalities

    CASE
        WHEN days_since_ingest > 30 THEN true
        -- Data older than 30 days is considered stale
        -- Zoning ordinances don't change daily, but 30 days is a reasonable freshness window
        -- If a municipality amended its zoning code, we want to capture that within a month
        ELSE false
    END AS is_stale
    -- True: this municipality hasn't been re-ingested in over 30 days
    -- Dagster's nightly_freshness_schedule reads this flag to decide what to re-ingest
    -- Most nights: 0 municipalities are stale → Dagster runs, logs "nothing to do", exits cleanly

FROM {{ ref('int_pipeline_health') }}
-- Pull from the intermediate model which already has the JOIN + GROUP BY done
-- {{ ref() }} creates DAG dependency: int_pipeline_health runs before mart_coverage
-- Which means: stg_coverage and stg_analyses run before int_pipeline_health
-- dbt resolves the full dependency chain from this single ref() call

ORDER BY chunk_count DESC
-- Richest municipalities first — most useful default for the dashboard
-- Fort Lauderdale (136 chunks, sparse) appears at the bottom = visual priority indicator
