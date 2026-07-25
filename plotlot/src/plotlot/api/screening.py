"""Batch "buy box" screening endpoint.

Streams per-address results (SSE) as each candidate finishes analysis, then a
final ranked summary. Streaming + heartbeats keep the connection alive through
Render's 30s proxy timeout for long batches.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from plotlot.api.schemas import BuyBoxRequest
from plotlot.pipeline.analyze import analyze_property_full
from plotlot.pipeline.screening import BuyBox, ScreeningResult, screen_addresses

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/screen", tags=["screening"])

_MAX_ADDRESSES = 100


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _to_buy_box(req: BuyBoxRequest) -> BuyBox:
    return BuyBox(
        states=req.states,
        counties=req.counties,
        zoning_prefixes=req.zoning_prefixes,
        min_lot_sqft=req.min_lot_sqft,
        max_lot_sqft=req.max_lot_sqft,
        min_units=req.min_units,
        min_residual=req.min_residual,
        exclude_high_flood_risk=req.exclude_high_flood_risk,
        require_verified=req.require_verified,
        max_results=req.max_results,
    )


@router.post("")
async def screen(req: BuyBoxRequest) -> StreamingResponse:
    """Screen candidate addresses against a buy box, streaming progress via SSE."""
    addresses = [a.strip() for a in req.addresses if a and a.strip()][:_MAX_ADDRESSES]
    buy_box = _to_buy_box(req)

    async def event_gen():
        total = len(addresses)
        yield _sse("start", {"total": total})
        if not addresses:
            yield _sse(
                "summary",
                {"qualified": [], "rejected": [], "errors": [], "total": 0, "qualified_count": 0},
            )
            yield _sse("done", {})
            return

        queue: asyncio.Queue[ScreeningResult] = asyncio.Queue()

        async def on_result(r: ScreeningResult) -> None:
            await queue.put(r)

        async def _analyze(addr: str):
            return await analyze_property_full(addr, with_comps=req.with_comps)

        task = asyncio.create_task(
            screen_addresses(
                addresses, buy_box, _analyze, concurrency=req.concurrency, on_result=on_result
            )
        )

        completed = 0
        try:
            while completed < total:
                if task.done() and queue.empty():
                    break
                try:
                    r = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield _sse("heartbeat", {"completed": completed, "total": total})
                    continue
                completed += 1
                yield _sse("result", {"completed": completed, "total": total, "result": asdict(r)})

            batch = await task
            yield _sse(
                "summary",
                {
                    "qualified": [asdict(x) for x in batch.qualified],
                    "rejected": [asdict(x) for x in batch.rejected],
                    "errors": [asdict(x) for x in batch.errors],
                    "total": batch.total,
                    "qualified_count": batch.qualified_count,
                },
            )
            yield _sse("done", {})
        except Exception as exc:  # surface batch-level failure to the client
            logger.exception("Batch screening failed")
            yield _sse("error", {"detail": str(exc)})

    return StreamingResponse(event_gen(), media_type="text/event-stream")
