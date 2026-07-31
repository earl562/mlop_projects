# Todo7 production identity evidence

| Success criterion | Scenario and invocation | Binary observable | Artifact |
|---|---|---|---|
| Production config fails closed | `PLOTLOT_ENVIRONMENT=production uv run python -c 'import plotlot.config'` | exit 1; Pydantic reports incomplete production identity configuration | `backend-production-missing-config-rejected.log` |
| Clerk JWT verification | Production-mode `pytest tests/security/test_clerk_auth.py tests/security/test_service_principals.py -q` with deterministic local settings | 22 passed | `production-mode-backend-final.log` |
| Issuer/audience/azp/kid/signature/time/revocation/rotation | Deterministic local RSA keys and injected JWKS fetcher in `test_clerk_auth.py` | all rejection cases and rotation pass without network access | `production-mode-backend-final.log` |
| Verified actor defeats request spoofing | Local ASGI request with verified token plus conflicting body/query actor fields | actor is `user_verified` in `tenant_verified` | `production-mode-backend-final.log` |
| HTTP spoof rejection | Live production-mode Uvicorn; `curl -i -X GET /api/v1/subscription/status?... --data '{"user_id":"body_spoof"}'` | HTTP 401 with `WWW-Authenticate: Bearer` | `backend-http-spoof-rejected.log` |
| Roles/capabilities | `PLOTLOT_TEST_AUTH_BYPASS=0 npx playwright test --config tests/auth-playwright.config.ts --project=chromium` | 3 passed in Chromium; Owner/Admin/Analyst/Reviewer/Viewer matrix asserted | `frontend-auth-roles-next15-green.log` |
| Service-principal scope and TTL | `pytest tests/security/test_service_principals.py` | tenant/action mismatch, expiry, revocation, and TTL overflow rejected | `production-mode-backend-final.log` |
| Frontend production startup fails closed | Start standalone Next server without Clerk runtime settings | process exits 1 before serving | `frontend-startup-missing-config-next15.log` |
| Next 15 protection is active | Build output plus middleware manifest inspection | build reports `ƒ Middleware 90.2 kB`; protected `/workspace` is not HTTP 200 and carries Clerk signed-out headers with deterministic non-secret test configuration | `frontend-production-build-next15-middleware.log`, `frontend-protected-route-next15-headers.txt` |
| No production bypass artifact | `rg` forbidden-marker scan over auth source and compiled middleware/instrumentation | no matches | `frontend-source-artifact-forbidden-scan-final.log`, `backend-forbidden-source-scan.log` |
| Backend regression | `uv run pytest tests/unit -q` | 1872 passed | `backend-unit-suite.log` |
| Frontend regression | `npm run test:ui`, `npm run lint`, `npx tsc --noEmit`, production `npm run build` | 30 passed; lint 0 errors; tsc exit 0; build exit 0 | `frontend-vitest-suite.log`, `frontend-lint.log`, `frontend-tsc-next15.log`, `frontend-production-build-next15-middleware.log` |
| Type regression requested by Todo12 | `uv run mypy --follow-imports=silent src/plotlot/storage/models.py` after replacing SQL `func.now()` fallback with a Python UTC datetime | success, no issues | `storage-models-mypy-red.log`, `storage-models-mypy-green.log` |
| No-excuse/LOC | Python and TypeScript no-excuse scripts plus pure-LOC audit | TS: no violations; Python remaining broad-except/oversized-module are pre-existing and not added by Todo7; new modules are under 250 LOC | `typescript-no-excuse-next15-final.log`, `python-no-excuse-final.log`, `python-no-excuse-diff-classification.log`, `python-loc-audit.log`, `typescript-loc-next15-final.log` |
| Cleanup | Remove Playwright/debug artifacts and stop QA servers | no journal/results directories; ports 3997, 3998, 8017 have no listeners | `cleanup-receipt.log` |

All signing material is deterministic test-only data generated in-process. No network secret or live Clerk token is used.
