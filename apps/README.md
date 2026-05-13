# Apps

This directory contains deployable applications (services, web apps, jobs).

- `plotlot/` — PlotLot backend + frontend (FastAPI + Next.js)

Conventions:

- Keep app-specific dependency/lockfiles inside each app (e.g. `uv.lock`, `package-lock.json`).
- Add new apps as siblings under `apps/`.
