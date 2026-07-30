# Codex CLI Reference

PlotLot treats Codex CLI as an optional local developer/operator assistant. It is not
a production dependency and must not bypass PlotLot policy, evidence, verification,
authorization, or source-permission rules.

## Commands

Generate the PlotLot harness goal prompt:

```bash
uv run plotlot codex goal generate
```

Print the generated prompt as JSON:

```bash
uv run plotlot codex goal print
```

Inspect a local Codex checkout used as an architecture reference:

```bash
uv run plotlot codex inspect-reference --path ../codex
```

Check whether the local Codex binary is available:

```bash
uv run plotlot codex doctor
```

Run Codex non-interactively with a PlotLot goal file:

```bash
uv run plotlot codex run --goal docs/goals/full-harness.goal.md
```

Run the same lane against an explicit legacy model:

```bash
uv run plotlot codex run --goal docs/goals/full-harness.goal.md -m gpt-5.2
```

`plotlot codex run` uses the local `codex exec -` stdin path and forwards `-m`/`--model`
to the local Codex CLI as `codex -m <model_name> exec ...`. It reports
`production_dependency: false` in success and failure paths.

Legacy model selection can also be pinned in Codex config instead of passing `-m` on
every invocation. PlotLot's reference lane explicitly recognizes `gpt-5.2` for that
legacy-model path.

## Rules

- Do not vendor Codex CLI into PlotLot.
- Do not make Codex CLI required for production runtime.
- Do not use Codex CLI to access protected sources, publish reports, alter evidence, or
  bypass approval gates.
- Keep generated goal files under `docs/goals/`.
- Treat Codex output as implementation assistance, not source evidence.
