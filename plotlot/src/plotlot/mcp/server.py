from __future__ import annotations

import logging
from dataclasses import asdict
from typing import TypeAlias
from uuid import uuid4

import fastmcp

from plotlot.harness.agent_run_tool import handle_start_agent_run
from plotlot.harness.agent_run_trace_tool import handle_get_agent_run_trace
from plotlot.harness.agent_run_eval_tool import (
    handle_evaluate_agent_run,
    handle_get_agent_run_improvement_summary,
    handle_get_latest_agent_run_eval,
)
from plotlot.ingestion.acp_coordinator import run_on_demand_ingestion
from plotlot.land_use.models import ToolContext
from plotlot.pipeline.lookup_snapshot_eval import LOOKUP_CORRECTNESS_SUITE
from plotlot.harness.lookup_eval_tools import (
    DEFAULT_EVAL_HISTORY_LIMIT,
    handle_assess_lookup_release_gate,
    handle_list_lookup_eval_runs,
    handle_run_lookup_golden_eval_batch,
)
from plotlot.mcp.analysis import RunFullAnalysisDeps, run_full_analysis_tool
from plotlot.mcp.comps import (
    ComparableSalesDeps,
    ComparableSalesInput,
    run_get_comparable_sales,
)
from plotlot.mcp.coverage import CoverageDeps, run_get_coverage
from plotlot.mcp.ingestion import McpIngestInput, run_ingest_municipality
from plotlot.mcp.search import SearchZoningDeps, SearchZoningInput, run_search_zoning
from plotlot.pipeline.comps import find_comparables
from plotlot.pipeline.lookup import lookup_address
from plotlot.retrieval.search import hybrid_search
from plotlot.storage.db import get_session

logger = logging.getLogger(__name__)

FastMcpToolResult: TypeAlias = dict

mcp = fastmcp.FastMCP(
    name="plotlot",
    instructions=(
        "PlotLot: AI-powered land deal intelligence. "
        "Use ingest_municipality when a municipality has no zoning data. "
        "Use run_full_analysis to evaluate any US property address. "
        "Use search_zoning to look up specific zoning provisions. "
        "Use get_coverage to see what municipalities are already indexed. "
        "Use get_comparable_sales to find recent land transactions near a location. "
        "Use evaluate_agent_run and get_agent_run_improvement_summary to score "
        "agent-run replay quality. "
        "Use run_lookup_golden_eval_batch to run canonical lookup-correctness "
        "golden cases against recorded lookup snapshots. "
        "Use list_lookup_eval_runs and assess_lookup_release_gate to inspect "
        "lookup-correctness evals before release.\n\n"
        "GROUNDING RULES (strict - never violate):\n"
        "1. Report ONLY values present in tool responses. Never invent zoning codes, "
        "dimensional standards, phone numbers, office names, or URLs.\n"
        "2. run_full_analysis returns a 'data_status' object and 'presentation_guidance' "
        "string - follow that guidance exactly when wording your answer.\n"
        "3. If data_status.zoning_district_found is true, state the zoning district plainly; "
        "do NOT claim the zoning 'could not be retrieved'.\n"
        "4. If data_status.dimensional_standards_found is false, say the standards are not yet "
        "in the database and offer to run ingest_municipality - do NOT fill the gap from general "
        "knowledge.\n"
        "5. When a tool returns an 'error' field, report the error honestly; do not fabricate a "
        "successful-looking answer."
    ),
    version="2.1.0",
)


@mcp.tool
async def ingest_municipality(
    municipality: str,
    state: str,
    county: str | None = None,
) -> FastMcpToolResult:
    """Ingest zoning ordinances for a municipality into the PlotLot database."""

    return await run_ingest_municipality(
        McpIngestInput(municipality=municipality, state=state, county=county),
        runner=run_on_demand_ingestion,
    )


@mcp.tool
async def run_full_analysis(address: str) -> FastMcpToolResult:
    """Run the full PlotLot analysis pipeline for a US property address."""

    return await run_full_analysis_tool(
        address,
        deps=RunFullAnalysisDeps(lookup_address=lookup_address, asdict_fn=asdict),
    )


@mcp.tool
async def search_zoning(
    municipality: str,
    query: str,
    limit: int = 10,
) -> FastMcpToolResult:
    """Search indexed zoning ordinance text for a municipality."""

    return await run_search_zoning(
        SearchZoningInput(municipality=municipality, query=query, limit=limit),
        deps=SearchZoningDeps(get_session=get_session, hybrid_search=hybrid_search),
    )


