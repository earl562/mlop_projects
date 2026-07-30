from __future__ import annotations

import json
import sys
from collections.abc import Sequence

from pydantic import ValidationError

from plotlot.cli_harness_approvals import approvals_command
from plotlot.cli_harness_calc import calc_command, calculations_command
from plotlot.cli_harness_codex import codex_command
from plotlot.cli_harness_evidence import evidence_command
from plotlot.cli_harness_evals import eval_command
from plotlot.cli_harness_jobs import jobs_command
from plotlot.cli_harness_memory import memory_command
from plotlot.cli_harness_municode import municode_command
from plotlot.cli_harness_reports import claims_command, reports_command
from plotlot.cli_harness_runs import run_command, runs_command
from plotlot.cli_harness_scaffold import scaffold_command
from plotlot.cli_harness_support import option_value, parse_options, source_mode_option
from plotlot.cli_harness_tools import tools_command
from plotlot.cli_harness_tui import tui_command
from plotlot.cli_harness_verification import verification_command
from plotlot.harness.contracts import CountyName, JsonObject
from plotlot.harness.full_harness_registry import list_skill_specs
from plotlot.harness.health import HarnessHealthStatus, collect_harness_health
from plotlot.harness.south_florida_gis import search_south_florida_gis
from plotlot.harness.training_ingestion import discover_training_video_sources
from plotlot.observability.tracing import configure_otel
from plotlot.config import settings


HARNESS_COMMANDS = frozenset(
    {
        "doctor",
        "run",
        "runs",
        "jobs",
        "calc",
        "calculations",
        "evidence",
        "claims",
        "reports",
        "verification",
        "approvals",
        "eval",
        "codex",
        "memory",
        "municode",
        "scaffold",
        "tui",
        "gis",
        "training",
        "skills",
        "tools",
    }
)


def entrypoint() -> None:
    raise SystemExit(main(sys.argv[1:]))


def main(argv: Sequence[str] | None = None) -> int:
    configure_otel(
        settings.otel_service_name,
        settings.otel_service_version,
        console_exporter=settings.otel_console_exporter,
    )
    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in {"--help", "-h"}:
        _print_help()
        return 0
    if args[0] not in HARNESS_COMMANDS:
        from plotlot.cli import main as legacy_main

        legacy_main()
        return 0
    try:
        return _dispatch(args)
    except ValidationError as exc:
        print(json.dumps({"error": "invalid_input", "detail": exc.errors()}))
        return 2
    except ValueError as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
        return 2


def _dispatch(args: list[str]) -> int:
    match args[0]:
        case "doctor":
            return _doctor()
        case "skills":
            return _list_specs(
                "skills", [skill.model_dump(mode="json") for skill in list_skill_specs()]
            )
        case "tools":
            return tools_command(args[1:])
        case "gis":
            return _gis(args[1:])
        case "training":
            return _training(args[1:])
        case "run":
            return run_command(args[1:])
        case "runs":
            return runs_command(args[1:])
        case "jobs":
            return jobs_command(args[1:])
        case "calc":
            return calc_command(args[1:])
        case "calculations":
            return calculations_command(args[1:])
        case "evidence":
            return evidence_command(args[1:])
        case "claims":
            return claims_command(args[1:])
        case "reports":
            return reports_command(args[1:])
        case "verification":
            return verification_command(args[1:])
        case "approvals":
            return approvals_command(args[1:])
        case "eval":
            return eval_command(args[1:])
        case "codex":
            return codex_command(args[1:])
        case "memory":
            return memory_command(args[1:])
        case "municode":
            return municode_command(args[1:])
        case "scaffold":
            return scaffold_command(args[1:])
        case "tui":
            return tui_command(args[1:])
        case unreachable:
            print(json.dumps({"error": "unknown_command", "command": unreachable}))
            return 2


def _doctor() -> int:
    health = collect_harness_health()
    print(
        json.dumps(
            {
                "status": health.status.value,
                "harness_cli": "available",
                "source_mode": "fixture",
                "harness_health": health.model_dump(mode="json"),
            }
        )
    )
    return 0 if health.status == HarnessHealthStatus.OK else 1


def _list_specs(key: str, specs: list[JsonObject]) -> int:
    print(json.dumps({key: specs}))
    return 0


def _gis(args: list[str]) -> int:
    if len(args) < 2 or args[0] != "search":
        print(
            json.dumps({"error": "usage", "usage": "plotlot gis search <query> [--county Broward]"})
        )
        return 2
    query = args[1]
    options = parse_options(args[2:])
    county_value = option_value(options, "--county")
    county = CountyName(county_value) if county_value else None
    mode = source_mode_option(options)
    results = search_south_florida_gis(query, county=county, source_mode=mode)
    print(
        json.dumps(
            {
                "source_mode": mode.value,
                "results": [item.model_dump(mode="json") for item in results],
            }
        )
    )
    return 0


def _training(args: list[str]) -> int:
    if not args or args[0] != "discover":
        print(json.dumps({"error": "usage", "usage": "plotlot training discover [--url URL]"}))
        return 2
    options = parse_options(args[1:])
    url = option_value(options, "--url")
    mode = source_mode_option(options)
    videos = discover_training_video_sources(source_mode=mode, url=url)
    print(
        json.dumps(
            {
                "source_mode": mode.value,
                "videos": [video.model_dump(mode="json") for video in videos],
            }
        )
    )
    return 0


def _print_help() -> None:
    print("Usage:")
    print("  plotlot doctor")
    print("  plotlot run acquisition-memo --address ADDRESS --source-mode fixture --stream")
    print("  plotlot runs events RUN_ID")
    print("  plotlot runs replay RUN_ID")
    print("  plotlot runs export-debug-bundle RUN_ID")
    print(
        "  plotlot jobs create --address ADDRESS --analysis-type acquisition-memo --max-attempts 3"
    )
    print("  plotlot jobs run-next --fixture-failure MESSAGE")
    print("  plotlot calc residual-land-value --json '{...}'")
    print("  plotlot calculations list --run-id RUN_ID")
    print("  plotlot evidence list --run-id RUN_ID")
    print("  plotlot claims list --run-id RUN_ID")
    print("  plotlot reports show REPORT_ID")
    print("  plotlot verification show --report-id REPORT_ID")
    print("  plotlot approvals list --run-id RUN_ID")
    print("  plotlot approvals approve APPROVAL_ID --resolved-by USER")
    print("  plotlot eval run --suite harness")
    print("  plotlot codex goal generate")
    print("  plotlot codex doctor")
    print(
        "  plotlot memory write --workspace-id WORKSPACE_ID --memory-type site_assumption --content TEXT"
    )
    print("  plotlot municode search --jurisdiction miami --query parking")
    print("  plotlot scaffold tool TOOL_NAME --root PATH")
    print("  plotlot tui --screen run-monitor --run-id RUN_ID")
    print("  plotlot gis search zoning --county Broward --source-mode fixture")
    print("  plotlot training discover --url URL --source-mode fixture")
    print("  plotlot skills")
    print("  plotlot tools inspect search_municode")
    print(
        "  plotlot tools call search_municode --run-id RUN_ID --workspace-id WORKSPACE_ID --json '{...}'"
    )


if __name__ == "__main__":
    entrypoint()
