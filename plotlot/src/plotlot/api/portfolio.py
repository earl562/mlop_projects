"""Portfolio endpoints — save and list zoning analyses.

Phase 5b: Simple in-memory store for now. When auth is added (5b+),
this becomes user-scoped with PostgreSQL persistence.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from plotlot.api.schemas import SaveAnalysisRequest, SavedAnalysisResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])

# In-memory store — will be replaced with DB when auth is added
_portfolio: dict[str, dict] = {}


@router.post("", response_model=SavedAnalysisResponse)
async def save_analysis(request: SaveAnalysisRequest):
    """Save a zoning analysis to the portfolio."""
    report = request.report
    analysis_id = str(uuid.uuid4())[:8]

    entry = {
        "id": analysis_id,
        "address": report.formatted_address or report.address,
        "municipality": report.municipality,
        "county": report.county,
        "zoning_district": report.zoning_district,
        "max_units": report.density_analysis.max_units if report.density_analysis else None,
        "confidence": report.confidence,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "report": report.model_dump(),
    }

    _portfolio[analysis_id] = entry
    logger.info("Saved analysis %s: %s", analysis_id, report.address)

    return SavedAnalysisResponse(**entry)  # type: ignore[arg-type]


@router.get("", response_model=list[SavedAnalysisResponse])
async def list_analyses():
    """List all saved analyses in the portfolio."""
    return [
        SavedAnalysisResponse(**entry)  # type: ignore[arg-type]
        for entry in sorted(
            _portfolio.values(),
            key=lambda x: x["saved_at"],
            reverse=True,
        )
    ]


@router.get("/{analysis_id}", response_model=SavedAnalysisResponse)
async def get_analysis(analysis_id: str):
    """Get a specific saved analysis."""
    if analysis_id not in _portfolio:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return SavedAnalysisResponse(**_portfolio[analysis_id])


@router.delete("/{analysis_id}")
async def delete_analysis(analysis_id: str):
    """Remove an analysis from the portfolio."""
    if analysis_id not in _portfolio:
        raise HTTPException(status_code=404, detail="Analysis not found")
    del _portfolio[analysis_id]
    return {"status": "deleted", "id": analysis_id}
