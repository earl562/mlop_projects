from __future__ import annotations

import json
from pathlib import Path

from plotlot.cli_harness_support import option_value, parse_options
from plotlot.harness.scaffold import ScaffoldTargetExistsError, scaffold_tool


def scaffold_command(args: list[str]) -> int:
    try:
        match args:
            case ["tool", tool_name, *raw_options]:
                return _scaffold_tool(tool_name, raw_options)
            case _:
                return _usage()
    except ScaffoldTargetExistsError as exc:
        print(json.dumps({"error": "scaffold_target_exists", "path": str(exc.path)}))
        return 1
    except ValueError as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
        return 2


def _scaffold_tool(tool_name: str, raw_options: list[str]) -> int:
    options = parse_options(raw_options)
    root = Path(option_value(options, "--root") or ".")
    manifest = scaffold_tool(tool_name, root, force="--force" in options.flags)
    print(json.dumps({"scaffold": manifest.model_dump(mode="json")}))
    return 0


def _usage() -> int:
    print(
        json.dumps(
            {
                "error": "usage",
                "usage": "plotlot scaffold tool TOOL_NAME [--root PATH] [--force]",
            }
        )
    )
    return 2
