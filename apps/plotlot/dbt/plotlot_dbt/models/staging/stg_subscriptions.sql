-- stg_subscriptions.sql — Clean pass-through with computed business logic flags
--
-- WHAT THIS DOES: user_subscriptions is already clean normalized OLTP data.
-- No JSON blobs, no schema mismatch, no upstream deficiency to model around.
-- This staging model adds TWO computed boolean columns using CASE WHEN expressions:
--   is_pro       → True if plan = 'pro' (faster segmentation in mart_usage)
--   is_at_quota  → True if free user has hit the 5-analysis monthly cap
--
-- WHY COMPUTE HERE? These flags encode business rules (free tier cap = 5, pro = unlimited).
-- Computing them once in the staging layer means every downstream model gets them for free
-- without re-implementing the CASE WHEN logic. Single source of truth for business rules.
--
-- ENTITY RESOLUTION CONTEXT: user_id here is the primary key.
-- The same user_id appears as a foreign key in portfolio_entries.
-- int_user_activity joins stg_subscriptions + stg_portfolio on user_id
-- to reconcile billing identity with deal behavior — the "household matching" pattern.

{{ config(materialized='view') }}

SELECT
    user_id,            -- Clerk UUID — PRIMARY KEY for user identity
                        -- This is the "household key" that joins to portfolio_entries

    plan,               -- Raw plan value: 'free' or 'pro'
                        -- Tested in sources.yml with accepted_values to prevent unexpected values

    analyses_used,      -- How many pipeline runs this user has made in the current billing period
                        -- Incremented by the FastAPI billing middleware after each successful /analyze call

    period_start,       -- Billing period start date (set by Stripe invoice.paid webhook)

    period_end,         -- Billing period end date

    created_at,         -- When this user first signed up — user cohort analysis

    -- ─────────────────────────────────────────────────────────────────────
    -- COMPUTED BUSINESS LOGIC FLAGS
    -- CASE WHEN expressions that encode business rules as boolean columns
    -- ─────────────────────────────────────────────────────────────────────

    CASE
        WHEN plan = 'pro' THEN true   -- Pro plan users: full access, no monthly cap
        ELSE false                    -- Free plan users: capped at 5 analyses per period
    END AS is_pro,
    -- Simple derived flag from plan column
    -- Downstream models use is_pro for segmentation instead of re-writing the CASE WHEN

    CASE
        WHEN plan = 'free' AND analyses_used >= 5 THEN true
        -- Free tier monthly cap is 5 analyses (hardcoded in FastAPI billing middleware)
        -- When analyses_used reaches 5, the API returns 402 Payment Required
        -- These users are conversion candidates — high intent, hitting the paywall
        ELSE false                    -- Pro users never hit quota; free users under 5 analyses
    END AS is_at_quota
    -- mart_usage uses COUNT(*) FILTER (WHERE is_at_quota) to show conversion pressure

FROM {{ source('plotlot', 'user_subscriptions') }}
-- {{ source('plotlot', 'user_subscriptions') }} resolves to "public"."user_subscriptions"
-- No WHERE clause — include ALL users (active and inactive)
-- Inactive users (no recent analyses) still matter for cohort/churn analysis
