"""Data Center Site Selection API routes.

POST /api/v1/analyze/datacenter — SSE streaming pipeline for industrial site evaluation.

Separate from the residential zoning pipeline:
  - Different pipeline steps (EIA, FCC, FEMA, USGS, industrial RAG)
  - Different output type (SiteScorecard vs ZoningReport)
  - Different cache key (analysis_type="datacenter")
"""

import asyncio
import json
import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from plotlot.api.billing import check_analysis_limit
from plotlot.api.cache import cache_report, get_cached_report
from plotlot.api.schemas import AnalyzeRequest
from plotlot.core.types import InfraSignal
from plotlot.retrieval.geocode import geocode_address
from plotlot.retrieval.property import lookup_property
from plotlot.retrieval.search import hybrid_search
from plotlot.storage.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["datacenter"])

_DC_CACHE_QUALITY_FIELDS = ("composite_rating", "composite_score")


def _unavailable_signal(name: str, label: str) -> InfraSignal:
    """Return a neutral 0.5-score signal when a data source is unreachable."""
    return InfraSignal(
        name=name,
        label=label,
        score=0.5,
        rating="Fair",
        summary="Data unavailable — scored neutral.",
        raw_value="N/A",
        source="unavailable",
        confidence="low",
    )


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _dc_should_cache(scorecard: dict) -> bool:
    """Quality gate for data center report cache writes."""
    composite_rating = scorecard.get("composite_rating", "")
    composite_score = scorecard.get("composite_score", 0.0)
    return bool(composite_rating) and composite_score > 0.0


