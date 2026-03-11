Start local development servers for PlotLot.

## Steps

1. Check that required environment variables are set in `plotlot/.env`:
   - `DATABASE_URL`
   - `NVIDIA_API_KEY`
   - `GEOCODIO_API_KEY`

2. Start the backend (in `plotlot/`):
   ```bash
   cd plotlot && uv run uvicorn plotlot.api.main:app --reload --port 8000
   ```

3. In a separate terminal, start the frontend (in `plotlot/frontend/`):
   ```bash
   cd plotlot/frontend && npm run dev
   ```

4. Verify both are running:
   - Backend health: `curl http://localhost:8000/health`
   - Frontend: open `http://localhost:3000`

Report the status of both servers. If either fails, diagnose and fix the issue.
