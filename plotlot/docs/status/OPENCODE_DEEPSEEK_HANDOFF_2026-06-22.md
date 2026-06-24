# OpenCode / DeepSeek Handoff - 2026-06-22

## Current State

Branch: `feature/deal-analysis-pipeline`

Repo root: `/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2`

Backend package root: `/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot`

Remote auth:
- `gh` CLI is installed.
- `gh` is authenticated as `earl562`.
- `gh auth setup-git` was run so pushes can use GitHub credentials.

OpenCode resume helpers:
- `/goal` command file: `.opencode/commands/goal.md`
- Project skill: `skills/plotlot-goal-resume/SKILL.md`
- OpenCode custom command docs confirm repo-local `.opencode/commands/*.md` files become slash commands.

Latest pushed commit:
- `64f0866 feat: add lookup snapshot evidence kernel`

Commits already pushed in this workstream:
- `9201e8c ci: enforce harness release gates`
- `2cab7ea feat: add agent harness workbench gates`
- `64f0866 feat: add lookup snapshot evidence kernel`

There is a large staged backend/MCP harness slice that has not yet been committed.
There are also many unrelated unstaged and untracked files in the worktree. Do not use
`git add .`, `git add -A`, `git reset --hard`, `git checkout .`, `git clean`, or `git stash`.

## Gate Status (June 22, 2026)

The prior gate review rejected the staged harness slice because several helper modules were
not in the index. This was closed in this session by staging:

- `plotlot/src/plotlot/api/mcp_tool_run_persistence.py`
- `plotlot/src/plotlot/api/tool_approval_validation.py`
- `plotlot/src/plotlot/api/tool_artifact_persistence.py`
- `plotlot/src/plotlot/api/tool_call_models.py`
- `plotlot/src/plotlot/api/tool_run_trace.py`
- `plotlot/src/plotlot/mcp/analysis.py`
- `plotlot/src/plotlot/mcp/comps.py`
- `plotlot/src/plotlot/mcp/coverage.py`
- `plotlot/src/plotlot/mcp/ingestion.py`
- `plotlot/src/plotlot/mcp/search.py`
- `plotlot/src/plotlot/mcp/tool_types.py`

With these files staged, runtime import checks in this worktree now pass for:
- `import plotlot.api.tools`
- `import plotlot.api.mcp`
- `import plotlot.mcp.server`

Gate-relevant tests were run on the updated slice:
- `uv run pytest tests/unit/test_agent_run_api.py`
- `uv run pytest tests/unit/test_mcp_server_agent_run_tools.py tests/unit/test_agent_run_mcp.py tests/unit/test_agent_run_trace.py tests/unit/test_context_broker.py`
- `uv run ruff check src/plotlot/api src/plotlot/harness src/plotlot/mcp ...`
- `uv run mypy src/plotlot/api src/plotlot/harness src/plotlot/mcp --ignore-missing-imports`

Remaining acceptance blockers from the previous review still stand until evidence artifacts are generated: a slice-specific goal review report, manual QA matrix, and notepad are still not present under `.omo/evidence` for this slice.

To close that gap, this session added and staged:
- `plotlot/.omo/evidence/agent-run-harness-backend-code-review.md`
- `plotlot/.omo/evidence/agent-run-harness-backend-qa/manualQa.md`
- `plotlot/.omo/evidence/agent-run-harness-backend-notepad.md`

The new artifacts record:
- verification commands and current pass status
- remaining high-priority QA risk (negative adversarial coverage for missing-zoning-input evidence states)
- explicit blocker closure from staging missing helper imports

## What We Did

1. Installed and connected GitHub CLI.
   - Verified `gh` is installed and authenticated as `earl562`.
   - Configured git credential integration with GitHub.

2. Committed and pushed CI/release-gate work.
   - Added workflow validation for CI/release-gate rules.
   - Added tests for workflow policy validation.
   - Pushed `9201e8c ci: enforce harness release gates`.

3. Committed and pushed frontend workbench gate work.
   - Added agent-run and release-gate frontend workbench surfaces.
   - Added focused frontend tests.
   - Pushed `2cab7ea feat: add agent harness workbench gates`.

4. Committed and pushed lookup snapshot evidence kernel.
   - Added lookup snapshot evidence kernel, repository, API surface, eval/release gate, golden cases, and tests.
   - Verification before push included focused lookup tests, ruff, mypy, and full unit tests.
   - Pushed `64f0866 feat: add lookup snapshot evidence kernel`.

5. Built the next backend agent-run harness slice and staged it.
   - Added agent-run domain models, repositories, trace models, eval models, improvement log, artifact claim validation, and report artifact generation.
   - Added API endpoints for starting agent runs, getting runs, retrieving traces, and evaluating runs.
   - Added MCP adapters and MCP server tool exposure for agent-run and eval tooling.
   - Added context broker evidence packets, evidence quality warnings, stale/missing evidence behavior, and traceable source retrievals.
   - Added planner primitives and specialist lane assignment rules.
   - Added document/report evidence gates so material claims require recorded evidence IDs.
   - Added tests for API access, MCP access, trace output, eval scoring, warning/escalation behavior, context broker, planner, and document evidence gates.