@router.post("/analyze/datacenter")
async def analyze_datacenter(request: AnalyzeRequest, _: None = Depends(check_analysis_limit)):
    """Stream data center site analysis with real-time pipeline progress via SSE."""

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

            if isinstance(geo.get("accuracy"), (int, float)) and geo["accuracy"] < 0.8:
                yield _sse_event(
                    "error",
                    {
                        "detail": f"Low geocoding accuracy ({geo['accuracy']}). Check address.",
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

            # Cache check
            try:
                cached = await get_cached_report(request.address, analysis_type="datacenter")
                if cached:
                    logger.info("DC Cache HIT for %s", request.address)
                    yield _sse_event(
                        "cache_hit", {"message": "Using cached site analysis", "type": "datacenter"}
                    )
                    yield _sse_event("done", cached)
                    return
            except Exception as exc:
                logger.warning("DC cache lookup failed: %s", exc)

            # Step 2: Property lookup
            yield _sse_event("status", {"step": "property", "message": "Looking up parcel data..."})
            try:
                prop = await asyncio.wait_for(
                    lookup_property(
                        request.address,
                        county,
                        lat=lat,
                        lng=lng,
                        state=geo.get("state", "FL"),
                    ),
                    timeout=30.0,
                )
            except asyncio.TimeoutError:
                yield _sse_event(
                    "error",
                    {
                        "detail": "Property lookup timed out. Try again.",
                        "error_type": "property_timeout",
                    },
                )
                return
            except Exception as exc:
                logger.warning("DC property lookup failed: %s", exc)
                prop = None

            if prop:
                yield _sse_event(
                    "property",
                    {
                        "step": "property",
                        "complete": True,
                        "zoning_code": prop.zoning_code or "",
                        "lot_size_sqft": prop.lot_size_sqft,
                        "municipality": prop.municipality,
                    },
                )
            else:
                yield _sse_event(
                    "status",
                    {
                        "step": "property",
                        "message": "Property data not found — proceeding with geocode-only data",
                        "complete": True,
                    },
                )
                # Build minimal PropertyRecord from geocode data
                from plotlot.core.types import PropertyRecord

                prop = PropertyRecord(
                    address=request.address,
                    municipality=municipality,
                    county=county,
                )

            # Step 3: Industrial zoning RAG search
            yield _sse_event(
                "status", {"step": "zoning_search", "message": "Searching industrial ordinances..."}
            )
            zoning_code = prop.zoning_code or ""
            try:
                zoning_query = (
                    f"industrial zoning data center server farm {zoning_code} "
                    f"setback noise outdoor equipment conditional use {municipality}"
                )
                dc_session = await get_session()
                try:
                    search_results = await hybrid_search(
                        dc_session, municipality, zoning_query, limit=15
                    )
                    # Also try a broader industrial search if initial results are sparse
                    if len(search_results) < 5:
                        broader = await hybrid_search(
                            dc_session,
                            municipality,
                            f"industrial manufacturing heavy industrial special use {municipality}",
                            limit=10,
                        )
                        seen_sections = {r.section for r in search_results}
                        search_results.extend(r for r in broader if r.section not in seen_sections)
                finally:
                    await dc_session.close()
            except Exception as exc:
                logger.warning("DC zoning search failed: %s", exc)
                search_results = []

            yield _sse_event(
                "status",
                {
                    "step": "zoning_search",
                    "message": f"Found {len(search_results)} relevant ordinance sections",
                    "complete": True,
                    "chunk_count": len(search_results),
                },
            )

            # Step 4–9: Infrastructure signals + scoring (run_datacenter_pipeline)
            yield _sse_event(
                "status",
                {
                    "step": "infrastructure",
                    "message": "Analyzing power grid, fiber, flood zone, seismic risk, and zoning...",
                },
            )

            # Emit sub-step signals as they complete using concurrent tasks with progress updates
            from plotlot.pipeline.datacenter import (
                fetch_power_signal,
                fetch_fiber_signal,
                fetch_flood_signal,
                fetch_seismic_signal,
                extract_datacenter_params,
                score_zoning_signal,
                compute_composite_score,
                generate_site_summary,
            )

            # Kick off all concurrent tasks
            tasks = {
                "power": asyncio.create_task(fetch_power_signal(lat, lng)),
                "fiber": asyncio.create_task(fetch_fiber_signal(lat, lng)),
                "flood": asyncio.create_task(fetch_flood_signal(lat, lng)),
                "seismic": asyncio.create_task(fetch_seismic_signal(lat, lng)),
                "zoning_params": asyncio.create_task(
                    extract_datacenter_params(municipality, county, zoning_code, search_results)
                ),
            }

            results = {}
            pending = dict(tasks)

            # Stream signals as they complete; heartbeat every 14s to keep Render proxy alive
            while pending:
                done_tasks, _ = await asyncio.wait(
                    list(pending.values()), return_when=asyncio.FIRST_COMPLETED, timeout=14.0
                )
                if not done_tasks:
                    yield _sse_event("heartbeat", {"type": "heartbeat"})
                    continue
                for done in done_tasks:
                    task_name = next(k for k, v in pending.items() if v is done)
                    try:
                        results[task_name] = await done
                        sig = results[task_name]
                        if task_name != "zoning_params":
                            yield _sse_event(
                                "signal",
                                {
                                    "signal": task_name,
                                    "label": sig.label,
                                    "score": sig.score,
                                    "rating": sig.rating,
                                    "summary": sig.summary,
                                    "raw_value": sig.raw_value,
                                    "source": sig.source,
                                },
                            )
                    except Exception as exc:
                        logger.error("Signal task %s failed: %s", task_name, exc)
                    del pending[task_name]

            power_signal = results.get("power") or _unavailable_signal("power_grid", "Power Grid")
            fiber_signal = results.get("fiber") or _unavailable_signal(
                "fiber", "Fiber Connectivity"
            )
            flood_signal = results.get("flood") or _unavailable_signal("flood_zone", "Flood Zone")
            seismic_signal = results.get("seismic") or _unavailable_signal(
                "seismic", "Seismic Risk"
            )
            dc_params = results.get("zoning_params")

            # Score zoning signal from extracted params
            from plotlot.core.types import DataCenterParams

            if dc_params is None:
                dc_params = DataCenterParams(zoning_code=zoning_code)
            zoning_signal = score_zoning_signal(dc_params, zoning_code)

            yield _sse_event(
                "signal",
                {
                    "signal": "zoning",
                    "label": zoning_signal.label,
                    "score": zoning_signal.score,
                    "rating": zoning_signal.rating,
                    "summary": zoning_signal.summary,
                    "raw_value": zoning_signal.raw_value,
                    "source": zoning_signal.source,
                },
            )

            composite_score, composite_rating = compute_composite_score(
                power_signal, fiber_signal, flood_signal, seismic_signal, zoning_signal
            )

            yield _sse_event(
                "status",
                {
                    "step": "scoring",
                    "message": f"Composite score: {composite_score:.0%} — {composite_rating}",
                    "complete": True,
                    "composite_score": composite_score,
                    "composite_rating": composite_rating,
                },
            )

            # Generate executive summary — LLM call can take 30-60s, emit heartbeat first
            yield _sse_event("heartbeat", {"type": "heartbeat"})
            yield _sse_event(
                "status", {"step": "summary", "message": "Generating executive summary..."}
            )
            partial_scorecard = {
                "address": request.address,
                "municipality": municipality,
                "composite_score": composite_score,
                "composite_rating": composite_rating,
                "signals": {
                    "power": asdict(power_signal),
                    "fiber": asdict(fiber_signal),
                    "flood": asdict(flood_signal),
                    "seismic": asdict(seismic_signal),
                    "zoning": asdict(zoning_signal),
                },
                "datacenter_params": asdict(dc_params),
            }
            summary, deal_breakers, strengths = await generate_site_summary(
                request.address, partial_scorecard
            )

            sources = [
                "NREL Utility Rates API",
                "FCC National Broadband Map",
                "FEMA NFIP Flood Map Service",
                "USGS Seismic Hazard API",
                "Municode Industrial Ordinance RAG",
            ]
            sources.extend(dc_params.source_sections)

            from plotlot.core.types import SiteScorecard

            scorecard = SiteScorecard(
                address=request.address,
                formatted_address=request.address,
                municipality=municipality,
                county=county,
                lat=lat,
                lng=lng,
                property_record=prop,
                power_signal=power_signal,
                fiber_signal=fiber_signal,
                flood_signal=flood_signal,
                seismic_signal=seismic_signal,
                zoning_signal=zoning_signal,
                datacenter_params=dc_params,
                composite_score=composite_score,
                composite_rating=composite_rating,
                summary=summary,
                deal_breakers=deal_breakers,
                strengths=strengths,
                sources=list(set(sources)),
                confidence="high"
                if all(
                    s.confidence == "high"
                    for s in [
                        power_signal,
                        fiber_signal,
                        flood_signal,
                        seismic_signal,
                        zoning_signal,
                    ]
                )
                else "medium",
            )

            scorecard_dict = asdict(scorecard)

            # Cache write
            try:
                if _dc_should_cache(scorecard_dict):
                    await cache_report(request.address, scorecard_dict, analysis_type="datacenter")
            except Exception as exc:
                logger.warning("DC cache write failed: %s", exc)

            yield _sse_event("done", scorecard_dict)

        except Exception:
            logger.exception("Data center pipeline error for %s", request.address)
            yield _sse_event(
                "error",
                {
                    "detail": "Data center analysis failed. Please try again.",
                    "error_type": "pipeline_error",
                },
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
