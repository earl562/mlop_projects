---
title: "Auth + Billing Deployment Runbook (Clerk + Stripe on Render/Vercel)"
owner: plotlot
last_verified: 2026-06-03
status: in_progress
---

# Auth + Billing Deployment Runbook

This runbook walks through wiring Clerk (auth) and Stripe (billing) on
PlotLot's three deployment surfaces — local dev, Render (backend), and
Vercel (frontend).  The backend code is already in place; the work is
configuration.

The acceptance criteria are:

1. A user can sign up / sign in via Clerk.
2. The free tier (5 analyses/month) is enforced for free users.
3. A user can upgrade to Pro via Stripe Checkout.
4. The Stripe webhook marks the user as Pro and the new state is
   reflected on next request.
5. A subscription cancellation reverts the user to Free.
6. All four flows are covered by automated tests.

The test coverage is in:

- `tests/unit/test_auth.py` — Clerk JWT verification (16 cases)
- `tests/unit/test_middleware.py` — Rate limiter + auth multiplier (11 cases)
- `tests/unit/test_billing.py` — Stripe webhook + subscription lifecycle (14 cases)

## What is already wired

- ✅ Backend Clerk JWT verification (`src/plotlot/api/auth.py`) — opt-in
  via `AUTH_ENABLED`.
- ✅ Backend Stripe billing + webhook (`src/plotlot/api/billing.py`) —
  checkout completion, subscription deletion, invoice paid.
- ✅ Backend middleware stack (`src/plotlot/api/main.py`):
  AuthMiddleware → RateLimitMiddleware → CorrelationIDMiddleware →
  APIVersionMiddleware → CORSMiddleware.
- ✅ Rate limiter with 3× bonus for authenticated users
  (`src/plotlot/api/middleware.py`).
- ✅ Frontend Clerk middleware (`frontend/src/proxy.ts`) with public-route
  whitelist.
- ✅ Frontend Stripe checkout route
  (`frontend/src/app/api/stripe/checkout/route.ts`).
- ✅ Frontend billing page (`frontend/src/app/billing/page.tsx`).
- ✅ DB migration for `user_subscriptions` table
  (`alembic/versions/006_add_user_subscriptions.py`).
- ✅ Env var scaffolding in `plotlot/.env.example` and
  `plotlot/render.yaml` (Stripe + Clerk slots added in this run).
- ✅ `scripts/check_auth_readiness.py` and
  `scripts/bootstrap_live_auth.py` for credential bootstrapping.

## What requires the user (browser + dashboard steps)

Three steps cannot be automated from a CLI without interactive auth:

### 1. `stripe login` (one-time, ~30s)

```bash
stripe login
```

This prints a URL like
`https://dashboard.stripe.com/stripecli/confirm_auth?t=...` that you
must open in a browser.  After clicking "Allow access", the CLI is
paired with your Stripe account for webhook forwarding.

This is required for `stripe listen` to forward webhooks to your local
backend during development.

### 2. Stripe Dashboard — create product + price + webhook

In the **test mode** of <https://dashboard.stripe.com/test/products>:

1. **Product**: create "PlotLot Pro" (recurring, $49/month).
2. **Price**: copy the `price_...` ID → set as `STRIPE_PRO_PRICE_ID`.
3. **API keys**: from <https://dashboard.stripe.com/test/apikeys>, copy
   the secret key (`sk_test_...`) → `STRIPE_SECRET_KEY`.
4. **Webhook endpoint**: at
   <https://dashboard.stripe.com/test/webhooks>, add endpoint
   `https://<your-render-backend>/api/v1/stripe/webhook`, subscribe to
   `checkout.session.completed`,
   `customer.subscription.deleted`, and `invoice.paid`.  Copy the
   signing secret (`whsec_...`) → `STRIPE_WEBHOOK_SECRET`.

For local development, the equivalent is:

```bash
stripe listen --forward-to localhost:8000/api/v1/stripe/webhook
# copy the printed whsec_... into STRIPE_WEBHOOK_SECRET in .env
```

### 3. Clerk Dashboard — create application + copy keys

At <https://dashboard.clerk.com/>:

1. **Create application** (sign-in methods: email + Google).
2. **API Keys** page: copy
   - `pk_test_...` → `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` (frontend)
   - `sk_test_...` → `CLERK_SECRET_KEY` (frontend + backend optional)
3. **JWT Templates** → copy the JWKS URL (looks like
   `https://<your-app>.clerk.accounts.dev/.well-known/jwks.json`) →
   `CLERK_JWKS_URL` (backend).

## Local development setup

```bash
cd plotlot/plotlot

# 1. Auth the Stripe CLI (browser step above)
stripe login

# 2. Copy env template and fill in
cp .env.example .env
# edit .env: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRO_PRICE_ID,
#            NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY, CLERK_SECRET_KEY, CLERK_JWKS_URL

# 3. Start webhook forwarding in a second terminal
stripe listen --forward-to localhost:8000/api/v1/stripe/webhook
# copy the printed whsec_... into .env's STRIPE_WEBHOOK_SECRET

# 4. Start backend
uv run uvicorn plotlot.api.main:app --reload

# 5. Start frontend
cd frontend && npm run dev

# 6. Verify
uv run python scripts/check_auth_readiness.py
uv run pytest tests/unit/test_auth.py tests/unit/test_middleware.py tests/unit/test_billing.py -v
```

