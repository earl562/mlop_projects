# Authenticated Test Matrix

PlotLot has two levels of local confidence:

1. **Deterministic local success** — no external credentials required.
2. **Authenticated/live success** — requires credentials and sometimes running local services.

Run the deterministic gate first:

```bash
make verify-local
```

Then inspect live/auth readiness without printing secrets:

```bash
make auth-readiness
# or
python3 scripts/check_auth_readiness.py --json
```

Programmatically populate local `.env` values from CLIs:

```bash
python3 scripts/bootstrap_live_auth.py --help
```

Common examples:

```bash
# 1) Pull known keys from linked Vercel project (frontend/) into root .env
python3 scripts/bootstrap_live_auth.py --from-vercel --vercel-environment development

# 2) Copy local shell env values into .env
python3 scripts/bootstrap_live_auth.py --from-env GEOCODIO_API_KEY --from-env JINA_API_KEY

# 3) Enable Codex OAuth fallback for live agent lanes
python3 scripts/bootstrap_live_auth.py --enable-codex-oauth
```

To make missing credential-backed lanes fail explicitly:

```bash
bash scripts/verify_local_success.sh --strict-auth --skip-browser --skip-build
```

## Credential groups

| Group | Purpose | Required values |
| --- | --- | --- |
| `database_backed_e2e` | DB-backed frontend e2e and backend smoke tests | `DATABASE_URL` plus reachable Postgres (`make db-up` for local Docker DB) |
| `llm_agent` | Live chat, LLM extraction fallback, live evals | one of `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `OPENAI_ACCESS_TOKEN`, `NVIDIA_API_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, or Codex OAuth with `PLOTLOT_USE_CODEX_OAUTH=1` and an existing `PLOTLOT_CODEX_AUTH_FILE` |
| `geocoding` | Live Geocodio address lookup | `GEOCODIO_API_KEY` |
| `web_search` | Agent web-source search through Jina | `JINA_API_KEY` |
| `google_workspace` | Google Docs/Sheets creation tools | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` |
| `google_rendering` | Building/concept rendering endpoints | `GOOGLE_API_KEY` |
| `google_maps_enhanced` | Optional Google Maps SDK imagery/street-view enhancements | optional `NEXT_PUBLIC_GOOGLE_MAPS_KEY` (fallback exists without key) |
| `stripe_billing` | Checkout and webhook verification | `STRIPE_SECRET_KEY`, `STRIPE_PRO_PRICE_ID`, `STRIPE_WEBHOOK_SECRET` |
| `clerk_auth` | Real authenticated sessions/JWT verification | `CLERK_JWKS_URL` when `AUTH_ENABLED=true`; frontend sign-in also needs `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` |
| `fal_video` | Video generation API route | `FAL_KEY` |
| `huggingface_embeddings` | Hugging Face inference-backed embeddings path | `HF_TOKEN` |

## Suggested completion ladder

1. Run `make verify-local` and fix deterministic failures first.
2. Run `make auth-readiness` and decide which live lanes matter for the change.
3. Start local DB when DB-backed lanes matter:

   ```bash
   make db-up
   ```

4. Run DB-backed frontend lanes when API + DB are running:

   ```bash
   cd frontend
   npm run test:e2e:db
   ```

5. Run the live served frontend agent lane when `llm_agent` is ready. This starts the local backend when needed, serves the frontend through Playwright, sends a real browser prompt to `/api/v1/chat`, and verifies the SSE response reaches the UI:

   ```bash
   make live-agent-e2e
   # or, if the backend is already running:
   cd frontend
   npm run test:e2e:live-agent
   ```

6. Run live backend tests only when credentials and network access are intentionally available:

   ```bash
   uv run pytest tests/integration -m live -v
   uv run pytest tests/eval/test_eval_live.py -m "eval and e2e" -v
   ```

7. For Google Workspace, run the OAuth helper before live Docs/Sheets tests:

   ```bash
   uv run python scripts/setup_google_auth.py
   ```

## Safety rules

- Never print secret values in logs or commits.
- Use `.env` for local values; keep `.env.example` placeholders only.
- Keep deterministic local success green even when live credentials are missing.
- Use `--strict-auth` only when the goal is to prove all credential-backed lanes are ready.
