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
    except Exception as e:
        logger.exception("Pipeline error for address: %s", request.address)
        raise HTTPException(status_code=502, detail=str(e))

    if report is None:
        raise HTTPException(
            status_code=422,
            detail=f"Could not geocode address: {request.address}",
        )

    return ZoningReportResponse(**asdict(report))


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
            yield _sse_event("status", {
                "step": "analysis",
                "message": "AI analyzing zoning code...",
            })
            report = await _agentic_analysis(
                address=request.address,
                geo=geo,
                prop_record=prop_record,
                search_results=search_results,
                municipality=municipality,
                county=county,
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
