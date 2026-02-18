# EP Engineering Lab — Monorepo

## Structure

This is a monorepo for Earl Perry's ML/LLMOps portfolio. Each project lives in its own directory with its own `pyproject.toml`, `Dockerfile`, and CI config.

| Directory | Project | Status |
|-----------|---------|--------|
| `plotlot/` | PlotLot v2 — AI zoning analysis | Active |
| `mangoai/` | MangoAI — Agricultural vision | Planned |
| `agent-forge/` | Agent Forge — Multi-agent tools | Planned |
| `agent-eval/` | Agent Eval — LLM evaluation | Planned |

## Rules

1. **Use Claude Sonnet for email generation** as specified in global config.
2. Each project has its own `CLAUDE.md` with project-specific instructions.
3. CI workflows use `working-directory` to scope to the right project.
