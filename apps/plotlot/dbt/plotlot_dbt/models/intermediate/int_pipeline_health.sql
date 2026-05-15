-- int_pipeline_health.sql — Multi-system attribution: coverage metrics + analysis quality
--
-- WHAT THIS DOES: Joins ordinance coverage data (stg_coverage) with pipeline analysis
-- results (stg_analyses) to answer the question:
-- "Does richer ordinance coverage produce higher-confidence analyses?"
--
-- This is the "multi-system attribution" skill the Flow JD asks for.
-- Data lives in TWO source tables:
--   ordinance_chunks  → scraped data volume, freshness, section breadth
--   report_cache      → analysis outcomes, confidence levels, density results
-- This model bridges them through the shared municipality field.
--
-- INTERVIEW FRAMING: "I joined coverage metrics from our ingestion pipeline with
-- analysis quality from our LLM pipeline to prove that sparse coverage correlates
-- with low confidence. That justified prioritizing Fort Lauderdale re-ingestion."
--
-- JOIN TYPE: LEFT JOIN — keep ALL municipalities from coverage,
-- even those with zero analyses run. They're gaps in our analytics too.

{{ config(materialized='table') }}
-- 'table' materialization: dbt writes a physical table in plotlot_dbt schema
-- Use 'table' (not 'view') for intermediate models because:
--   1. mart_coverage JOINs this model — physical table = faster mart queries
--   2. The municipality JOIN + AVG aggregation is expensive to recompute every time
-- Trade-off: slightly stale (refreshed on dbt run) vs. always-fresh (view)
-- Acceptable here — municipalities don't change intra-day

SELECT
    -- ─────────────────────────────────────────────────────────────────────
    -- COVERAGE DIMENSIONS — from stg_coverage (one row per municipality already)
    -- ─────────────────────────────────────────────────────────────────────
    c.municipality,                                           -- e.g. "Miami Gardens"
    c.county,                                                 -- e.g. "Miami-Dade"
    c.state,                                                  -- e.g. "FL"
    c.chunk_count,                                            -- Total ordinance chunks indexed
    c.last_scraped_at,                                        -- When data was last refreshed
    c.section_count,                                          -- Distinct sections covered

    EXTRACT(DAY FROM c.data_age_interval) AS days_since_ingest,
    -- Extract just the day count from the INTERVAL type
    -- INTERVAL '14 days 06:23' → 14 (as float, cast to int in mart_coverage)
    -- Used by mart_coverage to compute is_stale (> 30 days = stale)
    -- Dagster reads is_stale to decide what to re-ingest nightly

    -- ─────────────────────────────────────────────────────────────────────
    -- ANALYSIS QUALITY METRICS — aggregated from stg_analyses
    -- These come from the RIGHT side of the LEFT JOIN
    -- If no analyses exist for a municipality, these will be NULL
    -- ─────────────────────────────────────────────────────────────────────
    COUNT(a.id) AS total_analyses_run,
    -- How many times this municipality has been analyzed
    -- NULL-safe: COUNT(a.id) returns 0 when the LEFT JOIN produces no matches
    -- (municipalities with coverage but zero pipeline runs get total_analyses_run = 0)

    AVG(a.max_units) AS avg_max_units,
    -- Average calculated density across all analyses for this municipality
    -- Sanity check metric: should correlate with the zone's max_density_uac
    -- Large outliers = extraction errors worth investigating

    AVG(
        CASE
            WHEN a.confidence_level = 'high'   THEN 1.0
            -- High confidence: LLM extracted all key numeric params (density, FAR, setbacks)
            -- Full score — this is the happy path
            WHEN a.confidence_level = 'medium' THEN 0.5
            -- Medium confidence: some params extracted, some missing
            -- Still useful but pro forma may be incomplete
            ELSE 0.0
            -- Low confidence: few params extracted, analysis unreliable
            -- This is the signal that re-ingestion or better retrieval is needed
        END
    ) AS avg_confidence_score,
    -- 0.0 to 1.0 quality signal per municipality
    -- Hypothesis: municipalities with more chunks → higher avg_confidence_score
    -- This join lets us TEST that hypothesis with real data (multi-system attribution)

    -- ─────────────────────────────────────────────────────────────────────
    -- COVERAGE TIER — categorize municipality by data richness
    -- Used in mart_coverage for dashboard filtering
    -- ─────────────────────────────────────────────────────────────────────
    CASE
        WHEN c.chunk_count > 1000 THEN 'rich'
        -- Rich: 1000+ chunks — e.g. Miami Gardens (3,561), Miami-Dade County (2,666)
        -- These municipalities have broad section coverage and high extraction quality
        WHEN c.chunk_count > 200  THEN 'adequate'
        -- Adequate: 200-1000 chunks — e.g. Miramar (241), Boca Raton (1,538)
        -- Good enough for most zone types, may miss edge cases
        ELSE 'sparse'
        -- Sparse: <200 chunks — e.g. Fort Lauderdale (136)
        -- High risk of retrieval misses and low-confidence extractions
    END AS coverage_tier

FROM {{ ref('stg_coverage') }} c
-- {{ ref('stg_coverage') }} tells dbt: "this model depends on stg_coverage"
-- dbt builds stg_coverage BEFORE this model — dependency resolved automatically from the DAG
-- ref() also ensures schema prefixing: resolves to plotlot_dbt.stg_coverage at runtime

LEFT JOIN {{ ref('stg_analyses') }} a
-- LEFT JOIN: keep ALL municipalities from stg_coverage, even with zero analyses
-- A municipality with chunks but zero analyses is still worth showing in the dashboard
-- INNER JOIN would silently drop municipalities that haven't been queried yet
    ON a.municipality = c.municipality
-- Join key: municipality name (normalized consistently in both pipelines)
-- Potential improvement: normalize to LOWER() on both sides for robustness

GROUP BY
    -- All non-aggregated columns from stg_coverage must appear in GROUP BY
    c.municipality, c.county, c.state,
    c.chunk_count, c.last_scraped_at,
    c.data_age_interval,    -- The INTERVAL — used in EXTRACT above
    c.section_count