6. Refactored `default_runtime.py` before committing.
   - It had grown beyond the size threshold.
   - Split handlers into focused modules:
     - `default_location_tools.py`
     - `default_ordinance_tools.py`
     - `default_municode_live_tools.py`
     - `default_authority_tools.py`
     - `default_dataset_tools.py`
     - `default_document_tools.py`
     - `default_web_tools.py`
     - `default_runtime_support.py`
   - Kept `default_runtime.py` as thin wiring.
   - Preserved compatibility aliases:
     - `_handle_search_ordinances`
     - `_handle_search_municode_live`
     - `_is_pdf_scraped`
   - This was needed because `tests/unit/test_harness_runtime.py` patches/imports those private names.

7. Ran review and verification.
   - Focused agent-run/backend suite passed.
   - Harness runtime compatibility tests passed.
   - Full unit test suite passed.
   - Ruff check passed.
   - Ruff format check passed.
   - Mypy passed with existing unchecked-body notes only.
   - Local staged diff review found no whitespace errors and no obvious staged secrets.
   - A 5-lane review-work attempt was started, but the thread limit allowed only one reviewer to spawn. The wait was interrupted by the user before a result was collected.

8. Added OpenCode / DeepSeek resume support.
   - Created `.opencode/commands/goal.md` so OpenCode can resume with `/goal`.
   - Created `skills/plotlot-goal-resume/SKILL.md` for skill-based continuation.
   - Both point the next agent at this handoff, the repo rules, the git-discipline rule, current staged state, verification commands, and the next implementation queue.

## Staged Implementation Slice

The staged slice is intended to become the next commit, likely:

`feat: add agent run harness backend`

Staged summary at handoff time:
- `83 files changed`
- `9657 insertions`
- `2170 deletions`

Major staged areas:
- `plotlot/src/plotlot/api/agent_run_models.py`
- `plotlot/src/plotlot/api/agent_runs.py`
- `plotlot/src/plotlot/api/recorded_evidence_context.py`
- `plotlot/src/plotlot/api/mcp.py`
- `plotlot/src/plotlot/api/tools.py`
- `plotlot/src/plotlot/harness/agent_run*.py`
- `plotlot/src/plotlot/harness/context*.py`
- `plotlot/src/plotlot/harness/default_*tools.py`
- `plotlot/src/plotlot/harness/default_runtime.py`
- `plotlot/src/plotlot/harness/*tool_contract*.py`
- `plotlot/src/plotlot/harness/lookup_eval*.py`
- `plotlot/src/plotlot/harness/planner*.py`
- `plotlot/src/plotlot/harness/report_artifacts.py`
- `plotlot/src/plotlot/mcp/server.py`
- `plotlot/tests/unit/test_agent_run*.py`
- `plotlot/tests/unit/test_context_broker.py`
- `plotlot/tests/unit/test_document_tool*.py`
- `plotlot/tests/unit/test_harness_planner.py`
- `plotlot/tests/unit/test_mcp_server_agent_run_tools.py`

This staged slice should be reviewed with:

```bash
git diff --staged --stat
git diff --staged --name-only
git diff --staged
```

## Verification Already Run

From `/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot`:

```bash
uv run pytest tests/unit/test_agent_run_access_api.py tests/unit/test_agent_run_access_mcp.py tests/unit/test_agent_run_api.py tests/unit/test_agent_run_contradictions.py tests/unit/test_agent_run_eval.py tests/unit/test_agent_run_eval_assumption_labels.py tests/unit/test_agent_run_eval_mcp_tools.py tests/unit/test_agent_run_eval_trace_escalations.py tests/unit/test_agent_run_eval_trace_warnings.py tests/unit/test_agent_run_mcp.py tests/unit/test_agent_run_runtime.py tests/unit/test_agent_run_trace.py tests/unit/test_agent_run_trace_api.py tests/unit/test_context_broker.py tests/unit/test_document_tool_evidence_gate.py tests/unit/test_document_tool_recorded_evidence_context.py tests/unit/test_harness_planner.py tests/unit/test_mcp_server_agent_run_tools.py -q
```

Result:
- `43 passed, 1 warning`

```bash
uv run pytest tests/unit/test_harness_runtime.py -q
```

Result:
- `6 passed, 1 warning`

```bash
uv run pytest tests/unit/ -q
```

Result:
- `1589 passed, 2 warnings`

Warnings observed:
- MLflow filesystem tracking backend deprecation warning.
- Existing async mock / `prewarm_cache` runtime warnings.

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/plotlot/ --no-error-summary
```

Results:
- Ruff check passed.
- Ruff format check passed.
- Mypy exited successfully with existing unchecked-body notes in `storage/db.py`, `api/routes.py`, and `api/main.py`.

Staged size check was run and returned no files over threshold without an explicit `allow: SIZE_OK` marker:

```bash
for file in $(git diff --staged --name-only); do
  case "$file" in
    *.py|*.ts|*.tsx)
      lines=$(awk 'NF && $1 !~ /^#/ {count++} END {print count+0}' "$file")
      if [ "$lines" -gt 250 ] && ! rg -q 'allow: SIZE_OK' "$file"; then
        printf '%s %s\n' "$lines" "$file"
      fi
    ;;
  esac
