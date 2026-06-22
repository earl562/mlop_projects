---
description: Resume PlotLot lookup-correctness-first agentic harness work from the current handoff
agent: build
---

Resume the PlotLot implementation loop with minimal drop-off.

First, read these files end to end before making any edits:

1. `/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/AGENTS.md`
2. `/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot/AGENTS.md`
3. `/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/.claude/rules/git-discipline.md`
4. `/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot/docs/status/OPENCODE_DEEPSEEK_HANDOFF_2026-06-22.md`

Then verify live state:

```bash
cd /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2
git status --short --branch
git log --oneline -5 --decorate
git diff --staged --stat
git diff --staged --name-only
git ls-files --stage | rg 'plotlot/src/plotlot/api/(mcp_tool_run_persistence|tool_approval_validation|tool_artifact_persistence|tool_call_models|tool_run_trace)\\.py|plotlot/src/plotlot/mcp/(analysis|comps|coverage|ingestion|search|tool_types)\\.py'
```

Primary objective:

Continue building PlotLot as a lookup-correctness-first agentic land-developer harness:

Reliable ingestion -> evidence kernel -> context broker -> typed tool contracts -> deterministic calculators -> agent runtime/planner -> specialist lanes -> policy/approvals/escalation -> API + MCP adapters -> frontend workbench -> reports/documents/artifacts -> traces/evals/regression gates/continuous improvement.

Immediate work queue:

1. Final-review the currently staged backend/MCP agent-run harness slice.
2. Re-run required gates from `/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot`:

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/plotlot/ --no-error-summary
uv run pytest tests/unit/ -q
```

3. Verify staged import surface is complete before commit:

```bash
cd /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot
PYTHONDONTWRITEBYTECODE=1 uv run python -c "import plotlot.api.tools; import plotlot.api.mcp; import plotlot.mcp.server"
```

4. If green and import checks pass, commit only explicit staged paths with:

```bash
git commit -m "feat: add agent run harness backend"
git push
```

5. After push, continue with the next isolated slice around tool approval / MCP trace persistence.

Non-negotiable rules:

- Do not use `git add .` or `git add -A`.
- Do not run `git reset --hard`, `git checkout .`, `git clean`, or `git stash`.
- Do not revert unrelated dirty worktree changes.
- Do not commit `.env`, credentials, caches, MLflow artifacts, DB dumps, or large binaries.
- No `Co-Authored-By` trailers.
- Keep commits focused and push frequently.
- Every code change needs tests.
- Ruff check, ruff format check, mypy, and unit tests must pass before push.
- Every trust-critical claim must be evidence-backed.
- Missing zoning facts are unknown, not inferred.
- User-visible lookup fields need evidence IDs.
- Reports/documents may only cite recorded evidence IDs and labeled assumptions.
- External writes require approval.
- Deterministic calculators own calculations.
- LLM output cannot silently become trusted fact.
- Contradictions and stale evidence must surface as warnings or escalation.

If `$ARGUMENTS` is provided, treat it as the specific next slice or override for this resume run:

`$ARGUMENTS`
