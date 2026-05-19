-- stg_portfolio.sql — Unpacks portfolio_entries.report_json for user deal analytics
--
-- WHAT THIS DOES: Same JSON unpacking pattern as stg_analyses, but for the portfolio table.
-- portfolio_entries has the same report_json structure as report_cache.
-- This separation exists because they serve different analytical questions:
--   stg_analyses → "What is the overall quality of PlotLot's pipeline outputs?"
--   stg_portfolio → "What kinds of deals are users saving? What are they targeting?"
--
-- KEY COLUMNS: max_units and max_land_price tell us the user's deal strategy.
-- High max_units = density plays (multifamily/apartment). Low max_units = low-density.
-- High max_land_price = large projects. This powers mart_usage deal behavior metrics.
--
-- ENTITY RESOLUTION: user_id is the Clerk UUID that appears in BOTH portfolio_entries
-- and user_subscriptions. int_user_activity joins these two tables on user_id.

{{ config(materialized='view') }}

SELECT
    id,                 -- Source row UUID — keeps this joinable to portfolio_entries

    user_id,            -- Clerk UUID — the entity resolution key
                        -- This same user_id exists in user_subscriptions as the primary key
                        -- int_user_activity joins stg_portfolio + stg_subscriptions on this field

    address,            -- Raw user-input address for this saved deal (display only)

    municipality,       -- Denormalized into portfolio_entries as its own column (not inside JSON)
                        -- FastAPI writes this separately for fast filtering without JSON parsing
                        -- Match: report_cache uses report_json->>'municipality' (not a column)

    county,             -- Denormalized county — same pattern as municipality

    zoning_district,    -- Denormalized zoning code — e.g. "RM-25"

    created_at,         -- When the user saved this deal to their portfolio
                        -- Used in int_user_activity to compute last_deal_saved_at (recency signal)

    -- ─────────────────────────────────────────────────────────────────────
    -- JSON UNPACKING — financial outputs from the pipeline
    -- Same ->> operator pattern as stg_analyses
    -- These fields reveal WHAT DEALS USERS ARE SAVING (deal strategy analytics)
    -- ─────────────────────────────────────────────────────────────────────

    (report_json->'density_analysis'->>'max_units')::integer   AS max_units,
    -- Max buildable units on this parcel — shows whether the user targets density plays
    -- Aggregated in mart_usage as AVG(avg_deal_max_units) per plan tier

    (report_json->'pro_forma'->>'max_land_price')::float       AS max_land_price,
    -- Residual land value from the pro forma model — "what's the most I should pay?"
    -- High max_land_price = large project, aggressive market
    -- Aggregated in int_user_activity as AVG(avg_deal_land_price)

    (report_json->'pro_forma'->>'cost_per_door')::float        AS cost_per_door,
    -- Construction cost per dwelling unit — market-rate vs affordable development signal

    (report_json->>'confidence')::text                         AS confidence_level
    -- LLM extraction confidence: "high", "medium", or "low"
    -- Low confidence saves = user bookmarking uncertain analyses (potential quality issue)

FROM {{ source('plotlot', 'portfolio_entries') }}
-- {{ source('plotlot', 'portfolio_entries') }} resolves to "public"."portfolio_entries"
-- No WHERE clause here — we want ALL saved deals regardless of age (no TTL on portfolio)