done
```

## Git Discipline Rules

Follow these exactly:
- Commit format: `type: short description`, lowercase, no period.
- No `Co-Authored-By` trailers.
- Do not modify git config.
- Stage explicit paths only.
- Do not commit `.env`, credentials, caches, MLflow artifacts, DB dumps, or large binaries.
- Do not revert unrelated dirty worktree changes.

Applicable rule files already read:
- `/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/.claude/rules/git-discipline.md`
- `/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/AGENTS.md`
- `/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot/AGENTS.md`

## Dirty Worktree Warning

The worktree is intentionally dirty beyond the staged backend slice.

Do not assume all dirty files belong to the current commit.
Do not stage unrelated files.

Examples of unrelated or separate unstaged/untracked areas currently present:
- `.github/workflows/*`
- root `AGENTS.md`, `Makefile`
- frontend package/app/component/test files
- deleted logs and DB artifacts
- `plotlot/pyproject.toml`, `plotlot/render.yaml`
- many ingestion/pipeline/property/retrieval/storage modifications
- many untracked ingestion/MCP/pipeline scripts and tests
- research docs under `plotlot/docs/research/`
- `.github/dependabot.yml`

Before committing, run:

```bash
git status --short --branch
git diff --staged --name-only
git diff --staged --stat
```

Only commit the staged backend/MCP harness slice plus this handoff doc if desired.
If preserving OpenCode resume support, also include `.opencode/commands/goal.md` and
`skills/plotlot-goal-resume/SKILL.md`.

## Recommended Next Steps

1. Review the staged diff.

```bash
git diff --staged --stat
git diff --staged --name-only
git diff --staged
```

2. Re-run the backend gates from package root.

```bash
cd /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/plotlot
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/plotlot/ --no-error-summary
uv run pytest tests/unit/ -q
```

3. If still green, commit only the staged files.

```bash
cd /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2
git commit -m "feat: add agent run harness backend"
git push
```

4. After that commit, decide the next isolated slice.
   Recommended next slice: ingestion/MCP persistence and tool approval trace persistence, because there are untracked files already present for:
   - `plotlot/src/plotlot/api/mcp_tool_run_persistence.py`
   - `plotlot/src/plotlot/api/tool_approval_validation.py`
   - `plotlot/src/plotlot/api/tool_artifact_persistence.py`
   - `plotlot/src/plotlot/api/tool_call_models.py`
   - `plotlot/src/plotlot/api/tool_run_trace.py`
   - related tests such as `test_tool_trace_persistence.py`, `test_tool_connector_policy.py`, and `test_mcp_ingestion_context.py`.

5. Keep commits small and pushed frequently.
   The user explicitly wants SWE CI/CD discipline with constant commits and pushes to GitHub.

## Architecture Intent To Preserve

The product target is not just lookup. The backend should remain a lookup-correctness-first agentic land-developer harness:

Reliable ingestion -> evidence kernel -> context broker -> typed tool contracts -> deterministic calculators -> agent runtime/planner -> specialist lanes -> policy/approvals/escalation -> API + MCP adapters -> frontend workbench -> reports/documents/artifacts -> traces/evals/regression gates/continuous improvement.

Non-negotiables:
- Every user-visible lookup field needs evidence IDs.
- Missing or unsupported zoning facts remain unknown, not inferred.
- Reports and documents may only cite recorded evidence IDs and labeled assumptions.
- External writes require approval.
- Deterministic calculators own calculations.
- LLM output cannot silently become trusted fact.
- Contradictions and stale evidence must surface as warnings or escalation.

## Known Risks / Follow-Up Items

- The staged backend slice is large. It passed tests, but it should still get one more human or agent code review before commit if budget allows.
- The multi-agent review-work flow did not fully complete because the thread limit blocked four of five lanes and the one spawned reviewer was interrupted before reporting.
- There are many unrelated dirty files. The next agent must preserve them unless intentionally taking ownership of a specific slice.
- `land_use/models.py` is over the pure line threshold but already has an explicit size marker:
  `# allow: SIZE_OK - shared land-use Pydantic model aggregate; split in a dedicated refactor.`
- Some test comments use bug/BDD-style comments and should be left if they clarify regression intent.

## Quick Resume Prompt

Use this prompt for the next agent:

```text
Continue PlotLot on branch feature/deal-analysis-pipeline.
Read AGENTS.md, plotlot/AGENTS.md, and .claude/rules/git-discipline.md first.
If using OpenCode, run /goal from the repo root or load the plotlot-goal-resume skill.
Do not use git add -A, git add ., reset, checkout, clean, or stash.
The staged backend/MCP agent-run harness slice is ready for final review.
Run git diff --staged --stat/name-only, rerun ruff/format/mypy/full unit tests from plotlot/, then commit with:
feat: add agent run harness backend
Push to origin.
Do not stage unrelated dirty or untracked files.
After push, take the next isolated slice around tool approval / MCP trace persistence.
```
