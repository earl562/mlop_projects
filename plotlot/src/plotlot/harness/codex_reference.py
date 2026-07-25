from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

from pydantic import Field

from plotlot.harness.contracts import JsonObject
from plotlot.harness.contracts.base import HarnessContract

DEFAULT_CODEX_GOAL_PATH = Path("docs/goals/full-harness.goal.md")
LEGACY_CODEX_MODELS: Final[tuple[str, ...]] = ("gpt-5.2",)
DEFAULT_LEGACY_CODEX_MODEL: Final[str] = LEGACY_CODEX_MODELS[0]


class CodexReferenceConfig(HarnessContract):
    goal_path: Path = DEFAULT_CODEX_GOAL_PATH
    force: bool = False


class CodexGoalGenerationResult(HarnessContract):
    goal_path: Path
    created: bool
    skipped_reason: str | None = None


class CodexReferenceInspection(HarnessContract):
    path: Path
    exists: bool
    status: str = Field(min_length=1)
    detected_files: list[str] = Field(default_factory=list)
    production_dependency: bool = False
    metadata: JsonObject = Field(default_factory=dict)


class CodexDoctorResult(HarnessContract):
    status: str = Field(min_length=1)
    codex_path: str | None = None
    production_dependency: bool = False
    guidance: str = Field(min_length=1)


def codex_goal_template() -> str:
    return """# PlotLot Full Harness Goal

Use Codex CLI as an optional developer/operator assistant for PlotLot harness work.

## Operating Rules

- PlotLot owns the production runtime, policy engine, evidence ledger, source catalog,
  calculators, verifier, reports, CLI, API, workers, and UI surfaces.
- Codex CLI is optional and not a production runtime dependency.
- Do not vendor Codex CLI into PlotLot.
- Do not let Codex CLI bypass PlotLot policy, evidence, verification, or authorization.
- Use Codex for local repo inspection, implementation assistance, and operator prompts only.

## Suggested Command

```bash
codex --ask-for-approval on-request "$(cat docs/goals/full-harness.goal.md)"
```

- Legacy Codex models can be selected with `codex -m gpt-5.2 ...` when an operator
  needs that lane explicitly.
- The same model can be pinned through Codex config instead of per-command flags.

## Deliverables To Preserve

- Event-driven harness runs with ordered replayable events.
- Source-grounded evidence, claims, calculations, reports, and verification.
- South Florida GIS provider adapters under one shared source lane.
- Training ingestion with permitted transcripts, structured concepts, and workflow mappings.
- CLI/API/frontend/TUI/MCP surfaces using shared contracts and registries.
"""


def generate_codex_goal(config: CodexReferenceConfig) -> CodexGoalGenerationResult:
    path = config.goal_path
    if path.exists() and not config.force:
        return CodexGoalGenerationResult(
            goal_path=path,
            created=False,
            skipped_reason="target_exists",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(codex_goal_template(), encoding="utf-8")
    return CodexGoalGenerationResult(goal_path=path, created=True)


def read_codex_goal(path: Path = DEFAULT_CODEX_GOAL_PATH) -> str:
    return path.read_text(encoding="utf-8")


def inspect_codex_reference(path: Path) -> CodexReferenceInspection:
    if not path.exists():
        return CodexReferenceInspection(
            path=path,
            exists=False,
            status="missing",
            metadata={"expected": "Codex CLI checkout path"},
        )
    detected = [
        name
        for name in ["README.md", "package.json", "Cargo.toml", "codex-rs"]
        if (path / name).exists()
    ]
    return CodexReferenceInspection(
        path=path,
        exists=True,
        status="reference_available" if detected else "unrecognized_checkout",
        detected_files=detected,
        metadata={"detected_file_count": len(detected)},
    )


def codex_doctor() -> CodexDoctorResult:
    codex_path = shutil.which("codex")
    if codex_path is None:
        return CodexDoctorResult(
            status="optional_missing",
            guidance="Install Codex CLI only for local operator workflows; PlotLot does not require it.",
        )
    return CodexDoctorResult(
        status="available",
        codex_path=codex_path,
        guidance="Codex CLI is available for optional local operator workflows.",
    )
