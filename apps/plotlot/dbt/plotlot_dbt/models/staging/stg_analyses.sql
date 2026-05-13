-- stg_analyses.sql — THE most important model in the project
-- "Modeling around upstream deficiencies" — this is the exact skill the Flow JD asks for
--
-- UPSTREAM DEFICIENCY: report_cache.report_json is an opaque JSON blob.
-- The FastAPI backend writes the entire ZoningReport as JSON for write flexibility.
-- This is pragmatic for an OLTP system but terrible for analytics — you can't GROUP BY,
-- filter, or aggregate on fields buried inside a JSON blob without unpacking them first.
--
-- THIS MODEL SOLVES THAT: We use PostgreSQL JSON operators to extract 15 typed columns.
-- Downstream models (marts, intermediate joins) can now query these as normal SQL columns.
--
-- The "modeling around upstream deficiency" framing is: we didn't fix the source —
-- we modeled around it in the analytics layer. This is standard practice.

{{ config(materialized='view') }}
-- 'view' materialization: dbt creates a SQL VIEW in the plotlot_dbt schema
-- Views have no storage cost and always reflect the latest data in report_cache
-- Good choice for staging — we want freshness, not speed (marts handle caching)

SELECT
    -- ─────────────────────────────────────────────────────────────────────
    -- IDENTITY COLUMNS — carry through from the source table
    -- ─────────────────────────────────────────────────────────────────────

    id,                       -- Source row UUID — keeps this row joinable to other systems

    address,                  -- Raw address as the user typed it (e.g. "123 Main St, Miami FL")
                              -- NOT normalized — used for display only, not as a join key

    address_normalized,       -- Lowercase, stripped version (e.g. "123 main st miami fl")
                              -- This IS the entity resolution key — same parcel, different input
                              -- formatting always resolves to the same normalized key

    created_at,               -- When this pipeline run completed and was cached
                              -- Used for freshness tracking in mart_quality (30-day trend)

    expires_at,               -- When this cache entry expires (created_at + 24h)
                              -- stg_analyses WHERE clause filters to active entries only

    hit_count,                -- How many times this cached result has been served
                              -- High hit_count = pipeline ran once, cost paid once, served many times

    -- ─────────────────────────────────────────────────────────────────────
    -- JSON UNPACKING — this is the "upstream deficiency" modeling
    --
    -- PostgreSQL JSON operators:
    --   report_json->>'field'        = extract TOP-LEVEL field as text
    --   report_json->'obj'->>'field' = extract NESTED field as text (two hops)
    --   ::type                       = cast the extracted text to the target type
    --
    -- Why text first, then cast? ->> always returns text regardless of the JSON value type.
    -- Casting after extraction is the standard pattern.
    -- ─────────────────────────────────────────────────────────────────────

    -- Top-level report metadata
    (report_json->>'municipality')::text        AS municipality,      -- e.g. "Miami Gardens"
    (report_json->>'county')::text              AS county,            -- e.g. "Miami-Dade"
    (report_json->>'zoning_district')::text     AS zoning_district,   -- e.g. "RM-25" — the zone code
    (report_json->>'confidence')::text          AS confidence_level,  -- "high", "medium", or "low"
                                                                      -- Reflects LLM extraction quality

    -- Density analysis — the core output of the pipeline
    -- report_json->'density_analysis' extracts the nested object as JSON
    -- then ->>'field' extracts a specific key from that nested object as text
    (report_json->'density_analysis'->>'max_units')::integer             AS max_units,
    -- max_units = the final answer: how many dwelling units fit on this parcel
    -- Integer because you can't build 42.7 units — we round down to the binding constraint

    (report_json->'density_analysis'->>'governing_constraint')::text     AS governing_constraint,
    -- Which of the 4 constraints bound the result?
    -- Values: "min_lot_area", "density", "far", or "buildable_envelope"
    -- This is the interview story: "the binding constraint determines the max units"

    (report_json->'density_analysis'->>'buildable_area_sqft')::float     AS buildable_area_sqft,
    -- Lot area minus setbacks — the actual ground area available for building footprint

    -- Property record — physical parcel data from ArcGIS
    (report_json->'property_record'->>'lot_size_sqft')::float            AS lot_size_sqft,
    -- Raw parcel size before setback deductions — NOT the same as buildable_area_sqft

    (report_json->'property_record'->>'market_value')::float             AS market_value,
    -- County-assessed market value — used to sanity-check pro forma pricing

    -- Zoning parameters — numeric dimensional standards extracted by the LLM
    -- These come from the zoning ordinance text via hybrid retrieval + structured extraction
    (report_json->'numeric_params'->>'max_density_units_per_acre')::float  AS max_density_uac,
    -- e.g. 25.0 for an RM-25 zone — the "density" constraint input

    (report_json->'numeric_params'->>'max_far')::float                     AS max_far,
    -- Floor area ratio — total building square footage ÷ lot area
    -- A 0.5 FAR on a 10,000 sqft lot = max 5,000 sqft of building

    (report_json->'numeric_params'->>'max_height_ft')::float               AS max_height_ft,
    -- Maximum building height in feet — feeds the "buildable_envelope" constraint

    (report_json->'numeric_params'->>'setback_front_ft')::float            AS setback_front_ft
    -- Front setback requirement — reduces lot depth available for building

FROM {{ source('plotlot', 'report_cache') }}
-- {{ source('plotlot', 'report_cache') }} resolves to "public"."report_cache" at runtime
-- dbt reads sources.yml to know that source 'plotlot', table 'report_cache' = public.report_cache

WHERE expires_at > NOW()
-- Only include active (non-expired) cache entries
-- Expired entries are stale pipeline runs from > 24h ago
-- Including them would skew the quality trend chart in mart_quality
