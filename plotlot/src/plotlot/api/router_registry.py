from __future__ import annotations

from fastapi import FastAPI

from plotlot.api.analyses import router as analyses_router
from plotlot.api.approvals import router as approvals_router
from plotlot.api.billing import router as billing_router
from plotlot.api.chat import router as chat_router
from plotlot.api.documents import router as documents_router
from plotlot.api.evidence import router as evidence_router
from plotlot.api.geometry import router as geometry_router
from plotlot.api.harness import router as harness_router
from plotlot.api.harness_approvals import router as harness_approvals_router
from plotlot.api.harness_calculations import router as harness_calculations_router
from plotlot.api.harness_evidence import router as harness_evidence_router
from plotlot.api.harness_health import router as harness_health_router
from plotlot.api.harness_jobs import router as harness_jobs_router
from plotlot.api.harness_memory import router as harness_memory_router
from plotlot.api.harness_municode import router as harness_municode_router
from plotlot.api.harness_reports import router as harness_reports_router
from plotlot.api.harness_tools import router as harness_tools_router
from plotlot.api.harness_verification import router as harness_verification_router
from plotlot.api.mcp import router as mcp_router
from plotlot.api.ordinance import router as ordinance_router
from plotlot.api.portfolio import router as portfolio_router
from plotlot.api.render import router as render_router
from plotlot.api.routes import router as analysis_router
from plotlot.api.screening import router as screening_router
from plotlot.api.tools import router as tools_router
from plotlot.api.workspaces import router as workspaces_router


def register_routers(app: FastAPI) -> None:
    app.include_router(analysis_router)
    app.include_router(billing_router)
    app.include_router(chat_router)
    app.include_router(approvals_router)
    app.include_router(workspaces_router)
    app.include_router(analyses_router)
    app.include_router(tools_router)
    app.include_router(evidence_router)
    app.include_router(mcp_router)
    app.include_router(portfolio_router)
    app.include_router(geometry_router)
    app.include_router(ordinance_router)
    app.include_router(render_router)
    app.include_router(screening_router)
    app.include_router(documents_router)
    app.include_router(harness_router)
    app.include_router(harness_approvals_router)
    app.include_router(harness_calculations_router)
    app.include_router(harness_evidence_router)
    app.include_router(harness_health_router)
    app.include_router(harness_jobs_router)
    app.include_router(harness_memory_router)
    app.include_router(harness_municode_router)
    app.include_router(harness_reports_router)
    app.include_router(harness_tools_router)
    app.include_router(harness_verification_router)
