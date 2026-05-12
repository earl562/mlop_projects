# Current State

## Stack
- frontend: local Next.js dev server used by Playwright on `http://127.0.0.1:3000` during no-db e2e; not left running after validation
- backend: `http://127.0.0.1:8000` starts with `uv run uvicorn plotlot.api.main:app --host 127.0.0.1 --port 8000`
- database: expected local Postgres on `localhost:5433` with pgvector; **not running** during the latest health probe
- generated artifacts: local `.docx`/`.xlsx` downloads under `data/artifacts`; no hosted office-suite API required
- property discovery cache: local JSON cache at `data/cache/property_cache.json`

## Last Verified
- timestamp: 2026-05-12T21:06:28Z
- commands:
  - `uv run mypy src/plotlot/ --no-error-summary`
  - `uv run ruff check src/ tests/`
  - `bash -n scripts/run_backend_with_codex_oauth.sh scripts/setup_phase2.sh`
  - `uv run pytest tests/unit/test_health.py tests/unit/test_llm.py tests/unit/test_api.py -q`
  - `npm run lint`
  - `npm run test:ui`
  - `npm run build`
  - `uv run pytest tests/unit/test_local_artifacts.py tests/unit/test_render.py tests/unit/test_api.py -q`
  - `npm run test:e2e:no-db`
  - `GROQ_API_KEY=local-smoke-key uv run uvicorn plotlot.api.main:app --host 127.0.0.1 --port 8000`
  - `curl -fsS --max-time 10 http://127.0.0.1:8000/health`
  - `curl -fsS --max-time 25 https://plotlot-api.onrender.com/health`
  - `curl -fsS --max-time 45 https://plotlot-api.onrender.com/debug/llm`
  - `vercel inspect https://mlopprojects.vercel.app --timeout 30s`
  - `vercel env ls production`
  - `git grep -n -i "google" -- apps/plotlot/src apps/plotlot/frontend/src apps/plotlot/tests apps/plotlot/scripts apps/plotlot/pyproject.toml apps/plotlot/.env.example`
- result:
  - mypy passed
  - ruff passed
  - shell script syntax passed
  - LLM/health/API regression slice passed: 53 tests
  - frontend lint passed
  - frontend UI passed: 14 tests
  - frontend production build passed
  - local artifact/render/API regression slice passed: 42 tests
  - frontend no-db e2e passed: 9 tests
  - Google code scan returned no matches in active code/config/test/script surfaces
  - local backend `/health` returned HTTP 200 with `status=degraded` because local Postgres was not running; `agent_chat_ready=true` with `GROQ_API_KEY=local-smoke-key`
  - production backend `/health` returned HTTP 200 with `status=healthy` and `agent_chat_ready=true`
  - production backend `/debug/llm` returned NVIDIA provider status `ok` using `https://integrate.api.nvidia.com/v1`
  - Vercel `plotlot-v2` production env now contains `NEXT_PUBLIC_API_URL=https://plotlot-api.onrender.com` and no Google env var

## Working
- Google Workspace/Google cloud product code has been removed from active backend/frontend/test/script surfaces.
- Agent chat recognizes non-Google provider priority: Groq first, then NVIDIA, then OpenAI/Codex OAuth, with OpenRouter as fallback.
- Production backend currently has a working NVIDIA LLM path; local dev can use Groq, NVIDIA, OpenAI/Codex OAuth, or OpenRouter through env vars.
- Spreadsheet exports now use open `.xlsx` files generated with `openpyxl`.
- Document exports now use `.docx` files generated with `python-docx`.
- Generated files are downloadable through `/api/v1/artifacts/{filename}`.
- Property discovery caching no longer depends on cloud cache services; it uses a local JSON cache.
- Building/concept render endpoints no longer require hosted image-generation credentials; they return deterministic local PNG schematics.
- The current `/workspace` UI test contract matches the address-first lookup shell instead of stale rail cards.

## Broken / Gaps
- DB-backed analysis and portfolio readiness are blocked until local Postgres is started on `localhost:5433`.
- Local agent chat requires one of `GROQ_API_KEY`, `NVIDIA_API_KEY`, `OPENAI_API_KEY`, `OPENAI_ACCESS_TOKEN`, `PLOTLOT_USE_CODEX_OAUTH=1`, or `OPENROUTER_API_KEY`; production currently satisfies this through NVIDIA.
- Production MLflow is degraded because its database schema is behind the installed MLflow version; API health and agent chat are still ready.
- Vercel `plotlot-v2` Project Settings still point at root directory `plotlot/frontend`; current source is under `plotlot/apps/plotlot/frontend`, so production frontend redeploys require correcting that setting or using an explicit corrected deploy path.
- no automated heartbeat to Discord/origin yet
- no enforced handoff protocol across sessions

## Next Actions
1. Run `make db-up` from `apps/plotlot` and rerun `bash scripts/status/healthcheck.sh` for DB-backed health.
2. Prefer `GROQ_API_KEY` in production when available; otherwise keep the current working `NVIDIA_API_KEY` path.
3. Continue remaining P0/P1 remediation after db-backed verification is healthy.

## Resume Commands
```bash
cd apps/plotlot
uv run mypy src/plotlot/ --no-error-summary
npm --prefix frontend run test:ui
npm --prefix frontend run test:e2e:no-db
uv run pytest tests/unit/test_local_artifacts.py tests/unit/test_render.py tests/unit/test_api.py -q
uv run uvicorn plotlot.api.main:app --host 127.0.0.1 --port 8000
curl -i -sS http://127.0.0.1:8000/health
bash scripts/status/healthcheck.sh
```

## Evidence
- state plan: `docs/plans/2026-04-09-autonomy-continuity-plan.md`
- runtime json: `docs/status/runtime-status.json`
- spec remediation plan: `docs/SPEC_DRIVEN_REMEDIATION_PLAN_2026-05-11.md`
- work breakdown: `docs/status/SPEC_DRIVEN_WORK_BREAKDOWN_2026-05-11.md`
- future health logs: `logs/health/`
- future watchdog logs: `logs/runner/`
