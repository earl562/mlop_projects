from __future__ import annotations

import os
import shutil
from enum import StrEnum
from pathlib import Path

from pydantic import Field

from plotlot.harness.approval_store import default_approval_ledger_path
from plotlot.harness.calculation_store import default_calculation_ledger_path
from plotlot.harness.cost_assumption_source import load_cost_assumption_source_catalog
from plotlot.harness.contracts import JsonObject, SourceMode
from plotlot.harness.contracts.base import HarnessContract
from plotlot.harness.evidence_store import default_evidence_ledger_path
from plotlot.harness.full_harness_registry import (
    list_agent_role_specs,
    list_skill_specs,
    list_tool_specs,
)
from plotlot.harness.job_queue import default_harness_job_store_path
from plotlot.harness.memory_store import default_memory_store_path
from plotlot.harness.municode_source import load_municode_source_catalog
from plotlot.harness.report_store import default_report_ledger_path
from plotlot.harness.run_store import default_harness_store_path
from plotlot.harness.south_florida_gis import load_south_florida_gis_source_catalog
from plotlot.harness.tool_call_store import default_tool_call_ledger_path
from plotlot.harness.training_ingestion import discover_training_video_sources
from plotlot.harness.verification_store import default_verification_ledger_path


class HarnessHealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"


class HarnessHealthCheck(HarnessContract):
    name: str = Field(min_length=1)
    status: HarnessHealthStatus
    reason: str = Field(min_length=1)
    metadata: JsonObject = Field(default_factory=dict)


class HarnessHealthReport(HarnessContract):
    status: HarnessHealthStatus
    checks: list[HarnessHealthCheck]
    metrics: JsonObject = Field(default_factory=dict)


def collect_harness_health() -> HarnessHealthReport:
    checks = [
        _registry_check(),
        _source_catalog_check(),
        _cost_assumption_catalog_check(),
        _municode_catalog_check(),
        _training_fixture_check(),
        _local_store_paths_check(),
        _queue_check(),
        _cli_check(),
        _codex_optional_check(),
    ]
    return HarnessHealthReport(
        status=_rollup_status(checks),
        checks=checks,
        metrics=_health_metrics(checks),
    )


def filter_harness_health(names: set[str]) -> HarnessHealthReport:
    report = collect_harness_health()
    checks = [check for check in report.checks if check.name in names]
    return HarnessHealthReport(
        status=_rollup_status(checks),
        checks=checks,
        metrics=_health_metrics(checks),
    )


def _registry_check() -> HarnessHealthCheck:
    skills = list_skill_specs()
    roles = list_agent_role_specs()
    tools = list_tool_specs()
    ready = bool(skills and roles and tools)
    return HarnessHealthCheck(
        name="registries",
        status=HarnessHealthStatus.OK if ready else HarnessHealthStatus.ERROR,
        reason="registries_loaded" if ready else "registry_missing_entries",
        metadata={
            "skill_count": len(skills),
            "agent_role_count": len(roles),
            "tool_count": len(tools),
        },
    )


def _source_catalog_check() -> HarnessHealthCheck:
    sources = load_south_florida_gis_source_catalog(SourceMode.FIXTURE)
    providers = sorted({str(source.provider) for source in sources})
    ready = bool(sources)
    return HarnessHealthCheck(
        name="south_florida_gis_catalog",
        status=HarnessHealthStatus.OK if ready else HarnessHealthStatus.ERROR,
        reason="fixture_catalog_loaded" if ready else "fixture_catalog_empty",
        metadata={
            "source_count": len(sources),
            "provider_count": len(providers),
            "providers": ",".join(providers),
        },
    )


def _municode_catalog_check() -> HarnessHealthCheck:
    sources = load_municode_source_catalog(SourceMode.FIXTURE)
    ready = bool(sources)
    return HarnessHealthCheck(
        name="municode_fixture_catalog",
        status=HarnessHealthStatus.OK if ready else HarnessHealthStatus.ERROR,
        reason="municode_fixtures_loaded" if ready else "municode_fixtures_empty",
        metadata={"source_count": len(sources), "provider": "municode"},
    )


def _cost_assumption_catalog_check() -> HarnessHealthCheck:
    sources = load_cost_assumption_source_catalog(SourceMode.FIXTURE)
    ready = bool(sources)
    return HarnessHealthCheck(
        name="cost_assumption_fixture_catalog",
        status=HarnessHealthStatus.OK if ready else HarnessHealthStatus.ERROR,
        reason="cost_assumption_fixtures_loaded" if ready else "cost_assumption_fixtures_empty",
        metadata={"source_count": len(sources), "provider": "plotlot_market_profile"},
    )


