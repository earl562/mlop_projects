from __future__ import annotations

import json

from plotlot.cli_harness_support import (
    assumptions_from_options,
    option_value,
    parse_options,
    source_mode_option,
)
from plotlot.harness.contracts import ExecutionMode, RunId
from plotlot.harness.debug_bundle import default_debug_bundle_stores, export_debug_bundle
from plotlot.harness.fixture_runs import FixtureDealRunRequest, run_deal_analysis
from plotlot.harness.run_persistence import default_fixture_run_persistence_stores, persist_fixture_run_result
from plotlot.harness.run_store import (
    HarnessRunCancellationRequest,
    HarnessRunNotFoundError,
    RunCancellationBlockedError,
    default_harness_run_store,
)


def run_command(args: list[str]) -> int:
    if not args:
        print(json.dumps({"error": "usage", "usage": "plotlot run acquisition-memo --address ADDRESS"}))
        return 2
    analysis_type = args[0].replace("-", "_")
    options = parse_options(args[1:])
    address = option_value(options, "--address")
    if address is None:
        print(json.dumps({"error": "missing_address"}))
        return 2
    source_mode = source_mode_option(options)
    request = FixtureDealRunRequest(
        address=address,
        analysis_type=analysis_type,
        source_mode=source_mode,
        execution_mode=ExecutionMode.CLI,
        assumptions=assumptions_from_options(options),
    )
    result = run_deal_analysis(request)
    persist_fixture_run_result(
        result,
        default_fixture_run_persistence_stores(),
    )
    if "--stream" in options.flags:
        for event in result.events:
            print(json.dumps(event.model_dump(mode="json")))
    payload = result.model_dump(mode="json")
    payload.pop("events", None)
    print(json.dumps(payload))
    return 0 if result.status == "completed" else 1


def runs_command(args: list[str]) -> int:
    if not args:
        print(json.dumps({"error": "usage", "usage": _runs_usage()}))
        return 2
    store = default_harness_run_store()
    try:
        match args[0]:
            case "list":
                print(json.dumps({"runs": [run.model_dump(mode="json") for run in store.list_runs()]}))
                return 0
            case "show" if len(args) >= 2:
                print(json.dumps(store.get_run(RunId(args[1])).model_dump(mode="json")))
                return 0
            case "events" if len(args) >= 2:
                events = [event.model_dump(mode="json") for event in store.get_events(RunId(args[1]))]
                print(json.dumps({"run_id": args[1], "events": events}))
                return 0
            case "replay" if len(args) >= 2:
                print(json.dumps(store.replay_run(RunId(args[1])).model_dump(mode="json")))
                return 0
            case "cancel" if len(args) >= 2:
                options = parse_options(args[2:])
                result = store.cancel_run(
                    HarnessRunCancellationRequest(
                        run_id=RunId(args[1]),
                        actor_user_id=option_value(options, "--actor-user-id") or "cli",
                        reason=option_value(options, "--reason") or "Cancellation requested.",
                        execution_mode=ExecutionMode.CLI,
                    )
                )
                print(json.dumps(result.model_dump(mode="json")))
                return 0
            case "export-debug-bundle" if len(args) >= 2:
                bundle = export_debug_bundle(RunId(args[1]), default_debug_bundle_stores())
                print(json.dumps(bundle.model_dump(mode="json")))
                return 0
            case _:
                print(json.dumps({"error": "usage", "usage": _runs_usage()}))
                return 2
    except HarnessRunNotFoundError as exc:
        print(json.dumps({"error": "run_not_found", "detail": str(exc)}))
        return 1
    except RunCancellationBlockedError as exc:
        print(
            json.dumps(
                {
                    "error": "run_cancellation_blocked",
                    "detail": str(exc),
                    "current_status": exc.current_status,
                }
            )
        )
        return 1


def _runs_usage() -> str:
    return "plotlot runs <list|show|events|replay|cancel|export-debug-bundle>"
