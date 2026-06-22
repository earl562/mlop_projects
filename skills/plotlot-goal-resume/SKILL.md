---
name: plotlot-goal-resume
description: "Use when resuming PlotLot /goal work in OpenCode or DeepSeek. Rehydrates the current lookup-correctness-first agentic land-developer harness objective, handoff state, git rules, verification gates, and next implementation queue."
version: 1.0.0
author: PlotLot
license: MIT
platforms: [macos]
metadata:
  tags: [plotlot, goal, handoff, opencode, deepseek, agentic-harness]
---

# PlotLot Goal Resume

## When To Use

Use this skill at the start of any OpenCode / DeepSeek session that continues PlotLot work from the current Codex handoff.

Trigger phrases:
- `/goal`
- `goal`
- `resume PlotLot`
- `continue Plotlot`
- `agentic harness`
- `lookup correctness`
- `OpenCode handoff`
- `DeepSeek handoff`

## Required First Reads

Before editing or committing, read these files end to end:

```bash
sed -n '1,260p' /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/AGENTS.md
sed -n '1,320p' /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot/AGENTS.md
sed -n '1,240p' /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/.claude/rules/git-discipline.md
sed -n '1,360p' /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot/docs/status/OPENCODE_DEEPSEEK_HANDOFF_2026-06-22.md
```

If any file is longer than the ranges above, continue reading until EOF.

## Live State Check

Run this before making changes:

```bash
cd /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2
git status --short --branch
git log --oneline -5 --decorate
git diff --staged --stat
git diff --staged --name-only
git ls-files --stage | rg 'plotlot/src/plotlot/api/(mcp_tool_run_persistence|tool_approval_validation|tool_artifact_persistence|tool_call_models|tool_run_trace)\\.py|plotlot/src/plotlot/mcp/(analysis|comps|coverage|ingestion|search|tool_types)\\.py'
```

Report:
- active branch
- latest commit
- whether staged changes exist
- whether unrelated dirty/untracked files exist
- exact commit/push plan

## Objective

Continue PlotLot as a lookup-correctness-first agentic land-developer harness.

Core architecture:

```text
Reliable ingestion
-> Evidence kernel
-> Context broker
-> Typed tool contracts
-> Deterministic calculators
-> Agent runtime and planner
-> Specialist analyst lanes
-> Policy, approvals, and escalation
-> API + MCP adapters
-> Frontend workbench
-> Reports/documents/artifacts
-> Traces, evals, regression gates, and continuous improvement
```

## Current Handoff Summary

Latest pushed commit:

```text
64f0866 feat: add lookup snapshot evidence kernel
```

Already pushed in this workstream:

```text
9201e8c ci: enforce harness release gates
2cab7ea feat: add agent harness workbench gates
64f0866 feat: add lookup snapshot evidence kernel
```

Current staged slice:

```text
Backend/MCP agent-run harness implementation
83 files changed
9657 insertions
2170 deletions
```

Likely next commit message:

```text
feat: add agent run harness backend
```

## Verification Evidence From Codex

Already run from `/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot`:

```bash
uv run pytest tests/unit/test_agent_run_access_api.py tests/unit/test_agent_run_access_mcp.py tests/unit/test_agent_run_api.py tests/unit/test_agent_run_contradictions.py tests/unit/test_agent_run_eval.py tests/unit/test_agent_run_eval_assumption_labels.py tests/unit/test_agent_run_eval_mcp_tools.py tests/unit/test_agent_run_eval_trace_escalations.py tests/unit/test_agent_run_eval_trace_warnings.py tests/unit/test_agent_run_mcp.py tests/unit/test_agent_run_runtime.py tests/unit/test_agent_run_trace.py tests/unit/test_agent_run_trace_api.py tests/unit/test_context_broker.py tests/unit/test_document_tool_evidence_gate.py tests/unit/test_document_tool_recorded_evidence_context.py tests/unit/test_harness_planner.py tests/unit/test_mcp_server_agent_run_tools.py -q
```

Result: `43 passed, 1 warning`

```bash
uv run pytest tests/unit/test_harness_runtime.py -q
```

Result: `6 passed, 1 warning`

```bash
uv run pytest tests/unit/ -q
```

Result: `1589 passed, 2 warnings`

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/plotlot/ --no-error-summary
```

Results:
- ruff check passed
- ruff format check passed
- mypy passed with existing unchecked-body notes

## Immediate Resume Procedure

1. Review the staged diff.

```bash
cd /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2
git diff --staged --stat
git diff --staged --name-only
git diff --staged
```

2. Re-run gates.

```bash
cd /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/plotlot/ --no-error-summary
uv run pytest tests/unit/ -q
```

3. Verify staged import surface is complete before commit.

```bash
cd /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot
PYTHONDONTWRITEBYTECODE=1 uv run python -c "import plotlot.api.tools; import plotlot.api.mcp; import plotlot.mcp.server"
```

4. If green and import checks pass, commit and push.

```bash
cd /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2
git commit -m "feat: add agent run harness backend"
git push
```

5. Continue with the next isolated slice:
   tool approval / MCP trace persistence.

Likely files for next slice include:

```text
plotlot/src/plotlot/api/mcp_tool_run_persistence.py
plotlot/src/plotlot/api/tool_approval_validation.py
plotlot/src/plotlot/api/tool_artifact_persistence.py
plotlot/src/plotlot/api/tool_call_models.py
plotlot/src/plotlot/api/tool_run_trace.py
plotlot/tests/unit/test_tool_trace_persistence.py
plotlot/tests/unit/test_tool_connector_policy.py
plotlot/tests/unit/test_mcp_ingestion_context.py
```

## Git Rules

Never:
- `git add .`
- `git add -A`
- `git reset --hard`
- `git checkout .`
- `git clean`
- `git stash`
- revert unrelated dirty worktree changes
- commit secrets, caches, MLflow artifacts, DB dumps, or large binaries
- add `Co-Authored-By` trailers

Always:
- stage explicit paths only
- keep commits focused
- push after each passing commit
- use commit format `type: short description`
- run tests and quality gates before push

## Product Rules

Preserve these invariants:

- Lookup correctness is the first release gate.
- Every user-visible lookup field maps to evidence IDs.
- Missing or unsupported zoning facts are unknown, not inferred.
- Official public sources outrank aggregators, listings, cached summaries, or model memory.
- Contradictions are surfaced, not silently resolved.
- Reports/documents cite only recorded evidence IDs and labeled assumptions.
- External writes require approval.
- Deterministic calculators own zoning math, density, GLA, FAR, parking, setbacks, lot coverage, DSCR, NOI, land value, and scenario deltas.
- LLMs may extract/classify/summarize/reason, but deterministic validators decide what becomes trusted fact.

## If In Doubt

Stop and re-read:

```text
plotlot/docs/status/OPENCODE_DEEPSEEK_HANDOFF_2026-06-22.md
plotlot/docs/architecture/agentic-land-use-harness.md
plotlot/.omx/plans/prd-agentic-land-use-harness.md
```

Then continue with the smallest isolated commit that can pass tests and be pushed.
