# ingestion.py — The core business logic asset: conditional municipality re-ingestion
#
# WHAT THIS DOES:
#   1. Connects directly to Neon PostgreSQL (reads the dbt mart, not the raw table)
#   2. Queries mart_coverage to find municipalities where is_stale = true OR is_gap = true
#   3. For each stale municipality, calls the existing PlotLot /admin/ingest API
#   4. Logs structured metadata (which municipalities, how many chunks added) to the Dagster UI
#
# KEY DESIGN CHOICES:
#   - Reads FROM the dbt mart (plotlot_dbt.mart_coverage), NOT from raw ordinance_chunks
#     This proves the dbt layer is production-useful, not just a demo layer
#   - Calls the EXISTING /admin/ingest API (apps/plotlot/src/plotlot/pipeline/ingest.py)
#     No code duplication — Dagster orchestrates PlotLot's own ingestion pipeline
#   - Most nights: ZERO municipalities are stale → asset materializes cleanly, does nothing
#     This is intentional — a well-maintained system has low churn
#
# INTERVIEW FRAMING: "Dagster reads from the dbt mart to make orchestration decisions.
# The smart logic lives in the mart (is_stale, is_gap flags), not in the orchestrator.
# This separation means I can change the staleness threshold in one SQL file."

import asyncio  # Python stdlib: lets us run async functions from this synchronous Dagster asset
import asyncpg  # Direct asyncpg driver for PostgreSQL — same driver PlotLot FastAPI uses
import os  # Python stdlib: read environment variables (DATABASE_URL, PLOTLOT_API_URL)

from dagster import asset, AssetExecutionContext
# asset: decorator that turns a Python function into a Dagster software-defined asset
# AssetExecutionContext: typed context object passed to every asset — provides logging + metadata


