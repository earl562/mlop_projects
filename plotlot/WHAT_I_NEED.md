# What PlotLot Needs

Never paste API keys into chat, screenshots, issues, commits, or test output. Add secrets only
to `plotlot/.env` for local development and to the hosting provider's encrypted environment
settings for deployment.

## Core lookup and agent

```env
DATABASE_URL=postgresql+asyncpg://plotlot:plotlot@localhost:5432/plotlot

PLOTLOT_LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=deepseek/deepseek-v4-flash
OPENROUTER_SITE_URL=https://plotlot.app
OPENROUTER_APP_NAME=PlotLot

GEOCODIO_API_KEY=
JINA_API_KEY=
NVIDIA_API_KEY=
HF_TOKEN=
```

Use port `5432` for the existing Homebrew PostgreSQL service. Use port `5433` when running
PlotLot's Docker Compose database.

## Comparable properties

```env
RENTCAST_API_KEY=
HASDATA_API_KEY=
EXA_API_KEY=
```

RentCast is the preferred keyed fallback. Official parcel/GIS sources and the browser comp
workflow remain primary evidence paths where available. Browser-captured listings are
evidence candidates and must retain URL, retrieval time, filters, screenshot, and
verification status.

## Production features

```env
# Real user authentication
AUTH_ENABLED=false
CLERK_JWKS_URL=
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
CLERK_SECRET_KEY=

# Billing
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRO_PRICE_ID=

# Media generation
FAL_KEY=

# Error monitoring
SENTRY_DSN=
```

PlotLot does not use Google APIs. Mapping uses ArcGIS/OpenStreetMap. Reports and documents
use PlotLot's own export pipeline.

## Safe verification

From `plotlot/`:

```bash
make auth-readiness
```

This reports only whether each credential group is configured. It never prints secret
values.

Run the deterministic product gate:

```bash
make verify-local
make btdi
```

After the database and API are healthy, run:

```bash
make btdi-connected
make live-agent-e2e
```

## Credential rotation

If a credential appears in chat, a screenshot, a terminal recording, or git history:

1. Revoke it at the provider immediately.
2. Create a replacement with the smallest required permissions and a spending limit.
3. Update local `.env` and the encrypted deployment environment.
4. Run `make auth-readiness`.
5. Run the smallest live test for that provider.
