from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import assert_never

from plotlot.dev.agent_loop_commands import PROFILE_PHASES, build_commands, profile_phases
from plotlot.dev.agent_loop_models import (
    OUTPUT_TAIL_CHARS,
    CommandResult,
    CommandSpec,
    LoopConfig,
    LoopReport,
    RunStatus,
    redact_text,
)


def execute_loop(config: LoopConfig) -> LoopReport:
    results: list[CommandResult] = []
    pending_commands = build_commands(config)
    for command in pending_commands:
        if config.plan_only:
            results.append(_planned_result(command))
            continue

        result = _run_command(command, config.timeout_seconds)
        results.append(result)
        if config.stop_on_failure and result.status == RunStatus.FAILED:
            results.extend(_skipped_results_after_failure(pending_commands, command))
            break

    return LoopReport(
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        status=_overall_status(tuple(results)),
        phases=config.phases,
        results=tuple(results),
    )


def write_report(report: LoopReport, report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"agent-loop-{_timestamp_slug()}.json"
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report.to_json(), handle, indent=2)
        handle.write("\n")
    return report_path


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PlotLot's local agent work loop.")
    parser.add_argument(
        "--profile",
        choices=tuple(PROFILE_PHASES),
        default="smoke",
        help="Loop profile to run.",
    )
    parser.add_argument(
        "--report-dir",
        default=".omo/evidence/agent-loop",
        help="Directory for sanitized JSON evidence reports.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Write the command plan without executing commands.",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue later phases after a failing required command.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    app_root = Path(__file__).resolve().parents[3]
    repo_root = app_root.parent
    config = LoopConfig(
        repo_root=repo_root,
        app_root=app_root,
        report_dir=app_root / args.report_dir,
        phases=profile_phases(args.profile),
        stop_on_failure=not args.continue_on_failure,
        plan_only=args.plan_only,
    )
    report = execute_loop(config)
    report_path = write_report(report, config.report_dir)
    print(f"agent loop status: {report.status.value}")
    print(f"evidence report: {report_path}")
    return 0 if report.status in {RunStatus.PASSED, RunStatus.PLANNED} else 1


def _run_command(command: CommandSpec, timeout_seconds: int) -> CommandResult:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command.argv,
            cwd=command.cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        status = RunStatus.SKIPPED if command.optional else RunStatus.FAILED
        return _result_from_failure(command, status, 127, "", str(exc), started)
    except subprocess.TimeoutExpired as exc:
        return _result_from_failure(
            command,
            RunStatus.FAILED,
            124,
            _timeout_stream(exc.stdout),
            _timeout_stream(exc.stderr),
            started,
        )

    status = RunStatus.PASSED if completed.returncode == 0 else RunStatus.FAILED
    if command.optional and completed.returncode != 0:
        status = RunStatus.SKIPPED

    return CommandResult(
        name=command.name,
        phase=command.phase,
        command=command.display(),
        cwd=str(command.cwd),
        status=status,
        exit_code=completed.returncode,
        duration_ms=_duration_ms(started),
        stdout_tail=_tail(completed.stdout),
        stderr_tail=_tail(completed.stderr),
        optional=command.optional,
    )


def _planned_result(command: CommandSpec) -> CommandResult:
    return CommandResult(
        name=command.name,
        phase=command.phase,
        command=command.display(),
        cwd=str(command.cwd),
        status=RunStatus.PLANNED,
        exit_code=None,
        duration_ms=0,
        stdout_tail="",
        stderr_tail="",
        optional=command.optional,
    )


def _skipped_results_after_failure(
    commands: tuple[CommandSpec, ...],
    failed_command: CommandSpec,
) -> tuple[CommandResult, ...]:
    skipped: list[CommandResult] = []
    should_skip = False
    for command in commands:
        if should_skip:
            skipped.append(_skipped_after_failure(command))
        if command == failed_command:
            should_skip = True
    return tuple(skipped)


def _skipped_after_failure(command: CommandSpec) -> CommandResult:
    return CommandResult(
        name=command.name,
        phase=command.phase,
        command=command.display(),
        cwd=str(command.cwd),
        status=RunStatus.SKIPPED,
        exit_code=None,
        duration_ms=0,
        stdout_tail="",
        stderr_tail="blocked by earlier failure",
        optional=command.optional,
    )


def _result_from_failure(
    command: CommandSpec,
    status: RunStatus,
    exit_code: int,
    stdout: str,
    stderr: str,
    started: float,
) -> CommandResult:
    return CommandResult(
        name=command.name,
        phase=command.phase,
        command=command.display(),
        cwd=str(command.cwd),
        status=status,
        exit_code=exit_code,
        duration_ms=_duration_ms(started),
        stdout_tail=_tail(stdout),
        stderr_tail=_tail(stderr),
        optional=command.optional,
    )


def _overall_status(results: tuple[CommandResult, ...]) -> RunStatus:
    if all(result.status == RunStatus.PLANNED for result in results):
        return RunStatus.PLANNED
    if any(result.status == RunStatus.FAILED for result in results):
        return RunStatus.FAILED
    return RunStatus.PASSED


def _tail(value: str) -> str:
    return redact_text(value[-OUTPUT_TAIL_CHARS:])


def _timeout_stream(value: str | bytes | None) -> str:
    match value:
        case None:
            return ""
        case bytes():
            return value.decode("utf-8", errors="replace")
        case str():
            return value
        case unreachable:
            assert_never(unreachable)


def _duration_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _timestamp_slug() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
