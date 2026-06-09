"""Pipeline snapshot API — serves dashboard data."""
from fastapi import APIRouter
from plotlot.harness.lead_management import LeadPipeline
from plotlot.harness.portfolio import PortfolioDashboard

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])

_pipeline: LeadPipeline | None = None


def set_pipeline(pipeline: LeadPipeline) -> None:
    global _pipeline
    _pipeline = pipeline


@router.get("/snapshot")
async def pipeline_snapshot():
    if _pipeline is None:
        return {"total_leads": 0, "by_status": {}, "counties": {}, "top_deals": [], "hidden_gems_count": 0, "due_follow_up": 0, "avg_score": 0}
    dash = PortfolioDashboard(_pipeline)
    snap = dash.snapshot()
    return {
        "total_leads": snap.total_leads,
        "by_status": snap.by_status,
        "counties": snap.by_county,
        "top_deals": snap.top_deals,
        "hidden_gems_count": snap.hidden_gems_count,
        "due_follow_up": snap.due_follow_up,
        "avg_score": snap.avg_score,
    }
