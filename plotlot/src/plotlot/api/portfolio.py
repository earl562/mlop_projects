"""Portfolio endpoints — save and list zoning analyses.

Phase D2: Persistent PostgreSQL storage. Server restarts no longer lose data.
When auth is wired in (Supabase), queries will filter by user_id.
"""

import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select

from plotlot.api.schemas import SaveAnalysisRequest, SavedAnalysisResponse
from plotlot.storage.db import get_session
from plotlot.storage.models import PortfolioEntry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


def _row_to_response(row: PortfolioEntry) -> SavedAnalysisResponse:
    """Convert a PortfolioEntry ORM row to the API response schema."""
    report_data = row.report_json
    density = report_data.get("density_analysis")
    max_units = density.get("max_units") if density else None

    return SavedAnalysisResponse(
        id=str(row.id),
        address=row.address,
        municipality=row.municipality,
        county=row.county,
        zoning_district=row.zoning_district or "",
        max_units=max_units,
        confidence=report_data.get("confidence", ""),
        saved_at=row.created_at.isoformat() if row.created_at else "",
        report=report_data,
    )


@router.post("", response_model=SavedAnalysisResponse)
async def save_analysis(request: SaveAnalysisRequest):
    """Save a zoning analysis to the portfolio."""
    report = request.report

    entry = PortfolioEntry(
        address=report.formatted_address or report.address,
        municipality=report.municipality,
        county=report.county,
        zoning_district=report.zoning_district or None,
        report_json=report.model_dump(),
    )

    session = await get_session()
    try:
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        logger.info("Saved analysis %d: %s", entry.id, entry.address)
        return _row_to_response(entry)
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@router.get("", response_model=list[SavedAnalysisResponse])
async def list_analyses(user_id: str | None = None):
    """List all saved analyses in the portfolio.

    Optionally filter by user_id (ready for when auth is wired in).
    """
    session = await get_session()
    try:
        stmt = select(PortfolioEntry).order_by(PortfolioEntry.created_at.desc())
        if user_id is not None:
            stmt = stmt.where(PortfolioEntry.user_id == user_id)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [_row_to_response(row) for row in rows]
    finally:
        await session.close()


@router.get("/{analysis_id}", response_model=SavedAnalysisResponse)
async def get_analysis(analysis_id: int):
    """Get a specific saved analysis."""
    session = await get_session()
    try:
        result = await session.execute(
            select(PortfolioEntry).where(PortfolioEntry.id == analysis_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Analysis not found")
        return _row_to_response(row)
    finally:
        await session.close()


@router.delete("/{analysis_id}")
async def delete_analysis(analysis_id: int):
    """Remove an analysis from the portfolio."""
    session = await get_session()
    try:
        result = await session.execute(
            delete(PortfolioEntry).where(PortfolioEntry.id == analysis_id)
        )
        if result.rowcount == 0:  # type: ignore[union-attr]
            raise HTTPException(status_code=404, detail="Analysis not found")
        await session.commit()
        return {"status": "deleted", "id": str(analysis_id)}
    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
