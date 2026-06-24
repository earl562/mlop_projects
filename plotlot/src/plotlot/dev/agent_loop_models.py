from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum, unique
from pathlib import Path
from typing import Final

CommandResultJson = dict[str, str | int | bool | None]
AgentWorkerPolicyJson = dict[str, str | bool | None]
LoopReportJson = dict[str, str | list[str] | list[CommandResultJson] | list[AgentWorkerPolicyJson]]

OUTPUT_TAIL_CHARS: Final = 4_000
DEFAULT_TIMEOUT_SECONDS: Final = 900
SECRET_ASSIGNMENT_RE: Final = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*=)([^\s]+)"
)
AUTHORIZATION_RE: Final = re.compile(r"(?i)(authorization:\s*)(?:bearer\s+)?([^\s]+)")


@unique
class Phase(StrEnum):
    PLAN = "plan"
    DEBUG = "debug"
    HYGIENE = "hygiene"
    BACKEND = "backend"
    EVAL = "eval"
    FRONTEND = "frontend"
    BROWSER = "browser"
    REVIEW = "review"
    DEPLOY_READINESS = "deploy-readiness"


@unique
class RunStatus(StrEnum):
    PLANNED = "planned"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class LoopConfig:
    repo_root: Path
    app_root: Path
    report_dir: Path
    phases: tuple[Phase, ...]
    stop_on_failure: bool
    plan_only: bool
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    phase: Phase
    argv: tuple[str, ...]
    cwd: Path
    optional: bool = False

    def display(self) -> str:
        return " ".join(self.argv)


@dataclass(frozen=True, slots=True)
class AgentWorkerPolicy:
    phase: Phase
    worker: str
    primary_model: str
    escalation_model: str | None
    purpose: str
    gpt_55_allowed: bool

    def to_json(self) -> AgentWorkerPolicyJson:
        return {
            "phase": self.phase.value,
            "worker": self.worker,
            "primary_model": self.primary_model,
            "escalation_model": self.escalation_model,
            "purpose": self.purpose,
            "gpt_55_allowed": self.gpt_55_allowed,
        }


@dataclass(frozen=True, slots=True)
class CommandResult:
    name: str
    phase: Phase
    command: str
    cwd: str
    status: RunStatus
    exit_code: int | None
    duration_ms: int
    stdout_tail: str
    stderr_tail: str
    optional: bool

    def to_json(self) -> CommandResultJson:
        return {
            "name": self.name,
            "phase": self.phase.value,
            "command": self.command,
            "cwd": self.cwd,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "optional": self.optional,
        }


@dataclass(frozen=True, slots=True)
class LoopReport:
    generated_at: str
    status: RunStatus
    phases: tuple[Phase, ...]
    worker_policies: tuple[AgentWorkerPolicy, ...]
    results: tuple[CommandResult, ...]

    def to_json(self) -> LoopReportJson:
        return {
            "generated_at": self.generated_at,
            "status": self.status.value,
            "phases": [phase.value for phase in self.phases],
            "worker_policies": [policy.to_json() for policy in self.worker_policies],
            "results": [result.to_json() for result in self.results],
        }


def redact_text(value: str) -> str:
    redacted = SECRET_ASSIGNMENT_RE.sub(r"\1<redacted>", value)
    return AUTHORIZATION_RE.sub(r"\1<redacted>", redacted)
