Deploy PlotLot to production (Render + Vercel).

## Pre-deploy Checks

1. Ensure all tests pass:
   ```bash
   cd plotlot && uv run pytest tests/unit/ -v --tb=short
   ```

2. Ensure lint is clean:
   ```bash
   cd plotlot && uv run ruff check src/ tests/
   ```

3. Check for uncommitted changes:
   ```bash
   git status
   ```

## Deploy Steps

### Backend (Render)
- Render auto-deploys from `main` branch via Dockerfile
- Push to `main` triggers deploy: `git push origin main`
- If database schema changed, run migrations first:
  ```bash
  cd plotlot && uv run alembic upgrade head
  ```
- Monitor deploy at Render dashboard

### Frontend (Vercel)
- Vercel auto-deploys from `main` branch
- Push to `main` triggers deploy
- Check deploy status: `vercel --prod` (if Vercel CLI is configured)

## Post-deploy Verification

1. Backend health: `curl https://plotlot-api.onrender.com/health`
2. Frontend: check the Vercel deployment URL
3. Test a real analysis: enter an address and verify the pipeline completes

Report deployment status for both services.
