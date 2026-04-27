"""API route handlers for PlotLot.

POST /api/v1/analyze — synchronous analysis (await pipeline, return JSON)
POST /api/v1/analyze/stream — SSE streaming with real-time pipeline progress
"""

import asyncio
import json
import logging
from dataclasses import asdict

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from plotlot.api.billing import check_analysis_limit
from plotlot.api.cache import cache_report, get_cached_report
from plotlot.api.schemas import AnalyzeRequest, ErrorResponse, ZoningReportResponse
from plotlot.pipeline.lookup import lookup_address
from plotlot.retrieval.geocode import geocode_address
from plotlot.retrieval.property import lookup_property
from plotlot.retrieval.search import hybrid_search
from plotlot.pipeline.calculator import calculate_max_units, parse_lot_dimensions
from plotlot.pipeline.lookup import _agentic_analysis, PIPELINE_VERSION
from plotlot.observability.tracing import start_run, log_params, log_metrics, set_tag
from plotlot.observability.prompts import log_prompt_to_run
from plotlot.storage.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["analysis"])

PIPELINE_TIMEOUT = 120  # seconds


def _apply_confidence_metadata(response: ZoningReportResponse) -> None:
    """Populate confidence warning and suggested next steps (Klarna pattern)."""
    if response.confidence == "low":
        response.confidence_warning = (
            "Low confidence: Limited zoning data was found for this address. "
            "Results may be incomplete or estimated."
        )
        response.suggested_next_steps = [
            "Verify zoning with your local municipality",
            "Contact a licensed zoning attorney",
            "Check the county property appraiser website",
        ]
    elif response.confidence == "medium":
        response.confidence_warning = (
            "Medium confidence: Some zoning parameters could not be verified. "
            "Key figures should be confirmed with the municipality."
        )
        response.suggested_next_steps = [
            "Confirm density and setback values with the municipality",
        ]


def _describe_pipeline_error(exc: Exception) -> tuple[str, str]:
    """Map low-level pipeline failures into user-facing, actionable errors."""
    message = str(exc)
    lower = message.lower()
    if (
        "connection refused" in lower
        or "connect call failed" in lower
        or "errno 61" in lower
        or "database" in lower
    ):
        return (
            "Analysis is temporarily unavailable because the data backend is offline. "
            "Please try again shortly.",
            "backend_unavailable",
        )
    return (message, "pipeline_error")


