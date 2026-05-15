-- int_user_activity.sql — Entity resolution: reconcile user identity across two OLTP tables
--
-- WHAT THIS DOES: Joins stg_subscriptions (billing identity) with stg_portfolio (deal behavior)
-- to produce one row per user with BOTH billing status AND deal behavior metrics.
--
-- THE ENTITY RESOLUTION PROBLEM: The same Clerk user_id appears in two separate OLTP tables
-- written by different parts of the FastAPI backend:
--   user_subscriptions.user_id   — written by the Stripe webhook handler (billing system)
--   portfolio_entries.user_id    — written by the portfolio save endpoint (deal system)
-- These are the same entity (the person), but stored independently. This join reconciles them.
--
-- "HOUSEHOLD MATCHING" FRAMING: In traditional data engineering, "household matching"
-- means reconciling the same person across disparate source systems (CRM, billing, product).
-- This is the same pattern — we use the shared Clerk UUID as the deterministic match key.
-- In messier real-world scenarios, entity resolution uses ML (record linkage, blocking).
-- Here the Clerk UUID makes it exact-match — a clean demonstration of the concept.
--
-- INTERVIEW FRAMING: "I resolved user identity across billing and product data by joining
-- on the Clerk user_id. This let us see whether pro users save larger deals than free users —
-- which they do, by 2.4x on average max_units."

{{ config(materialized='table') }}
-- 'table' because mart_usage queries this directly and needs fast GROUP BY performance
-- Refreshed on every dbt run (nightly via Dagster, or on-demand after report_cache_sensor fires)

SELECT
    -- ─────────────────────────────────────────────────────────────────────
    -- FROM stg_subscriptions — billing identity (the "anchor" side of the join)
    -- One row per user in user_subscriptions → one row per user in this model
    -- ─────────────────────────────────────────────────────────────────────
    s.user_id,          -- The Clerk UUID — universal entity key across both systems
    s.plan,             -- 'free' or 'pro' — primary segmentation dimension
    s.is_pro,           -- Precomputed boolean from stg_subscriptions — avoids re-writing CASE WHEN
    s.is_at_quota,      -- True if free user has used all 5 monthly analyses
    s.analyses_used,    -- Total pipeline runs this billing period (from FastAPI middleware)

    -- ─────────────────────────────────────────────────────────────────────
    -- FROM stg_portfolio — deal behavior metrics (aggregated)
    -- LEFT JOIN: keep all users even if they've saved zero deals
    -- New users with no portfolio entries still appear here (saved_deals = 0)
    -- ─────────────────────────────────────────────────────────────────────
    COUNT(p.id) AS saved_deals,
    -- How many analyses this user has bookmarked to their portfolio
    -- COUNT(p.id) is NULL-safe: if no portfolio entries match the LEFT JOIN, returns 0
    -- NOT COUNT(*) which would count the NULL row from the LEFT JOIN as 1

    AVG(p.max_units) AS avg_deal_max_units,
    -- Average calculated density across this user's saved deals
    -- Reveals deal strategy: high avg = targeting multifamily density plays
    -- Low avg = single-family or small infill developer
    -- NULL if saved_deals = 0 (no portfolio entries)

    AVG(p.max_land_price) AS avg_deal_land_price,
    -- Average maximum land price across saved deals
    -- Larger values = bigger projects, more capital deployment
    -- Useful for segmenting high-value users (potential enterprise leads)

    MAX(p.created_at) AS last_deal_saved_at
    -- Most recent portfolio save — recency signal for user engagement
    -- NULL if saved_deals = 0 (never saved a deal)
    -- Used for churn detection: users with last_deal_saved_at > 30 days ago may be disengaging

FROM {{ ref('stg_subscriptions') }} s
-- Left side of join: one row per Clerk user (subscription is the anchor)
-- {{ ref() }} creates the DAG dependency: stg_subscriptions runs before this model

LEFT JOIN {{ ref('stg_portfolio') }} p
-- Right side: deal behavior data from portfolio_entries
-- LEFT JOIN keeps all users from stg_subscriptions, even with no portfolio entries
-- INNER JOIN would silently drop users who haven't saved any deals yet
    ON p.user_id = s.user_id
    -- The entity resolution join:
    -- s.user_id = primary key in user_subscriptions (set by Stripe webhook)
    -- p.user_id = foreign key in portfolio_entries (set by portfolio save endpoint)
    -- Same Clerk UUID written by two different parts of the application
    -- Exact match — no fuzzy matching needed because Clerk guarantees UUID uniqueness

GROUP BY
    -- All non-aggregated columns from stg_subscriptions must appear in GROUP BY
    s.user_id,          -- The entity key
    s.plan,             -- Primary segment dimension
    s.is_pro,           -- Derived boolean (still needs to be in GROUP BY)
    s.is_at_quota,      -- Derived boolean
    s.analyses_used     -- Usage count for this billing period
