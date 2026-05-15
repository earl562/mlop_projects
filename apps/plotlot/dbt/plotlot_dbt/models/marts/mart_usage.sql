-- mart_usage.sql — Plan-tier user analytics and conversion signal
--
-- WHAT THIS DOES: Aggregates int_user_activity by plan tier to answer:
--   - How many users on each plan?
--   - How much do they use the product?
--   - What kinds of deals do they save?
--   - How many free users are hitting the paywall (conversion candidates)?
--
-- CONSUMERS:
--   1. FastAPI /admin/data-quality endpoint (usage_by_plan response field)
--   2. Internal analytics dashboard (plan tier segmentation)
--   3. Investor updates (user engagement metrics)
--
-- BUSINESS VALUE: The is_at_quota column is the key conversion signal.
-- Free users who've hit 5 analyses are the highest-intent conversion candidates.
-- Knowing their count drives: email targeting, paywall copy A/B testing, pricing decisions.
--
-- DESIGN: This mart rolls up to plan-level (2 rows: 'free', 'pro').
-- It's intentionally coarse — individual user metrics live in int_user_activity.

{{ config(materialized='table') }}
-- 'table' — small result set (2 rows), fast to query, refreshed on dbt run

SELECT
    plan,
    -- The primary segmentation dimension: 'free' or 'pro'
    -- This mart produces exactly 2 rows: one per plan tier
    -- Downstream: API returns this as an array of {plan, user_count, ...} objects

    -- ─────────────────────────────────────────────────────────────────────
    -- USER VOLUME METRICS
    -- ─────────────────────────────────────────────────────────────────────
    COUNT(*) AS user_count,
    -- Total users on this plan tier (every row in int_user_activity = one user)
    -- Free user count → potential conversion pool
    -- Pro user count → revenue-generating users

    -- ─────────────────────────────────────────────────────────────────────
    -- USAGE METRICS — how much are they using the product?
    -- ─────────────────────────────────────────────────────────────────────
    SUM(analyses_used) AS total_analyses,
    -- Sum of all pipeline runs across all users on this plan
    -- Pro tier: unlimited, so this shows actual demand
    -- Free tier: capped at 5/user, so this shows demand within the cap

    AVG(analyses_used) AS avg_analyses_per_user,
    -- Average pipeline runs per user this billing period
    -- Low average on free tier = users finding value quickly without hitting the cap
    -- High average on free tier = users hitting the paywall frequently (high intent)

    -- ─────────────────────────────────────────────────────────────────────
    -- DEAL BEHAVIOR METRICS — what are they saving?
    -- ─────────────────────────────────────────────────────────────────────
    SUM(saved_deals) AS total_saved_deals,
    -- Total portfolio saves across all users on this plan
    -- Pro users saving more deals = higher engagement with the platform's core feature

    AVG(avg_deal_max_units) AS avg_deal_max_units,
    -- Average of each user's average deal density
    -- Interpretation: are pro users targeting bigger/denser projects than free users?
    -- If pro avg_deal_max_units >> free avg_deal_max_units: pro users are more sophisticated
    -- This could inform the pro tier marketing copy ("for serious multifamily developers")

    -- ─────────────────────────────────────────────────────────────────────
    -- CONVERSION SIGNAL — how many free users are hitting the paywall?
    -- ─────────────────────────────────────────────────────────────────────
    COUNT(*) FILTER (WHERE is_at_quota) AS users_at_quota
    -- Count of free-tier users who've used all 5 monthly analyses
    -- These users have already found enough value to hit the limit
    -- They are the highest-probability conversion candidates for the pro plan
    -- Tracking this metric over time shows whether the 5-analysis limit is the right threshold:
    --   If users_at_quota/user_count is very high: paywall is too tight (increase limit or lower pro price)
    --   If users_at_quota/user_count is very low: paywall is too loose (reduce limit or add features)

FROM {{ ref('int_user_activity') }}
-- Pull from the intermediate model which already resolved the user_id JOIN
-- {{ ref() }} creates DAG dependency: int_user_activity runs before mart_usage
-- Which means: stg_subscriptions and stg_portfolio run before int_user_activity

GROUP BY plan
-- Collapse all users into 2 rows: 'free' and 'pro'
-- All COUNT/SUM/AVG aggregates apply within each plan tier
