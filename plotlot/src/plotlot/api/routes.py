"""API route handlers for PlotLot.

POST /api/v1/analyze — synchronous analysis (await pipeline, return JSON)
POST /api/v1/analyze/stream — SSE streaming with real-time pipeline progress
"""

import asyncio
import json
import logging
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from plotlot.api.schemas import AnalyzeRequest, ErrorResponse, ZoningReportResponse
from plotlot.pipeline.lookup import lookup_address
from plotlot.retrieval.geocode import geocode_address
from plotlot.retrieval.property import lookup_property
from plotlot.retrieval.search import hybrid_search
from plotlot.pipeline.calculator import calculate_max_units, parse_lot_dimensions
from plotlot.pipeline.lookup import _agentic_analysis
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


@router.post(
    "/analyze",
    response_model=ZoningReportResponse,
    responses={
        422: {"model": ErrorResponse, "description": "Geocoding failed or invalid input"},
        502: {"model": ErrorResponse, "description": "Pipeline error"},
        504: {"model": ErrorResponse, "description": "Pipeline timeout"},
    },
)
async def analyze(request: AnalyzeRequest):
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
        raise HTTPException(status_code=502, detail=str(e))

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
                yield _sse_event("error", {
                    "detail": f"Could not geocode address: {request.address}",
                    "error_type": "geocoding_failed",
                })
                return

            municipality = geo["municipality"]
            county = geo["county"]
            lat = geo.get("lat")
            lng = geo.get("lng")

            # Boundary enforcement — reject addresses outside South Florida
            county_lower = county.lower() if county else ""
            from plotlot.pipeline.lookup import VALID_COUNTIES, ACCEPTABLE_ACCURACY
            if county_lower not in VALID_COUNTIES:
                yield _sse_event("error", {
                    "detail": (
                        f"Address is in {county} County. "
                        f"PlotLot covers Miami-Dade, Broward, and Palm Beach counties only."
                    ),
                    "error_type": "outside_coverage",
                })
                return

            accuracy = str(geo.get("accuracy", "")).lower()
            if accuracy and accuracy not in ACCEPTABLE_ACCURACY:
                yield _sse_event("error", {
                    "detail": (
                        f"Could not confidently locate this address "
                        f"(geocoding accuracy: {accuracy}). Please check the address."
                    ),
                    "error_type": "low_accuracy",
                })
                return

            yield _sse_event("status", {
                "step": "geocoding",
                "message": f"Found: {municipality}, {county} County",
                "complete": True,
            })

            # Step 2: Property lookup
            yield _sse_event("status", {
                "step": "property",
                "message": "Fetching property record...",
            })
            prop_record = await lookup_property(request.address, county, lat=lat, lng=lng)

            if prop_record and prop_record.municipality:
                pa_muni = prop_record.municipality.strip().title()
                if pa_muni and len(pa_muni) > 3 and pa_muni.lower() != municipality.lower():
                    municipality = pa_muni
                    geo["municipality"] = municipality

            yield _sse_event("status", {
                "step": "property",
                "message": f"Lot: {prop_record.lot_size_sqft:,.0f} sqft" if prop_record else "No record found",
                "complete": True,
            })

            # Step 3: Hybrid search
            yield _sse_event("status", {
                "step": "search",
                "message": "Searching zoning ordinances...",
            })
            search_query = prop_record.zoning_code if prop_record and prop_record.zoning_code else municipality
            session = await get_session()
            try:
                search_results = await hybrid_search(session, municipality, search_query, limit=15)
            finally:
                await session.close()

            yield _sse_event("status", {
                "step": "search",
                "message": f"Found {len(search_results)} relevant sections",
                "complete": True,
            })

            # Step 4: Agentic LLM analysis
            # Render's proxy has a 30s idle timeout — send heartbeats to keep alive
            yield _sse_event("status", {
                "step": "analysis",
                "message": "AI analyzing zoning code...",
            })

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
                yield _sse_event("status", {
                    "step": "analysis",
                    "message": "AI analyzing zoning code...",
                })

            if report is None:
                if not analysis_task.done():
                    analysis_task.cancel()
                logger.error("LLM analysis timed out for: %s", request.address)
                from plotlot.pipeline.lookup import _build_fallback_report
                report = _build_fallback_report(
                    request.address, geo, prop_record,
                    [f"{r.section} — {r.section_title}" for r in search_results if r.section],
                )

            yield _sse_event("status", {
                "step": "analysis",
                "message": f"Zoning: {report.zoning_district} — {report.zoning_description}",
                "complete": True,
            })

            # Step 5: Density calculation
            if report.numeric_params and report.property_record and report.property_record.lot_size_sqft > 0:
                yield _sse_event("status", {
                    "step": "calculation",
                    "message": "Computing max density...",
                })
                lot_width, lot_depth = parse_lot_dimensions(
                    report.property_record.lot_dimensions or "",
                )
                report.density_analysis = calculate_max_units(
                    lot_size_sqft=report.property_record.lot_size_sqft,
                    params=report.numeric_params,
                    lot_width_ft=lot_width,
                    lot_depth_ft=lot_depth,
                )
                yield _sse_event("status", {
                    "step": "calculation",
                    "message": f"Max units: {report.density_analysis.max_units} ({report.density_analysis.governing_constraint})",
                    "complete": True,
                })

            # Final result
            yield _sse_event("result", asdict(report))

        except Exception as e:
            logger.exception("Stream pipeline error for: %s", request.address)
            yield _sse_event("error", {
                "detail": str(e),
                "error_type": "pipeline_error",
            })

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
                select(func.count()).where(
                    OrdinanceChunk.municipality.ilike(municipality)
                )
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
            sql_delete(OrdinanceChunk).where(
                OrdinanceChunk.municipality.ilike(municipality)
            )
        )
        await session.commit()
        deleted = result.rowcount
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