@router.post(
    "/analyze",
    response_model=ZoningReportResponse,
    responses={
        402: {"description": "Free tier usage limit exceeded"},
        422: {"model": ErrorResponse, "description": "Geocoding failed or invalid input"},
        502: {"model": ErrorResponse, "description": "Pipeline error"},
        504: {"model": ErrorResponse, "description": "Pipeline timeout"},
    },
)
async def analyze(request: AnalyzeRequest, _: None = Depends(check_analysis_limit)):
    """Run the full zoning analysis pipeline for an address."""
    try:
        report = await asyncio.wait_for(
            lookup_address(request.address),
            timeout=PIPELINE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Pipeline timed out after {PIPELINE_TIMEOUT}s",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("Pipeline error for address: %s", request.address)
        detail = _describe_pipeline_error(e)[0]
        raise HTTPException(status_code=502, detail=detail)

    if report is None:
        raise HTTPException(
            status_code=422,
            detail=f"Could not geocode address: {request.address}",
        )

    response = ZoningReportResponse(**asdict(report))
    _apply_confidence_metadata(response)
    return response


def _sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/analyze/stream")
async def analyze_stream(request: AnalyzeRequest):
    """Stream zoning analysis with real-time pipeline progress via SSE."""

    async def event_generator():
        try:
            # Step 1: Geocode
            yield _sse_event("status", {"step": "geocoding", "message": "Resolving address..."})
            geo = await geocode_address(request.address)
            if not geo:
                yield _sse_event(
                    "error",
                    {
                        "detail": f"Could not geocode address: {request.address}",
                        "error_type": "geocoding_failed",
                    },
                )
                return

            municipality = geo["municipality"]
            county = geo["county"]
            lat = geo.get("lat")
            lng = geo.get("lng")

            accuracy_score = geo.get("accuracy")
            if isinstance(accuracy_score, (int, float)) and accuracy_score < 0.8:
                yield _sse_event(
                    "error",
                    {
                        "detail": (
                            f"Could not confidently locate this address "
                            f"(geocoding accuracy: {accuracy_score}). Please check the address."
                        ),
                        "error_type": "low_accuracy",
                    },
                )
                return

            yield _sse_event(
                "status",
                {
                    "step": "geocoding",
                    "message": f"Found: {municipality}, {county} County",
                    "complete": True,
                },
            )

            # Cache check — skip full pipeline for repeated addresses
            try:
                cached = await get_cached_report(request.address)
                if cached:
                    logger.info("Cache HIT for %s", request.address)
                    yield _sse_event(
                        "status",
                        {
                            "step": "cache_hit",
                            "message": "Using cached analysis",
                        },
                    )
                    yield _sse_event("result", cached)
                    return
            except Exception as exc:
                logger.warning("Cache lookup failed (proceeding without): %s", exc)

            # Step 2: Property lookup (with timeout + heartbeat)
            yield _sse_event(
                "status",
                {
                    "step": "property",
                    "message": "Fetching property record...",
                },
            )
            prop_task = asyncio.create_task(
                lookup_property(request.address, county, lat=lat, lng=lng)
            )
            prop_record = None
            for _tick in range(4):  # 4 × 10s = 40s max
                done, _ = await asyncio.wait({prop_task}, timeout=10)
                if done:
                    try:
                        prop_record = prop_task.result()
                    except Exception as e:
                        logger.warning("Property lookup failed: %s", e)
                    break
                # Heartbeat keeps SSE connection alive through Render proxy
                yield _sse_event(
                    "status",
                    {
                        "step": "property",
                        "message": "Fetching property record...",
                    },
                )
            else:
                # Timed out — cancel and proceed without property record
                prop_task.cancel()
                logger.warning("Property lookup timed out for: %s", request.address)

            if prop_record and prop_record.municipality:
                pa_muni = prop_record.municipality.strip().title()
                if pa_muni and len(pa_muni) > 3 and pa_muni.lower() != municipality.lower():
                    municipality = pa_muni
                    geo["municipality"] = municipality

            property_status: dict = {
                "step": "property",
                "message": f"Lot: {prop_record.lot_size_sqft:,.0f} sqft"
                if prop_record
                else "No record found",
                "complete": True,
            }
            if prop_record:
                property_status["resolved_address"] = (
                    f"{prop_record.address}, {prop_record.municipality}"
                    if prop_record.address
                    else geo.get("formatted_address", request.address)
                )
                property_status["folio"] = prop_record.folio
                property_status["lot_sqft"] = prop_record.lot_size_sqft
            else:
                property_status["resolved_address"] = geo.get("formatted_address", request.address)
            yield _sse_event("status", property_status)

            # Step 3: Hybrid search
            yield _sse_event(
                "status",
                {
                    "step": "search",
                    "message": "Searching zoning ordinances...",
                },
            )
            search_query = (
                prop_record.zoning_code if prop_record and prop_record.zoning_code else municipality
            )
            session = await get_session()
            try:
                search_results = await hybrid_search(session, municipality, search_query, limit=15)
            finally:
                await session.close()

            yield _sse_event(
                "status",
                {
                    "step": "search",
                    "message": f"Found {len(search_results)} relevant sections",
                    "complete": True,
                },
            )

            # Step 4: Agentic LLM analysis (wrapped in MLflow run for tracing)
            # Render's proxy has a 30s idle timeout — send heartbeats to keep alive
            yield _sse_event(
                "status",
                {
                    "step": "analysis",
                    "message": "AI analyzing zoning code...",
                },
            )

            with start_run(run_name=f"stream_{request.address[:30]}"):
                log_params(
                    {
                        "address": request.address,
                        "pipeline_version": PIPELINE_VERSION,
                        "endpoint": "stream",
                        "county": county,
                        "municipality": municipality,
                        "has_property_record": str(bool(prop_record)),
                        "search_result_count": str(len(search_results)),
                    }
                )
                log_prompt_to_run("analysis")

                analysis_task = asyncio.create_task(
                    _agentic_analysis(
                        address=request.address,
                        geo=geo,
                        prop_record=prop_record,
                        search_results=search_results,
                        municipality=municipality,
                        county=county,
                    )
                )

                report = None
                for _tick in range(6):  # 6 × 15s = 90s max
                    done, _ = await asyncio.wait({analysis_task}, timeout=15)
                    if done:
                        try:
                            report = analysis_task.result()
                        except Exception as e:
                            logger.error("Analysis task failed: %s", e)
                        break
                    # Heartbeat keeps SSE connection alive through Render proxy
                    yield _sse_event(
                        "status",
                        {
                            "step": "analysis",
                            "message": "AI analyzing zoning code...",
                        },
                    )

                if report is None:
                    if not analysis_task.done():
                        analysis_task.cancel()
                    logger.error("LLM analysis timed out for: %s", request.address)
                    from plotlot.pipeline.lookup import _build_fallback_report

                    report = _build_fallback_report(
                        request.address,
                        geo,
                        prop_record,
                        [f"{r.section} — {r.section_title}" for r in search_results if r.section],
                        search_results,
                    )

                # Log analysis metrics inside the MLflow run
                confidence_map = {"high": 1.0, "medium": 0.66, "low": 0.33}
                log_metrics(
                    {
                        "confidence_score": confidence_map.get(report.confidence, 0.0),
                        "source_count": float(len(report.sources)),
                        "has_numeric_params": 1.0 if report.numeric_params else 0.0,
                    }
                )
                set_tag("status", "success" if report.confidence != "low" else "low_confidence")

            # Thinking transparency: stream what the LLM found
            thinking_details = []
            if report.zoning_district:
                thinking_details.append(f"Identified zoning district: {report.zoning_district}")
            if report.numeric_params:
                np = report.numeric_params
                if np.max_density_units_per_acre:
                    thinking_details.append(f"Density: {np.max_density_units_per_acre} units/acre")
                if np.max_height_ft:
                    thinking_details.append(f"Height limit: {np.max_height_ft} ft")
                if np.setback_front_ft:
                    thinking_details.append(
                        f"Setbacks: F={np.setback_front_ft}' S={np.setback_side_ft}' R={np.setback_rear_ft}'"
                    )
                if np.far:
                    thinking_details.append(f"FAR: {np.far}")
            if thinking_details:
                yield _sse_event(
                    "thinking",
                    {
                        "step": "analysis",
                        "thoughts": thinking_details,
                    },
                )

            yield _sse_event(
                "status",
                {
                    "step": "analysis",
                    "message": f"Zoning: {report.zoning_district} — {report.zoning_description}",
                    "complete": True,
                },
            )

            # Step 5: Density calculation
            if "calculation" not in request.skip_steps and (
                report.numeric_params
                and report.property_record
                and report.property_record.lot_size_sqft > 0
            ):
                yield _sse_event(
                    "status",
                    {
                        "step": "calculation",
                        "message": "Computing max density...",
                    },
                )
                lot_width, lot_depth = parse_lot_dimensions(
                    report.property_record.lot_dimensions or "",
                )
                report.density_analysis = calculate_max_units(
                    lot_size_sqft=report.property_record.lot_size_sqft,
                    params=report.numeric_params,
                    lot_width_ft=lot_width,
                    lot_depth_ft=lot_depth,
                )
                yield _sse_event(
                    "status",
                    {
                        "step": "calculation",
                        "message": f"Max units: {report.density_analysis.max_units} ({report.density_analysis.governing_constraint})",
                        "complete": True,
                    },
                )
            elif "calculation" in request.skip_steps:
                yield _sse_event(
                    "status",
                    {"step": "calculation", "message": "Skipped", "complete": True},
                )

            # Step 6: Comparable sales (non-blocking, skippable)
            if (
                "comps" not in request.skip_steps
                and report.property_record
                and report.property_record.lat
            ):
                yield _sse_event(
                    "status",
                    {
                        "step": "comps",
                        "message": "Searching comparable sales...",
                    },
                )
                try:
                    from plotlot.pipeline.comps import find_comparables

                    state = geo.get("state", "FL")
                    comp_result = await asyncio.wait_for(
                        find_comparables(report.property_record, state=state),
                        timeout=30,
                    )
                    report.comp_analysis = comp_result
                    comp_msg = (
                        f"Found {len(comp_result.comparables)} comps"
                        if comp_result.comparables
                        else "No comparable sales found"
                    )
                    yield _sse_event(
                        "status",
                        {
                            "step": "comps",
                            "message": comp_msg,
                            "complete": True,
                        },
                    )
                except Exception as e:
                    logger.warning("Comp analysis failed (non-blocking): %s", e)
                    yield _sse_event(
                        "status",
                        {
                            "step": "comps",
                            "message": "Comp search unavailable",
                            "complete": True,
                        },
                    )
            elif "comps" in request.skip_steps:
                yield _sse_event(
                    "status",
                    {"step": "comps", "message": "Skipped", "complete": True},
                )

            # Step 7: Land pro forma (skippable)
            if (
                "proforma" not in request.skip_steps
                and report.density_analysis
                and report.density_analysis.max_units > 0
            ):
                yield _sse_event(
                    "status",
                    {
                        "step": "proforma",
                        "message": "Calculating land pro forma...",
                    },
                )
                try:
                    from plotlot.pipeline.proforma import calculate_land_pro_forma

                    report.pro_forma = calculate_land_pro_forma(
                        density=report.density_analysis,
                        comps=report.comp_analysis,
                    )
                    pf_msg = (
                        f"Max offer: ${report.pro_forma.max_land_price:,.0f}"
                        if report.pro_forma.max_land_price > 0
                        else "Pro forma calculated (ADV needed for offer price)"
                    )
                    yield _sse_event(
                        "status",
                        {
                            "step": "proforma",
                            "message": pf_msg,
                            "complete": True,
                        },
                    )
                except Exception as e:
                    logger.warning("Pro forma failed (non-blocking): %s", e)
            elif "proforma" in request.skip_steps:
                yield _sse_event(
                    "status",
                    {"step": "proforma", "message": "Skipped", "complete": True},
                )

            # Final result
            report_dict = asdict(report)
            yield _sse_event("result", report_dict)

            # Contextual suggestions based on deal type
            deal_suggestions: dict[str, list[str]] = {
                "land_deal": [
                    "Generate an LOI for this property",
                    "Run a detailed pro forma analysis",
                    "Find comparable sales nearby",
                ],
                "wholesale": [
                    "Calculate the MAO for this deal",
                    "Generate an assignment contract",
                    "Find comparable sales nearby",
                ],
                "creative_finance": [
                    "Analyze existing mortgage terms",
                    "Calculate monthly cash flow",
                    "Generate a deal summary",
                ],
                "hybrid": [
                    "Compare land deal vs creative finance",
                    "Generate a deal summary",
                    "Run a detailed pro forma analysis",
                ],
            }
            suggestions = deal_suggestions.get(request.deal_type, deal_suggestions["land_deal"])
            yield _sse_event(
                "suggestions", {"suggestions": suggestions, "deal_type": request.deal_type}
            )

            # Cache the result for future lookups
            try:
                await cache_report(request.address, report_dict)
                logger.info("Cached report for %s", request.address)
            except Exception as exc:
                logger.warning("Cache write failed: %s", exc)

        except Exception as e:
            logger.exception("Stream pipeline error for: %s", request.address)
            detail, error_type = _describe_pipeline_error(e)
            yield _sse_event(
                "error",
                {
                    "detail": detail,
                    "error_type": error_type,
                },
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Admin endpoints — data management
# ---------------------------------------------------------------------------


@router.get("/admin/chunks/stats")
async def chunk_stats():
    """Show ordinance chunk counts per municipality."""
    from sqlalchemy import func, select
    from plotlot.storage.models import OrdinanceChunk

    session = await get_session()
    try:
        result = await session.execute(
            select(
                OrdinanceChunk.municipality,
                OrdinanceChunk.county,
                func.count().label("chunks"),
            )
            .group_by(OrdinanceChunk.municipality, OrdinanceChunk.county)
            .order_by(func.count().desc())
        )
        rows = result.fetchall()
        total = sum(r.chunks for r in rows)
        return {
            "total_chunks": total,
            "municipalities": len(rows),
            "breakdown": [
                {"municipality": r.municipality, "county": r.county, "chunks": r.chunks}
                for r in rows
            ],
        }
    finally:
        await session.close()


# In-memory ingestion status tracker
_ingest_status: dict[str, dict] = {}


async def _run_ingestion(municipality_key: str, delete_existing: bool) -> None:
    """Background ingestion task."""
    from plotlot.pipeline.ingest import ingest_municipality, _resolve_config

    _ingest_status[municipality_key] = {"status": "running", "step": "initializing"}
    try:
        if delete_existing:
            from sqlalchemy import delete as sql_delete
            from plotlot.storage.models import OrdinanceChunk

            _ingest_status[municipality_key]["step"] = "deleting_existing"
            config = await _resolve_config(municipality_key)
            muni_name = config.municipality
            session = await get_session()
            try:
                result = await session.execute(
                    sql_delete(OrdinanceChunk).where(
                        OrdinanceChunk.municipality.ilike(f"%{muni_name}%")
                    )
                )
                await session.commit()
                deleted = result.rowcount  # type: ignore[attr-defined]
                logger.info("Deleted %d existing chunks for %s", deleted, muni_name)
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

        _ingest_status[municipality_key]["step"] = "scraping_and_embedding"
        count = await ingest_municipality(municipality_key)
        _ingest_status[municipality_key] = {
            "status": "complete",
            "chunks_stored": count,
        }
        logger.info("Ingestion complete for %s: %d chunks", municipality_key, count)

    except Exception as e:
        logger.exception("Background ingestion failed for: %s", municipality_key)
        _ingest_status[municipality_key] = {
            "status": "failed",
            "error": str(e),
        }


@router.post("/admin/ingest")
async def ingest_municipality_endpoint(
    municipality_key: str,
    background_tasks: BackgroundTasks,
    delete_existing: bool = False,
):
    """Start ingestion for a municipality (runs in background).

    Runs the full pipeline: discover → scrape → chunk → embed → store.
    Returns immediately. Poll GET /admin/ingest/status?key=X to check progress.
    """
    # Check if already running
    existing = _ingest_status.get(municipality_key, {})
    if existing.get("status") == "running":
        return {
            "municipality_key": municipality_key,
            "status": "already_running",
            "step": existing.get("step"),
        }

    # Ensure DB is initialized before starting the background task
    from plotlot.storage.db import init_db

    await init_db()

    background_tasks.add_task(_run_ingestion, municipality_key, delete_existing)
    _ingest_status[municipality_key] = {"status": "queued"}

    return {
        "municipality_key": municipality_key,
        "status": "started",
        "message": "Ingestion started in background. Poll /admin/ingest/status for progress.",
    }


@router.get("/admin/ingest/status")
async def ingest_status(key: str | None = None):
    """Check ingestion status for a municipality or all active ingestions."""
    if key:
        status = _ingest_status.get(key, {"status": "not_found"})
        return {"municipality_key": key, **status}
    return {"ingestions": dict(_ingest_status)}


# Batch ingestion status tracker
_batch_status: dict = {}


async def _run_batch_ingestion(skip_existing: bool) -> None:
    """Background task: ingest all discoverable municipalities sequentially.

    Processes one municipality at a time to stay within Render's 512MB RAM.
    Skips municipalities that already have chunks in the DB when skip_existing=True.
    """
    from plotlot.pipeline.ingest import ingest_municipality, _resolve_all_configs
    from sqlalchemy import func, select
    from plotlot.storage.models import OrdinanceChunk

    _batch_status["status"] = "discovering"
    _batch_status["step"] = "running auto-discovery"

    try:
        configs = await _resolve_all_configs()
        total = len(configs)
        _batch_status["total"] = total
        _batch_status["discovered_keys"] = list(configs.keys())
        logger.info("Batch ingestion: discovered %d municipalities", total)

        # Check which municipalities already have data
        if skip_existing:
            _batch_status["step"] = "checking existing data"
            session = await get_session()
            try:
                result = await session.execute(
                    select(
                        OrdinanceChunk.municipality,
                        func.count().label("chunks"),
                    ).group_by(OrdinanceChunk.municipality)
                )
                existing = {row.municipality.lower(): row.chunks for row in result.fetchall()}
            finally:
                await session.close()
            logger.info("Existing data: %d municipalities with chunks", len(existing))
        else:
            existing = {}

        completed = 0
        failed = 0
        skipped = 0
        results: dict[str, int | str] = {}

        _batch_status["status"] = "running"

        for i, (key, config) in enumerate(configs.items(), 1):
            # Check if this municipality already has data
            if skip_existing and config.municipality.lower() in existing:
                chunk_count = existing[config.municipality.lower()]
                logger.info(
                    "Skipping %s (%d/%d) — already has %d chunks",
                    config.municipality,
                    i,
                    total,
                    chunk_count,
                )
                results[key] = f"skipped ({chunk_count} chunks exist)"
                skipped += 1
                _batch_status.update(
                    {
                        "current": key,
                        "current_name": config.municipality,
                        "progress": f"{i}/{total}",
                        "completed": completed,
                        "failed": failed,
                        "skipped": skipped,
                    }
                )
                continue

            _batch_status.update(
                {
                    "current": key,
                    "current_name": config.municipality,
                    "step": f"ingesting {config.municipality}",
                    "progress": f"{i}/{total}",
                    "completed": completed,
                    "failed": failed,
                    "skipped": skipped,
                }
            )
            _ingest_status[key] = {"status": "running", "step": "scraping_and_embedding"}

            try:
                count = await ingest_municipality(key)
                results[key] = count
                completed += 1
                _ingest_status[key] = {"status": "complete", "chunks_stored": count}
                logger.info(
                    "Batch: %s complete (%d chunks) — %d/%d done",
                    config.municipality,
                    count,
                    i,
                    total,
                )
            except Exception as e:
                logger.error("Batch: %s failed: %s", config.municipality, e)
                results[key] = f"failed: {str(e)[:100]}"
                failed += 1
                _ingest_status[key] = {"status": "failed", "error": str(e)[:200]}

            await asyncio.sleep(0)  # yield between municipalities for user requests

        total_chunks = sum(v for v in results.values() if isinstance(v, int))
        _batch_status.update(
            {
                "status": "complete",
                "step": "done",
                "total_chunks": total_chunks,
                "completed": completed,
                "failed": failed,
                "skipped": skipped,
                "results": results,
            }
        )
        logger.info(
            "Batch ingestion complete: %d chunks, %d success, %d failed, %d skipped",
            total_chunks,
            completed,
            failed,
            skipped,
        )

    except Exception as e:
        logger.exception("Batch ingestion crashed")
        _batch_status.update(
            {
                "status": "failed",
                "error": str(e),
            }
        )


@router.post("/admin/ingest/batch")
async def ingest_batch(
    background_tasks: BackgroundTasks,
    skip_existing: bool = True,
):
    """Start batch ingestion of ALL discoverable municipalities.

    Runs auto-discovery, then ingests each municipality sequentially
    (one at a time to manage memory on Render's 512MB free tier).

    Args:
        skip_existing: Skip municipalities that already have chunks in DB (default: True).

    Returns immediately. Poll GET /admin/ingest/status to check progress.
    """
    if _batch_status.get("status") == "running":
        return {
            "status": "already_running",
            "progress": _batch_status.get("progress"),
            "current": _batch_status.get("current_name"),
        }

    from plotlot.storage.db import init_db

    await init_db()

    background_tasks.add_task(_run_batch_ingestion, skip_existing)
    _batch_status.clear()
    _batch_status["status"] = "queued"

    return {
        "status": "started",
        "message": "Batch ingestion started. Poll /admin/ingest/status to check progress.",
        "skip_existing": skip_existing,
    }


@router.get("/admin/ingest/batch/status")
async def batch_status():
    """Check batch ingestion progress."""
    return dict(_batch_status)


@router.get("/admin/data-quality")
async def data_quality():
    """Data quality dashboard for ordinance coverage.

    Primary contract is the legacy municipality summary used by tests and local
    tooling. The response also includes a normalized `coverage` field so newer
    dashboards can consume the same payload.
    """
    from sqlalchemy import text

    def _serialize_dt(value):
        return value.isoformat() if hasattr(value, "isoformat") else value

    session = await get_session()
    try:
        result = await session.execute(
            text("""
                SELECT
                    municipality,
                    county,
                    COUNT(*) AS chunk_count,
                    COUNT(DISTINCT municode_node_id) AS section_count,
                    MIN(created_at) AS first_ingested,
                    MAX(created_at) AS last_ingested,
                    AVG(LENGTH(chunk_text)) AS avg_chunk_length,
                    MIN(LENGTH(chunk_text)) AS min_chunk_length,
                    MAX(LENGTH(chunk_text)) AS max_chunk_length
                FROM ordinance_chunks
                GROUP BY municipality, county
                ORDER BY chunk_count DESC
            """)
        )
        rows = result.fetchall()

        municipalities = [
            {
                "municipality": municipality,
                "county": county,
                "chunk_count": chunk_count,
                "section_count": section_count,
                "first_ingested": _serialize_dt(first_ingested),
                "last_ingested": _serialize_dt(last_ingested),
                "avg_chunk_length": int(avg_chunk_length) if avg_chunk_length is not None else 0,
                "min_chunk_length": min_chunk_length or 0,
                "max_chunk_length": max_chunk_length or 0,
            }
            for (
                municipality,
                county,
                chunk_count,
                section_count,
                first_ingested,
                last_ingested,
                avg_chunk_length,
                min_chunk_length,
                max_chunk_length,
            ) in rows
        ]

        coverage = [
            {
                "municipality": row["municipality"],
                "county": row["county"],
                "state": None,
                "chunk_count": row["chunk_count"],
                "section_count": row["section_count"],
                "last_scraped_at": row["last_ingested"],
                "days_since_ingest": None,
                "total_analyses_run": 0,
                "avg_confidence_score": None,
                "coverage_tier": "seeded" if row["chunk_count"] else "gap",
                "is_stale": False,
                "is_gap": row["chunk_count"] == 0,
            }
            for row in municipalities
        ]

        return {
            "municipalities": municipalities,
            "coverage": coverage,
            "quality_trend": [],
            "gap_count": sum(1 for row in coverage if row["is_gap"]),
            "discoverable_total": max(88, len(coverage)),
            "ingested_total": sum(1 for row in coverage if not row["is_gap"]),
            "usage_by_plan": [],
            "total_municipalities": len(municipalities),
            "total_chunks": sum(row["chunk_count"] for row in municipalities),
        }
    except Exception as e:
        logger.exception("Data quality query failed")
        return {
            "error": str(e),
            "municipalities": [],
            "coverage": [],
            "quality_trend": [],
            "gap_count": 0,
            "discoverable_total": 88,
            "ingested_total": 0,
            "usage_by_plan": [],
            "total_municipalities": 0,
            "total_chunks": 0,
        }
    finally:
        await session.close()


@router.get("/admin/analytics")
async def analytics():
    """API usage analytics -- request counts, latencies, error rates."""
    from plotlot.api.analytics import get_analytics

    return get_analytics()


@router.get("/admin/costs")
async def cost_dashboard():
    """LLM cost dashboard -- token usage and estimated costs from MLflow.

    Aggregates per-run token counts and estimated USD costs across recent
    MLflow experiments. Production relevance: without cost visibility,
    GetOnStack's costs went from $127/week to $47K/month.
    """
    from plotlot.observability.tracing import mlflow as _mlflow

    if _mlflow is None:
        return {"error": "MLflow not installed", "costs": []}

    try:
        client = _mlflow.MlflowClient()
        experiments = client.search_experiments(max_results=5)

        cost_data: list[dict] = []
        total_cost = 0.0
        total_tokens = 0

        for exp in experiments:
            runs = client.search_runs(
                experiment_ids=[exp.experiment_id],
                max_results=50,
                order_by=["start_time DESC"],
            )
            for run in runs:
                metrics = run.data.metrics
                cost = metrics.get("estimated_cost_usd", 0)
                tokens = int(metrics.get("total_tokens", 0))
                if cost > 0 or tokens > 0:
                    cost_data.append(
                        {
                            "run_id": run.info.run_id,
                            "start_time": run.info.start_time,
                            "model": run.data.params.get("model", "unknown"),
                            "input_tokens": int(metrics.get("input_tokens", 0)),
                            "output_tokens": int(metrics.get("output_tokens", 0)),
                            "total_tokens": tokens,
                            "estimated_cost_usd": round(cost, 6),
                        }
                    )
                    total_cost += cost
                    total_tokens += tokens

        return {
            "total_estimated_cost_usd": round(total_cost, 4),
            "total_tokens": total_tokens,
            "query_count": len(cost_data),
            "recent_queries": cost_data[:20],
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "costs": []}


@router.delete("/admin/cache/{address}")
async def delete_cache_entry(address: str):
    """Delete a single cached report by address."""
    from plotlot.api.cache import normalize_address
    from plotlot.storage.models import ReportCache
    from sqlalchemy import delete as sql_delete

    normalized = normalize_address(address)
    session = await get_session()
    try:
        result = await session.execute(
            sql_delete(ReportCache).where(ReportCache.address_normalized == normalized)
        )
        await session.commit()
        deleted = result.rowcount  # type: ignore[attr-defined]
        return {"address": address, "deleted": deleted}
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@router.delete("/admin/cache")
async def clear_all_cache(confirm: bool = False):
    """Clear all cached reports. Requires confirm=true."""
    from plotlot.storage.models import ReportCache
    from sqlalchemy import delete as sql_delete, func, select

    session = await get_session()
    try:
        if not confirm:
            result = await session.execute(select(func.count()).select_from(ReportCache))
            count = result.scalar() or 0
            return {
                "cached_reports": count,
                "confirmed": False,
                "message": f"Would delete {count} cached reports. Add confirm=true to proceed.",
            }

        result = await session.execute(sql_delete(ReportCache))
        await session.commit()
        deleted = result.rowcount  # type: ignore[attr-defined]
        return {"deleted": deleted, "confirmed": True}
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@router.delete("/admin/chunks")
async def delete_chunks(municipality: str, confirm: bool = False):
    """Delete ordinance chunks for a municipality (e.g., bad data cleanup).

    Requires confirm=true as a safety check.
    """
    if not confirm:
        # Dry run — show what would be deleted
        from sqlalchemy import func, select
        from plotlot.storage.models import OrdinanceChunk

        session = await get_session()
        try:
            result = await session.execute(
                select(func.count()).where(OrdinanceChunk.municipality.ilike(municipality))
            )
            count = result.scalar() or 0
            return {
                "municipality": municipality,
                "chunks_to_delete": count,
                "confirmed": False,
                "message": f"Would delete {count} chunks. Add confirm=true to proceed.",
            }
        finally:
            await session.close()

    # Actual delete
    from sqlalchemy import delete as sql_delete
    from plotlot.storage.models import OrdinanceChunk

    session = await get_session()
    try:
        result = await session.execute(
            sql_delete(OrdinanceChunk).where(OrdinanceChunk.municipality.ilike(municipality))
        )
        await session.commit()
        deleted = result.rowcount  # type: ignore[attr-defined]
        logger.info("Deleted %d chunks for municipality: %s", deleted, municipality)
        return {
            "municipality": municipality,
            "chunks_deleted": deleted,
            "confirmed": True,
        }
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
