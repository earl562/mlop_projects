"""Portfolio endpoints — save and list zoning analyses.

Phase D2: Persistent PostgreSQL storage. Server restarts no longer lose data.
When auth is wired in (Supabase), queries will filter by user_id.
"""

import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException
from sqlalchemy import delete, select

from plotlot.api.schemas import SaveAnalysisRequest, SavedAnalysisResponse
from plotlot.storage.db import get_session
from plotlot.storage.models import PortfolioEntry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


def _row_to_response(row: PortfolioEntry) -> SavedAnalysisResponse:
    """Convert a PortfolioEntry ORM row to the API response schema."""
    from plotlot.api.schemas import ZoningReportResponse

    # Type-cast ORM attributes to their scalar types
    address: str = cast(str, row.address)  # type: ignore[assignment]
    municipality: str = cast(str, row.municipality)  # type: ignore[assignment]
    county: str = cast(str, row.county)  # type: ignore[assignment]
    zoning_district: str = cast(str, row.zoning_district or "")  # type: ignore[assignment]
    created_at = row.created_at
    report_data: dict[str, Any] = cast(dict, row.report_json)  # type: ignore[assignment]

    density = report_data.get("density_analysis")
    max_units = density.get("max_units") if density else None

    # Convert dict to ZoningReportResponse
    report = ZoningReportResponse.model_validate(report_data)

    return SavedAnalysisResponse(
        id=str(row.id),
        address=address,
        municipality=municipality,
        county=county,
        zoning_district=zoning_district,
        max_units=max_units,
        confidence=report_data.get("confidence", ""),
        saved_at=created_at.isoformat() if created_at else "",
        report=report,
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
        if result.rowcount == 0:  # type: ignore[attr-defined]
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
