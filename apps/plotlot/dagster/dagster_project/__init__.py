# __init__.py — The Dagster "code location" entry point
#
# This is THE file Dagster reads when it loads the dagster_project package.
# workspace.yaml points to this package, and Dagster looks for a variable named "defs"
# of type Definitions at the module level.
#
# The Definitions object is the container for EVERYTHING Dagster manages:
#   assets  → things that produce data (dbt models, ingestion runs)
#   sensors → poll external systems and trigger jobs when conditions are met
#   schedules → cron-based job triggers
#   jobs    → named subsets of the asset graph

from dagster import Definitions  # The container class that wires everything together

# Import each component from its module
# These imports trigger the Python files to be parsed and their decorators to register

from .assets.ingestion import municipality_freshness_asset
# The Python asset that:
#   1. Reads mart_coverage to find stale municipalities
#   2. Calls /admin/ingest for each stale one
#   3. Logs structured metadata to the Dagster UI
# "." prefix = relative import from within the dagster_project package

from .assets.dbt_assets import plotlot_dbt_assets
# The dbt-powered asset that wraps all 11 dbt models as Dagster assets
# It's a list (produced by @dbt_assets decorator) — we spread it with * below

from .sensors.report_cache_sensor import report_cache_sensor
# Polls report_cache every 5 minutes for new analyses
# Triggers dbt_refresh_job when new data appears (event-driven mart refresh)

from .schedules.nightly_freshness import nightly_freshness_schedule
# Cron schedule: 2:00 AM nightly → triggers ingestion_job
# Checks mart_coverage.is_stale and re-ingests only what's stale

from .jobs import ingestion_job, dbt_refresh_job
# ingestion_job: runs municipality_freshness_asset
# dbt_refresh_job: runs all dbt assets


# defs is the variable Dagster reads — MUST be named "defs" at module level
# workspace.yaml → dagster_project package → defs = this Definitions object
defs = Definitions(
    assets=[
        municipality_freshness_asset,  # The Python ingestion asset (1 asset)
        *plotlot_dbt_assets,  # The dbt model assets (11 assets, spread into the list)
        # * unpacks: [stg_analyses, stg_coverage, ..., mart_usage]
        # Total: 12 assets in the asset graph
    ],
    sensors=[
        report_cache_sensor,  # Event-driven: watches for new analyses
    ],
    schedules=[
        nightly_freshness_schedule,  # Cron-driven: 2am nightly freshness check
    ],
    jobs=[
        ingestion_job,  # Triggered by: nightly_freshness_schedule
        dbt_refresh_job,  # Triggered by: report_cache_sensor
    ],
)
