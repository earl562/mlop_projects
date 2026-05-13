-- mart_quality.sql — Daily pipeline quality trend for the last 30 days
--
-- WHAT THIS DOES: Aggregates analysis outcomes by day + municipality to produce
-- a time-series quality trend. Powers the 30-day confidence chart in /admin/data-quality.
--
-- WHY TIME-SERIES? A single confidence score doesn't tell you if quality is improving.
-- A 30-day trend shows: did re-ingestion improve confidence? Did a new municipality
-- drop quality when we first added it? Time-series makes regression detection possible.
--
-- CONSUMERS:
--   1. FastAPI /admin/data-quality endpoint (quality_trend response field)
--   2. Frontend confidence chart (30-day line chart by municipality)
--
-- DESIGN DECISION: DATE_TRUNC('day', created_at) as the time grain.
-- Day-level granularity is coarse enough to have statistically meaningful confidence scores
-- (multiple analyses per day) but fine enough to show weekly patterns.

{{ config(materialized='table') }}
-- 'table' — queried by the API on every dashboard load; physical table = predictable latency
-- 30-day window means this table is bounded in size regardless of total report_cache volume

SELECT
    DATE_TRUNC('day', created_at) AS analysis_date,
    -- Truncate the full timestamp to midnight on that day
    -- e.g. "2025-03-15 14:23:44" → "2025-03-15 00:00:00"
    -- This collapses all analyses for a given day into a single date bucket for GROUP BY
    -- The API casts this to text (::text) for JSON serialization since dates don't serialize natively

    municipality,
    -- Group by municipality AND day so you can see per-municipality quality trends
    -- e.g. Miami Gardens might improve after re-ingestion while Fort Lauderdale stays flat

    -- ─────────────────────────────────────────────────────────────────────
    -- VOLUME METRICS — how busy was this day?
    -- ─────────────────────────────────────────────────────────────────────
    COUNT(*) AS analyses_count,
    -- How many pipeline analyses completed on this day for this municipality
    -- High count = popular address or active testing
    -- Low count = weekend or quiet period

    -- ─────────────────────────────────────────────────────────────────────
    -- QUALITY METRICS — how good were the results?
    -- ─────────────────────────────────────────────────────────────────────
    AVG(
        CASE
            WHEN confidence_level = 'high'   THEN 1.0   -- Full LLM extraction: all key params found
            WHEN confidence_level = 'medium' THEN 0.5   -- Partial extraction: some params missing
            ELSE 0.0                                    -- Low/null: poor retrieval quality
        END
    ) AS avg_confidence_score,
    -- Daily quality trend signal: 0.0 to 1.0
    -- If this drops after a Municode scraping change, re-ingestion fixed the wrong thing
    -- If this rises after re-ingestion, we know the fix worked → the data confirms it

    -- Confidence distribution for stacked bar chart visualization
    COUNT(*) FILTER (WHERE confidence_level = 'high')    AS high_confidence_count,
    -- FILTER is a PostgreSQL extension that adds a WHERE clause to an aggregate function
    -- Equivalent to: SUM(CASE WHEN confidence_level = 'high' THEN 1 ELSE 0 END)
    -- But more readable and slightly faster in PostgreSQL

    COUNT(*) FILTER (WHERE confidence_level = 'medium')  AS medium_confidence_count,
    -- Medium: some params extracted — partial success

    COUNT(*) FILTER (WHERE confidence_level = 'low')     AS low_confidence_count,
    -- Low: extraction largely failed — likely a retrieval problem (sparse coverage)

    -- ─────────────────────────────────────────────────────────────────────
    -- OUTCOME METRICS — what are users getting back?
    -- ─────────────────────────────────────────────────────────────────────
    AVG(max_units)        AS avg_max_units,
    -- Average density outcome for this day + municipality
    -- Should be relatively stable unless zoning changed or extraction improved dramatically

    AVG(lot_size_sqft)    AS avg_lot_size_sqft
    -- Average parcel size being analyzed
    -- Shifts over time reveal what types of parcels users are looking up

FROM {{ ref('stg_analyses') }}
-- Pull from stg_analyses (which already unpacked the JSON and filtered expired entries)
-- {{ ref() }} creates DAG dependency: stg_analyses runs before mart_quality
-- stg_analyses already filters WHERE expires_at > NOW() — so only active cache entries included

WHERE created_at > NOW() - INTERVAL '30 days'
-- Only include the last 30 days
-- Keeps this mart table bounded in size regardless of total report_cache volume
-- The 30-day window matches the frontend chart (30-day confidence trend)
-- Anything older isn't shown in the UI and doesn't need to be in this mart

GROUP BY
    DATE_TRUNC('day', created_at),   -- The time bucket (day)
    municipality                      -- The geographic dimension

ORDER BY analysis_date DESC
-- Most recent dates first — makes API consumption simpler (no need to reverse)
