# nightly_freshness.py — Cron schedule: 2 AM nightly freshness check
#
# WHAT THIS DOES: Triggers ingestion_job at 2:00 AM every night.
# ingestion_job runs municipality_freshness_asset which:
#   1. Reads mart_coverage.is_stale to find stale municipalities
#   2. Re-ingests only those (often zero — most nights are no-ops)
#
# WHY 2 AM? Zoning ordinance scraping is I/O heavy and slow.
# 2 AM is the lowest-traffic window for both Render (backend) and Municode (source).
# Running at 2 AM minimizes interference with user traffic.
#
# WHY NOT JUST USE THE SENSOR? The sensor (report_cache_sensor) handles dbt mart refresh.
# This schedule handles source data freshness (ordinance chunks).
# They're separate concerns:
#   Sensor: "new analyses came in → refresh the analytics layer"
#   Schedule: "it's been 30 days → refresh the source data layer"

from dagster import ScheduleDefinition
# ScheduleDefinition: simple cron-based schedule object
# No custom logic needed here — the smart logic lives in municipality_freshness_asset itself
# ScheduleDefinition just says "run this job at this time"


nightly_freshness_schedule = ScheduleDefinition(
    name="nightly_municipality_freshness",
    # Unique name for this schedule — appears in the Dagster UI Schedules tab
    # Click "Start" in the UI to enable it; it won't run until enabled
    job_name="ingestion_job",
    # Which job to trigger when the schedule fires
    # ingestion_job is defined in jobs.py — it runs municipality_freshness_asset
    cron_schedule="0 2 * * *",
    # Standard cron syntax:
    #   0    = minute 0 (on the hour)
    #   2    = hour 2 (2 AM)
    #   *    = every day of the month
    #   *    = every month
    #   *    = every day of the week
    # Translation: "At 02:00 AM, every day"
    # Cron is evaluated in UTC by default in Dagster
    # 2 AM UTC = 10 PM EST (winter) / 9 PM PDT (summer) — late enough for US market
    description=(
        "Nightly freshness check: queries mart_coverage for stale municipalities "
        "and re-ingests only those with data older than 30 days. "
        "Most nights: zero ingestion jobs fired (data is still fresh). "
        "Staleness threshold is defined in mart_coverage.sql — change it there."
        # Good descriptions explain WHAT the schedule does AND where to look to change behavior
        # "change it in mart_coverage.sql" = no magic numbers buried in Python
    ),
    # This description appears in the Dagster UI Schedules tab — useful for teammates
)
