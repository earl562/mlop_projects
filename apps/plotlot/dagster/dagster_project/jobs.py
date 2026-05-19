# jobs.py — Named subsets of the asset graph that can be triggered independently
#
# A Dagster "job" is a selection of assets + the configuration for running them together.
# Jobs let you trigger PART of the asset graph, not always everything.
#
# Two jobs:
#   ingestion_job    → runs only municipality_freshness_asset (the Python ingestion asset)
#                      Triggered by: nightly_freshness_schedule (2am cron)
#                      Also runnable manually from the Dagster UI "Materialize" button
#
#   dbt_refresh_job  → runs all dbt assets (all 11 dbt models + tests)
#                      Triggered by: report_cache_sensor (event-driven, 5-min polling)
#                      Also runnable manually from the Dagster UI
#
# WHY SEPARATE JOBS? They have different triggers and different runtimes:
#   ingestion = slow (5-10 min per municipality, HTTP calls, scraping)
#   dbt refresh = fast (seconds to minutes, just SQL queries in Neon)
# Separating them means a new analysis doesn't have to wait for ingestion to finish
# before the marts get updated.

from dagster import define_asset_job, AssetSelection
# define_asset_job: creates a job from a selection of assets
# AssetSelection: fluent API to select assets by name, group, tag, etc.
#   AssetSelection.assets("name") → select one specific asset by key
#   AssetSelection.all()          → select every asset in the code location
#   selection_a - selection_b     → set subtraction (all assets EXCEPT selection_b)


ingestion_job = define_asset_job(
    name="ingestion_job",
    # Unique job name — referenced in:
    #   1. nightly_freshness_schedule (job_name="ingestion_job")
    #   2. Dagster UI "Jobs" tab (where you can trigger it manually)
    selection=AssetSelection.assets("municipality_freshness_asset"),
    # Select ONLY the municipality_freshness_asset (the Python ingestion asset)
    # AssetSelection.assets() takes the asset key, which is derived from the function name
    # The dbt assets (11 models) are NOT selected here — ingestion runs independently of dbt
    description=(
        "Nightly freshness check: reads mart_coverage, finds stale municipalities, "
        "re-ingests only those with data older than 30 days. "
        "Triggered by nightly_municipality_freshness schedule at 2am UTC."
    ),
)


dbt_refresh_job = define_asset_job(
    name="dbt_refresh_job",
    # Unique job name — referenced in:
    #   1. report_cache_sensor (job_name="dbt_refresh_job")
    #   2. Dagster UI "Jobs" tab
    selection=(AssetSelection.all() - AssetSelection.assets("municipality_freshness_asset")),
    # AssetSelection.all() = every asset in the code location (12 assets: 1 Python + 11 dbt)
    # Subtract the ingestion asset so dbt_refresh_job ONLY runs dbt models, not ingestion
    # Result: the 11 dbt model assets (stg_*, int_*, mart_*)
    #
    # WHY EXCLUDE ingestion? dbt refresh should be fast (triggered every 5 min by sensor).
    # Including ingestion would make every dbt refresh potentially wait for slow HTTP scraping.
    # Ingestion has its own job (ingestion_job) and its own schedule (2am cron).
    description=(
        "Runs all dbt models and tests: staging → intermediate → marts. "
        "Keeps analytics tables current after new analyses arrive. "
        "Triggered by report_cache_sensor when new analyses appear in report_cache."
    ),
)