def _training_fixture_check() -> HarnessHealthCheck:
    videos = discover_training_video_sources(source_mode=SourceMode.FIXTURE)
    ready = bool(videos)
    return HarnessHealthCheck(
        name="training_fixture_catalog",
        status=HarnessHealthStatus.OK if ready else HarnessHealthStatus.ERROR,
        reason="training_fixtures_loaded" if ready else "training_fixtures_empty",
        metadata={"video_count": len(videos)},
    )


def _local_store_paths_check() -> HarnessHealthCheck:
    paths = {
        "run_store": default_harness_store_path(),
        "job_store": default_harness_job_store_path(),
        "evidence_store": default_evidence_ledger_path(),
        "report_store": default_report_ledger_path(),
        "calculation_store": default_calculation_ledger_path(),
        "verification_store": default_verification_ledger_path(),
        "approval_store": default_approval_ledger_path(),
        "memory_store": default_memory_store_path(),
        "tool_call_store": default_tool_call_ledger_path(),
    }
    readiness = {name: _path_parent_writable(path) for name, path in paths.items()}
    ready = all(readiness.values())
    return HarnessHealthCheck(
        name="local_store_paths",
        status=HarnessHealthStatus.OK if ready else HarnessHealthStatus.DEGRADED,
        reason="store_paths_ready" if ready else "store_path_parent_not_writable",
        metadata={
            **{name: str(path) for name, path in paths.items()},
            **{f"{name}_writable": value for name, value in readiness.items()},
        },
    )


def _queue_check() -> HarnessHealthCheck:
    path = default_harness_job_store_path()
    ready = _path_parent_writable(path)
    return HarnessHealthCheck(
        name="queue",
        status=HarnessHealthStatus.OK if ready else HarnessHealthStatus.DEGRADED,
        reason="local_json_queue_ready" if ready else "queue_store_parent_not_writable",
        metadata={
            "mode": "local_json_single_worker",
            "job_store": str(path),
        },
    )


def _cli_check() -> HarnessHealthCheck:
    return HarnessHealthCheck(
        name="cli",
        status=HarnessHealthStatus.OK,
        reason="harness_cli_available",
        metadata={
            "commands": ["doctor", "run", "runs", "approvals", "scaffold", "tui", "gis", "training"]
        },
    )


def _codex_optional_check() -> HarnessHealthCheck:
    codex_path = shutil.which("codex")
    return HarnessHealthCheck(
        name="codex_optional",
        status=HarnessHealthStatus.OK,
        reason="codex_cli_available" if codex_path else "codex_cli_optional_missing",
        metadata={"available": bool(codex_path), "path": codex_path or ""},
    )


def _path_parent_writable(path: Path) -> bool:
    parent = path.expanduser().parent
    existing = _nearest_existing_parent(parent)
    return existing.exists() and os.access(existing, os.W_OK)


def _nearest_existing_parent(path: Path) -> Path:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def _rollup_status(checks: list[HarnessHealthCheck]) -> HarnessHealthStatus:
    if not checks:
        return HarnessHealthStatus.ERROR
    statuses = {check.status for check in checks}
    if HarnessHealthStatus.ERROR in statuses:
        return HarnessHealthStatus.ERROR
    if HarnessHealthStatus.DEGRADED in statuses:
        return HarnessHealthStatus.DEGRADED
    return HarnessHealthStatus.OK


def _health_metrics(checks: list[HarnessHealthCheck]) -> JsonObject:
    registry = next((check for check in checks if check.name == "registries"), None)
    source = next((check for check in checks if check.name == "south_florida_gis_catalog"), None)
    municode = next((check for check in checks if check.name == "municode_fixture_catalog"), None)
    training = next((check for check in checks if check.name == "training_fixture_catalog"), None)
    return {
        "check_count": len(checks),
        "skill_count": _metric_int(registry, "skill_count"),
        "tool_count": _metric_int(registry, "tool_count"),
        "gis_source_count": _metric_int(source, "source_count"),
        "municode_source_count": _metric_int(municode, "source_count"),
        "training_video_count": _metric_int(training, "video_count"),
    }


def _metric_int(check: HarnessHealthCheck | None, key: str) -> int:
    if check is None:
        return 0
    value = check.metadata.get(key)
    return value if isinstance(value, int) else 0
