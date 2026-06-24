# PlotLot Agent-Run Harness Backend Code Review

codeQualityStatus: BLOCK
recommendation: REQUEST_CHANGES
reportPath: `.omo/evidence/agent-run-harness-backend-code-review.md`

## Scope Reviewed

- `src/plotlot/api/tools.py`
- `src/plotlot/api/mcp.py`
- `src/plotlot/api/agent_run_models.py`
- `src/plotlot/api/agent_runs.py`
- `src/plotlot/mcp/server.py`
- `src/plotlot/harness/default_*.py`
- `src/plotlot/harness/planner*.py`
- `src/plotlot/harness/context*.py`
- `src/plotlot/harness/agent_run*.py`
- `tests/unit/test_agent_run*.py`
- `tests/unit/test_mcp_server_agent_run_tools.py`
- `tests/unit/test_context_broker.py`

Additional helpers newly added to complete staged imports:
- `src/plotlot/api/mcp_tool_run_persistence.py`
- `src/plotlot/api/tool_approval_validation.py`
- `src/plotlot/api/tool_artifact_persistence.py`
- `src/plotlot/api/tool_call_models.py`
- `src/plotlot/api/tool_run_trace.py`
- `src/plotlot/mcp/analysis.py`
- `src/plotlot/mcp/comps.py`
- `src/plotlot/mcp/coverage.py`
- `src/plotlot/mcp/ingestion.py`
- `src/plotlot/mcp/search.py`
- `src/plotlot/mcp/tool_types.py`

## Verification

Executed locally:
- `cd plotlot && PYTHONDONTWRITEBYTECODE=1 uv run python -c "import plotlot.api.tools; import plotlot.api.mcp; import plotlot.mcp.server"`
- `cd plotlot && uv run pytest tests/unit/test_agent_run_api.py -q`
- `cd plotlot && uv run pytest tests/unit/test_mcp_server_agent_run_tools.py tests/unit/test_agent_run_mcp.py tests/unit/test_agent_run_trace.py tests/unit/test_context_broker.py -q`
- `cd plotlot && uv run ruff check src/plotlot/api src/plotlot/harness src/plotlot/mcp tests/unit/test_agent_run_api.py tests/unit/test_agent_run_mcp.py tests/unit/test_agent_run_trace.py tests/unit/test_mcp_server_agent_run_tools.py`
- `cd plotlot && uv run mypy src/plotlot/api src/plotlot/harness src/plotlot/mcp --ignore-missing-imports`

Result summary: all checks above passed in this environment.

## Findings

### HIGH

1. `tests/unit/test_agent_run_api.py::test_agent_run_endpoint_evaluates_lookup_run_and_tracks_improvement` (and related tests) now cover focused behavior, but it remains a rich contract for planner/eval/report coupling. Monitor for brittleness when planner internals evolve.

### MEDIUM

1. `git status` and staged diff evidence indicate this slice is very broad (backend, MCP, tool contracts, planner, and tests) and should keep split commits where possible to reduce regression-risk.
2. Existing project guidance still forbids `git add -A`; the current `/goal` resume instructions have been updated to enforce explicit staging and import checks.

### BLOCKER

1. Manual QA remains focused on positive cases; V3 (evidence-only facts under adversarial missing-zoning inputs) still needs a dedicated negative test in this slice.
