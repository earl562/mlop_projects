from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Final

from plotlot.cli_harness_support import option_value, parse_options
from plotlot.harness.codex_reference import (
    CodexReferenceConfig,
    DEFAULT_LEGACY_CODEX_MODEL,
    codex_doctor,
    generate_codex_goal,
    inspect_codex_reference,
    read_codex_goal,
)

_MODEL_FLAGS: Final[frozenset[str]] = frozenset({"-m", "--model"})


def codex_command(args: list[str]) -> int:
    if not args:
        return _usage()
    match args[0]:
        case "goal":
            return _goal_command(args[1:])
        case "doctor":
            doctor = codex_doctor()
            print(json.dumps(doctor.model_dump(mode="json")))
            return 0
        case "inspect-reference":
            options = parse_options(args[1:])
            path = option_value(options, "--path")
            if path is None:
                return _usage()
            inspection = inspect_codex_reference(Path(path))
            print(json.dumps(inspection.model_dump(mode="json")))
            return 0 if inspection.exists else 1
        case "run":
            return _run_command(args[1:])
        case _:
            return _usage()


def _goal_command(args: list[str]) -> int:
    if not args:
        return _usage()
    options = parse_options(args[1:])
    path = Path(option_value(options, "--path") or "docs/goals/full-harness.goal.md")
    match args[0]:
        case "generate":
            result = generate_codex_goal(
                CodexReferenceConfig(goal_path=path, force="--force" in options.flags)
            )
            print(json.dumps(result.model_dump(mode="json")))
            return 0
        case "print":
            try:
                content = read_codex_goal(path)
            except FileNotFoundError:
                print(json.dumps({"error": "goal_not_found", "goal_path": str(path)}))
                return 1
            print(json.dumps({"goal_path": str(path), "content": content}))
            return 0
        case _:
            return _usage()


def _run_command(args: list[str]) -> int:
    options = parse_options(args)
    goal_path = option_value(options, "--goal")
    if goal_path is None:
        return _usage()
    selected_model = _model_option(args)
    doctor = codex_doctor()
    if doctor.codex_path is None:
        print(
            json.dumps(
                {
                    "error": "codex_cli_unavailable",
                    "production_dependency": False,
                    "goal_path": goal_path,
                }
            )
        )
        return 1
    try:
        prompt = read_codex_goal(Path(goal_path))
    except FileNotFoundError:
        print(json.dumps({"error": "goal_not_found", "goal_path": goal_path}))
        return 1
    command = _codex_run_command(doctor.codex_path, selected_model)
    try:
        completed = subprocess.run(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(
            json.dumps(
                {
                    "error": "codex_run_timeout",
                    "production_dependency": False,
                    "goal_path": goal_path,
                }
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": "completed" if completed.returncode == 0 else "failed",
                "exit_code": completed.returncode,
                "production_dependency": False,
                "goal_path": goal_path,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
    )
    return completed.returncode


def _model_option(args: list[str]) -> str | None:
    index = 0
    while index < len(args):
        token = args[index]
        if token in _MODEL_FLAGS and index + 1 < len(args):
            return args[index + 1]
        index += 1
    return None


def _codex_run_command(codex_path: str, model: str | None) -> list[str]:
    command = [codex_path]
    if model is not None:
        command.extend(["-m", model])
    command.extend(["exec", "--cd", str(Path.cwd()), "-"])
    return command


def _usage() -> int:
    print(
        json.dumps(
            {
                "error": "usage",
                "usage": (
                    "plotlot codex <goal generate|goal print|run|inspect-reference|doctor>"
                    f" [run --goal PATH [-m {DEFAULT_LEGACY_CODEX_MODEL}]]"
                ),
            }
        )
    )
    return 2