@asset(
    # Dagster asset decorator — registers this function as a Dagster asset named "municipality_freshness_asset"
    # The name comes from the function name (snake_case → asset key)
    description=(
        "Checks all ingested municipalities for stale ordinance data (>30 days old). "
        "Fires ingestion only for stale municipalities. Most nights: zero jobs fired."
        # This description appears in the Dagster UI asset catalog
        # Good descriptions help teammates understand what the asset does without reading code
    ),
)
def municipality_freshness_asset(context: AssetExecutionContext):
    """
    Reads mart_coverage (the dbt mart) to find stale municipalities.
    Calls the existing PlotLot /admin/ingest endpoint for each one.
    Logs structured metadata to the Dagster UI.
    """
    import httpx
    # Lazy import of httpx inside the function body
    # Keeps the module-level namespace clean — httpx only needed when this asset actually runs
    # Standard pattern in Dagster assets to avoid import-time side effects

    # ─────────────────────────────────────────────────────────────────────
    # Get the database connection string from the environment
    # ─────────────────────────────────────────────────────────────────────
    db_url = os.environ["DATABASE_URL"].replace(
        "postgresql+asyncpg://",  # SQLAlchemy async driver prefix (used by PlotLot's ORM)
        "postgresql://",  # Standard asyncpg connection string prefix
    )
    # asyncpg uses "postgresql://" not "postgresql+asyncpg://"
    # PlotLot's DATABASE_URL uses the SQLAlchemy prefix because it uses async SQLAlchemy
    # We strip it here because this asset uses asyncpg directly (not SQLAlchemy)

    async def check_and_ingest():
        """
        Async inner function that does the actual database query and HTTP calls.
        Defined as async because asyncpg requires an async context.
        Called via asyncio.run() at the bottom of this function.
        """

        # ─────────────────────────────────────────────────────────────────
        # Open a direct asyncpg connection to Neon
        # ─────────────────────────────────────────────────────────────────
        conn = await asyncpg.connect(
            db_url,  # The Neon connection string (postgresql://user:pass@host/db)
            ssl="require",  # Neon requires SSL on all connections — this enables it
        )
        # asyncpg.connect() is lighter than SQLAlchemy — no ORM overhead, just a raw connection
        # Good choice for simple admin queries like this one

        # ─────────────────────────────────────────────────────────────────
        # Query mart_coverage to find municipalities needing re-ingestion
        # ─────────────────────────────────────────────────────────────────
        stale = await conn.fetch(
            """
            SELECT municipality
            FROM plotlot_dbt.mart_coverage
            WHERE is_stale = true OR is_gap = true
            ORDER BY chunk_count ASC
            """
            # plotlot_dbt.mart_coverage = dbt schema + mart table name
            # is_stale = true  → data older than 30 days (set by CASE WHEN in mart_coverage.sql)
            # is_gap = true    → zero chunks ever ingested (new municipality discovered)
            # ORDER BY chunk_count ASC → smallest coverage first
            #   Because municipalities with fewer chunks are more urgent:
            #   Fort Lauderdale (136 chunks) is more broken than Miami Gardens (3,561)
        )

        await conn.close()
        # Always close the connection when done
        # asyncpg doesn't use context managers by default — explicit close is required
        # Leaving connections open would exhaust Neon's free tier connection limit (10 concurrent)

        results = []  # Collect results for structured metadata logging to the Dagster UI

        # ─────────────────────────────────────────────────────────────────
        # Call PlotLot's /admin/ingest API for each stale municipality
        # ─────────────────────────────────────────────────────────────────
        api_base = os.environ.get(
            "PLOTLOT_API_URL",  # Production: set to https://your-render-service.onrender.com
            "http://localhost:8000",  # Local dev default — assumes backend is running locally
        )
        # PLOTLOT_API_URL is set in the Dagster dev environment (or Dagster Cloud secrets)
        # os.environ.get with a default = won't crash if the env var is missing (local dev friendly)

        for row in stale:
            # row is an asyncpg Record object — access fields like a dict
            muni = row["municipality"]  # Extract the municipality name string

            context.log.info(f"Stale municipality detected: {muni} — triggering ingestion")
            # context.log.info() writes a structured log line to the Dagster UI
            # Visible in the "Events" tab of the asset materialization run
            # Do NOT use print() — Dagster captures context.log, not stdout

            async with httpx.AsyncClient(timeout=300) as client:
                # httpx.AsyncClient: async HTTP session
                # timeout=300: allow 5 minutes per ingestion call
                #   Ingestion can take 2-5 minutes (scrape + embed + upsert 1,000+ chunks)
                #   Default httpx timeout is 5 seconds — would always fail for ingestion
                # async with: ensures the client is properly closed after the request completes

                resp = await client.post(
                    f"{api_base}/admin/ingest",
                    # The existing PlotLot endpoint in routes.py
                    # This is NOT a new endpoint — Dagster calls PlotLot's own API
                    json={"municipality": muni},
                    # JSON body — matches the request model for /admin/ingest
                    # PlotLot's ingest_municipiality() function handles the rest
                )

                result = resp.json()
                # Returns: { municipality, chunks_added, chunks_updated, errors, duration_s }
                # These are the output fields from apps/plotlot/src/plotlot/pipeline/ingest.py

                results.append({"municipality": muni, **result})
                # Merge: { municipality: "Fort Lauderdale", chunks_added: 45, ... }
                # ** unpacks the result dict into keyword arguments for dict creation

                context.log.info(f"Ingestion complete for {muni}: {result}")
                # Log the completion with the result payload — visible in Dagster UI Events tab

        return results
        # Return the list of ingestion results — used for metadata below

    # ─────────────────────────────────────────────────────────────────────
    # Bridge async → sync: run the async function from this synchronous Dagster asset
    # ─────────────────────────────────────────────────────────────────────
    results = asyncio.run(check_and_ingest())
    # asyncio.run() is the standard bridge pattern:
    #   - Creates a new event loop
    #   - Runs the coroutine to completion
    #   - Returns the result
    # Dagster assets are synchronous by default (they're just Python functions)
    # asyncio.run() lets us use async libraries (asyncpg, httpx) inside them

    # ─────────────────────────────────────────────────────────────────────
    # Attach structured metadata to this asset materialization in the Dagster UI
    # ─────────────────────────────────────────────────────────────────────
    context.add_output_metadata(
        {
            "stale_count": len(results),
            # How many municipalities were re-ingested this run
            # 0 on most nights (normal!) — means the system is healthy and current
            "municipalities_ingested": [r["municipality"] for r in results],
            # List of municipality names that were re-ingested
            # Visible in the Dagster UI "Metadata" tab for this materialization
            # Click any asset materialization → "Events" → find the Output event → see this metadata
        }
    )
    # add_output_metadata() stores arbitrary key-value data alongside the materialization event
    # It's how you attach "why did this run do what it did" context to the Dagster run history

    return results
    # Return value is stored as the asset's output in Dagster's event log
    # Not strictly required for this asset (we care about side effects: ingestion calls)
    # but useful for the sensor to potentially inspect the results