@mcp.tool
async def get_coverage() -> FastMcpToolResult:
    """Return zoning ordinance coverage statistics for indexed municipalities."""

    return await run_get_coverage(CoverageDeps(get_session=get_session))


@mcp.tool
async def get_comparable_sales(
    lat: float,
    lng: float,
    state: str = "FL",
    radius_miles: float = 3.0,
) -> FastMcpToolResult:
    """Find comparable land sales near a coordinate."""

    return await run_get_comparable_sales(
        ComparableSalesInput(
            lat=lat,
            lng=lng,
            state=state,
            radius_miles=radius_miles,
        ),
        deps=ComparableSalesDeps(find_comparables=find_comparables),
    )


@mcp.tool
async def list_lookup_eval_runs(
    suite: str = LOOKUP_CORRECTNESS_SUITE,
    limit: int = DEFAULT_EVAL_HISTORY_LIMIT,
) -> FastMcpToolResult:
    """List recorded lookup-correctness eval runs and improvement-log entries."""

    return await handle_list_lookup_eval_runs(
        {"suite": suite, "limit": limit},
        _fastmcp_tool_context("list_lookup_eval_runs"),
    )


@mcp.tool
async def assess_lookup_release_gate(
    suite: str = LOOKUP_CORRECTNESS_SUITE,
) -> FastMcpToolResult:
    """Assess whether latest lookup-correctness eval history blocks release."""

    return await handle_assess_lookup_release_gate(
        {"suite": suite},
        _fastmcp_tool_context("assess_lookup_release_gate"),
    )


@mcp.tool
async def run_lookup_golden_eval_batch(
    snapshot_id: str,
    address: str | None = None,
    case_id: str | None = None,
    suite: str = LOOKUP_CORRECTNESS_SUITE,
    use_latest_baseline: bool = True,
) -> FastMcpToolResult:
    """Run a recorded lookup snapshot against a canonical golden fixture."""

    return await handle_run_lookup_golden_eval_batch(
        {
            "suite": suite,
            "snapshots": [
                {
                    "snapshot_id": snapshot_id,
                    "address": address,
                    "case_id": case_id,
                }
            ],
            "use_latest_baseline": use_latest_baseline,
        },
        _fastmcp_tool_context("run_lookup_golden_eval_batch"),
    )


@mcp.tool
async def start_agent_run(
    lookup_snapshot_id: str,
    objective: str,
    run_id: str | None = None,
) -> FastMcpToolResult:
    """Start a replayable agent run from a recorded lookup snapshot."""

    resolved_run_id = run_id.strip() if run_id else f"fastmcp_agent_run_{uuid4()}"
    return await handle_start_agent_run(
        {"lookup_snapshot_id": lookup_snapshot_id, "objective": objective},
        _fastmcp_tool_context("start_agent_run", resolved_run_id),
    )


@mcp.tool
async def get_agent_run_trace(run_id: str) -> FastMcpToolResult:
    """Return the replay trace package for a recorded agent run."""

    return await handle_get_agent_run_trace(
        {"run_id": run_id},
        _fastmcp_tool_context("get_agent_run_trace"),
    )


@mcp.tool
async def evaluate_agent_run(run_id: str) -> FastMcpToolResult:
    """Score a recorded agent run against deterministic replay and evidence gates."""

    return await handle_evaluate_agent_run(
        {"run_id": run_id},
        _fastmcp_tool_context("evaluate_agent_run"),
    )


@mcp.tool
async def get_latest_agent_run_eval(run_id: str) -> FastMcpToolResult:
    """Return the latest persisted deterministic eval for a recorded agent run."""

    return await handle_get_latest_agent_run_eval(
        {"run_id": run_id},
        _fastmcp_tool_context("get_latest_agent_run_eval"),
    )


@mcp.tool
async def get_agent_run_improvement_summary(run_id: str) -> FastMcpToolResult:
    """Return baseline delta and release-blocking status for an agent-run eval."""

    return await handle_get_agent_run_improvement_summary(
        {"run_id": run_id},
        _fastmcp_tool_context("get_agent_run_improvement_summary"),
    )


def _fastmcp_tool_context(
    tool_name: str,
    run_id: str = "fastmcp_lookup_eval",
) -> ToolContext:
    return ToolContext(
        workspace_id="fastmcp",
        actor_user_id="fastmcp",
        run_id=run_id,
        tool_run_id=f"fastmcp_{tool_name}",
        project_id="fastmcp_project",
        risk_budget_cents=0,
    )


def run() -> None:
    mcp.run()