## Backend (Render) — wiring secrets

Three options for getting the keys onto Render.  The render.yaml in
this repo already declares the slots (`sync: false`) so the values can
be set without redeploying.

### Option A — Render dashboard (recommended for one-time setup)

1. Visit <https://dashboard.render.com/web/> and select `plotlot-api`.
2. **Environment** → add / update:
   - `AUTH_ENABLED` = `true` (after Clerk is configured)
   - `CLERK_JWKS_URL` = (paste from Clerk dashboard)
   - `STRIPE_SECRET_KEY` = `sk_test_...` or `sk_live_...`
   - `STRIPE_WEBHOOK_SECRET` = `whsec_...` (from Stripe webhook
     endpoint configuration)
   - `STRIPE_PRO_PRICE_ID` = `price_...`
3. **Save** → Render auto-redeploys.

### Option B — Render CLI (does NOT support env-var setting in v2.10)

As of Render CLI v2.10, there is **no `render env` subcommand** —
`render env set` is not a valid command (verified: `Error: unknown
command "env" for "render"`). The CLI in this version only supports
`deploys`, `services`, `workspaces`, `environments`, and `login`.

The supported CLI-driven paths for env vars are:

- **Option A above** (Render dashboard — recommended).
- **`render.yaml` `envVars`** with `sync: false` (already done in this
  repo — the slots are declared and will be created on next deploy;
  values are still set via the dashboard).
- **Render API directly** (`https://api.render.com/v1/services/{id}/env-vars`)
  — scriptable from any language with HTTP + a Render API key, but
  requires an API key separate from the CLI token.

(The current Render CLI token is also expired — see
`~/.render/cli.yaml` — so `render login` is required before any
`render services` / `render deploys` / `render environments` calls.)

### Option C — `bootstrap_live_auth.py` (after Render env is linked)

If your Render service has a `RENDER_EXTERNAL_URL` or is otherwise
importable, the existing `scripts/bootstrap_live_auth.py` already
supports `--from-vercel` and 1Password sources.  Extend it to support
`--from-render` if needed.

## Frontend (Vercel) — wiring secrets

The Vercel project for `plotlot-v2` needs the public Clerk key and the
server-side Stripe key (for `/api/stripe/checkout`).

### Option A — Vercel dashboard

1. Visit <https://vercel.com/earl562/plotlot-v2/settings/environment-variables>
2. Add:
   - `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` = `pk_test_...` (Production +
     Preview + Development)
   - `CLERK_SECRET_KEY` = `sk_test_...` (server runtime only)
   - `STRIPE_SECRET_KEY` = `sk_test_...`
   - `STRIPE_PRO_PRICE_ID` = `price_...`
   - `NEXT_PUBLIC_APP_URL` = `https://plotlot-v2.vercel.app`
   - `NEXT_PUBLIC_API_URL` = `https://plotlot-api.onrender.com`

### Option B — Vercel CLI

```bash
cd plotlot/plotlot/frontend
vercel link --yes
vercel env add NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY production
# paste value, repeat for preview, development
vercel env add CLERK_SECRET_KEY production
vercel env add STRIPE_SECRET_KEY production
vercel env add STRIPE_PRO_PRICE_ID production
vercel env add NEXT_PUBLIC_APP_URL production
vercel env add NEXT_PUBLIC_API_URL production
```

## Manual smoke test (acceptance criteria)

After all of the above is done, walk through these flows end-to-end:

1. **Sign up**: visit the Vercel frontend, click "Sign in", create a
   Clerk account.
2. **Free tier**: run 6 analyses. The 6th should return HTTP 402 with
   `{"error": "usage_limit_exceeded", "limit": 5}`.
3. **Upgrade**: visit `/billing`, click "Upgrade to Pro", complete the
   Stripe Checkout form with test card `4242 4242 4242 4242`.
4. **Verify webhook**: in the Render logs you should see
   `User <clerk_id> upgraded to Pro (customer=cus_...)`. In Stripe
   dashboard → Webhooks, the event should show 200 OK.
5. **Unlimited**: after refresh, `/billing` should show "Pro" plan and
   analyses should no longer be limited.
6. **Cancel**: in Stripe dashboard → Subscriptions, cancel the test
   subscription. Within seconds the user should revert to Free.

## Verification commands

```bash
# Backend
cd plotlot/plotlot
uv run python scripts/check_auth_readiness.py
uv run pytest tests/unit/test_auth.py tests/unit/test_middleware.py tests/unit/test_billing.py -v
uv run ruff check src/plotlot/api/ tests/unit/test_auth.py tests/unit/test_middleware.py tests/unit/test_billing.py

# Frontend (optional)
cd frontend
npm run lint
npx tsc --noEmit
```

`auth-readiness` should report `READY` for both `clerk_auth` and
`stripe_billing` once all env vars are set.

## Rollback

If something goes wrong, flip `AUTH_ENABLED=false` in Render env to
revert to anonymous access.  Stripe checkout will return 503 if
`STRIPE_SECRET_KEY` is missing.
