# PlotLot Engineering Contract

This file is the repository-wide source of truth for human and automated contributors. It contains product and engineering rules only. Personal profiles, prospect notes, private business context, tool personalities, and local agent state do not belong in version control.

## Product

PlotLot is an evidence-backed land intelligence platform for zoning research, site feasibility, acquisition lead screening, comparable-sale analysis, and development underwriting.

The active release scope is capability-driven. The priority market families are:

- San Diego County, California
- Miami-Dade County, Florida
- Broward County, Florida
- Palm Beach County and West Palm Beach, Florida
- Mecklenburg County and Charlotte, North Carolina

Do not claim nationwide or uniform county coverage. Each result must describe the capabilities and source coverage actually available for that jurisdiction.

## Repository Layout

```text
plotlot/
├── src/plotlot/          # Python product package
├── tests/                # unit, integration, evaluation, and fixtures
├── frontend/             # canonical Next.js application
├── alembic/              # database migrations
├── scripts/              # deterministic operational tooling
└── docs/                 # current architecture, ADRs, plans, and runbooks
```

`plotlot/frontend/` is the only canonical frontend root. Local AI workspaces such as `.claude`, `.omo`, and `.omx` are ignored and must never be committed.

## Canonical Architecture

The intended dependency direction is:

```text
HTTP / SSE / Chat / MCP / CLI / Multi-agent coordinator
                         |
                         v
                 Application services
                         |
                         v
            Domain rules and deterministic tools
                         |
                         v
       Provider ports / integrations / repositories
```

Transport modules authenticate, validate transport envelopes, and render results. They must not independently implement geocoding, property resolution, ordinance retrieval, comparable-sale qualification, approvals, evidence persistence, calculations, or report generation.

### Analysis

One transport-neutral analysis service must ultimately power JSON, SSE, chat, MCP, CLI, and specialist-agent calls. Until migration is complete, compatibility adapters are allowed only when protected by parity tests and an explicit removal plan.

### Tool execution

`ToolContract` metadata and the governed harness runtime are canonical for tool names, input schemas, risk classes, budgets, and approval behavior. Every transport must use the same application-level execution transaction for approval validation, runtime invocation, evidence, artifacts, audit records, and rollback.

### Multi-agent workflows

Specialist agents are least-privilege capability manifests, not unrestricted autonomous chatbots. The coordinator may schedule independent tasks concurrently, but every tool call remains policy-gated. Missing facts, evidence, or assumptions must become explicit review items rather than model guesses.

## Trust Rules

Every decision-relevant value must be identified as one of:

- verified fact with source and evidence identifier
- deterministic calculation with named inputs
- user-supplied assumption
- labeled estimate with confidence and basis
- unknown

The LLM may plan, summarize, compare, and explain. It may not invent parcel facts, zoning standards, comparable sales, prices, yields, residual values, or external approvals.

Comparable-sale and acquisition recommendations must abstain when evidence is insufficient. External writes and outbound communications require durable approval through the canonical policy path.

## Data and Privacy

- Never commit `.env`, OAuth credentials, API keys, tokens, local databases, or connector exports.
- Lead evaluation fixtures may contain property facts but no owner phone, email, mailing-contact fields, or free-text outreach notes.
- Generated browser output, screenshots, traces, and benchmark results belong in ignored paths or GitHub Actions artifacts.
- Source freshness, authority, retrieval time, and confidence must remain attached to evidence.

## Python Standards

- Python 3.12 or newer.
- Type hints on public and internal signatures.
- Pydantic models at application and transport boundaries.
- Async I/O with `httpx.AsyncClient`, async database sessions, and bounded timeouts.
- Deterministic domain code should remain synchronous when it performs no I/O.
- Use logging or structured tracing in library code; CLI scripts may print user-facing output.
- Do not add module-level mutable caches without an explicit lifecycle, bound, and test.
- Avoid raw dictionaries across stable application boundaries unless the external payload is intentionally opaque.

## TypeScript Standards

- Next.js App Router, React 19, and Tailwind CSS 4.
- Feature-owned or generated API contracts; do not grow another monolithic manually mirrored type file.
- Page components compose features. Data fetching, stream parsing, persistence, and reducers belong in focused modules or hooks.
- Preserve accessibility, loading, error, empty, and degraded states.

## Test-Driven Changes

Every behavior change or refactor starts with a failing test that demonstrates the desired contract. Confirm the test fails for the intended reason, implement the minimum change, then run the focused and broader regression suites.

Required local backend gates:

```bash
cd plotlot
uv sync --frozen --extra dev --extra eval
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/plotlot/ --no-error-summary
uv run pytest tests/unit/ -q
```

Required frontend gates:

```bash
cd plotlot/frontend
npm ci
npm run lint
npm run build
npm run test:ui
npm run test:e2e:no-db
```

Database-backed and live-provider tests require their documented services and credentials. A live external outage remains visible as a health failure; it must not be hidden by skipping or weakening deterministic tests.

## Branch and Commit Discipline

- `main` is protected production and must remain deployable.
- `cpt-pro` is the current integration line for the production harness program.
- Feature and cleanup work uses isolated branches based on the intended integration line.
- Keep commits narrow, reviewable, and attributable to the repository owner.
- Do not use force pushes on shared integration branches.
- Do not merge a draft or failing pull request into `main`.
- Record exact commands and terminal CI conclusions before claiming completion.

## Documentation

Keep only current, operationally useful documents:

- architecture and flow contracts
- ADRs
- implementation plans for active work
- connector contracts
- runbooks
- status records tied to exact commits and workflow runs

Delete obsolete handoffs and generated session narratives rather than moving them into an archive directory. Git history is the archive.

## Definition of a Production-Ready Change

A change is production-ready only when:

1. Its user-visible and failure behavior is covered by tests.
2. It follows the canonical analysis and tool-execution boundaries.
3. It preserves evidence, approval, and tenant isolation.
4. Ruff, formatting, mypy, unit, frontend, and applicable browser gates pass.
5. Live-provider or deployment dependencies have explicit terminal evidence.
6. The diff contains no credentials, personal context, contact data, or generated artifacts.
