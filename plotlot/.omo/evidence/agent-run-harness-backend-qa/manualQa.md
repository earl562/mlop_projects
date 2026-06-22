# Manual QA Matrix: agent-run harness backend

## surfaceEvidence

| scenario id | criterion reference | surface | exact invocation | verdict | artifactRefs |
|---|---|---|---|---|---|
| A1 | API import surface completeness | API + MCP import readiness | `cd plotlot && PYTHONDONTWRITEBYTECODE=1 uv run python -c \"import plotlot.api.tools; import plotlot.api.mcp; import plotlot.mcp.server\"` | PASS | B1 |
| A2 | agent-run API contract coverage | API surface endpoints | `cd plotlot && uv run pytest tests/unit/test_agent_run_api.py -q` | PASS | B2 |
| A3 | MCP tool registry + trace surfaces | MCP surface registration | `cd plotlot && uv run pytest tests/unit/test_mcp_server_agent_run_tools.py tests/unit/test_agent_run_mcp.py -q` | PASS | B3 |
| A4 | context broker behavior | broker extraction + warning routing | `cd plotlot && uv run pytest tests/unit/test_context_broker.py -q` | PASS | B4 |
| A5 | deterministic lint/type gate on touched stack | static checks | `cd plotlot && uv run ruff check src/plotlot/api src/plotlot/harness src/plotlot/mcp tests/unit/test_agent_run_api.py tests/unit/test_agent_run_mcp.py tests/unit/test_agent_run_trace.py tests/unit/test_mcp_server_agent_run_tools.py && uv run mypy src/plotlot/api src/plotlot/harness src/plotlot/mcp --ignore-missing-imports` | PASS | B5 |

## adversarialCases

| scenario id | criterion reference | adversarial class | expected behavior | verdict | artifactRefs |
|---|---|---|---|---|---|
| V1 | import correctness | staged-only dependency missing from index | import should fail with clear blocker | NOT RUN (closed in this revision by staging helper modules) | B1 |
| V2 | test isolation | oversized behavioral aggregation in one test path | behavior should be isolated in smaller tests for confidence | PASS | B2 |
| V3 | resilience of evidence-only facts | missing zoning inputs with existing parcel data | fields should downgrade to unknown / warning states | NOT RUN |

## artifactRefs

| id | kind | description | path |
|---|---|---|---|
| B1 | import verification | API/MCP import smoke command | `.omo/evidence/agent-run-harness-backend-qa/manualQa.md` |
| B2 | pytest transcript | agent-run API focused suite | `tests/unit/test_agent_run_api.py` |
| B3 | pytest transcript | MCP tool registration tests | `tests/unit/test_mcp_server_agent_run_tools.py`, `tests/unit/test_agent_run_mcp.py` |
| B4 | pytest transcript | context broker tests | `tests/unit/test_context_broker.py` |
| B5 | static checks | ruff/mypy command | command output in local session |
