from __future__ import annotations

import json

from pydantic import TypeAdapter, ValidationError

from plotlot.cli_harness_support import option_value, parse_options, source_mode_option
from plotlot.domain.types import ToolContext
from plotlot.harness.contracts import ExecutionMode, JsonObject, RunId
from plotlot.harness.full_harness_registry import (
    RegistryLookupError,
    get_tool_spec,
    list_tool_specs,
)
from plotlot.harness.run_store import HarnessRunNotFoundError, default_harness_run_store
from plotlot.harness.tool_call_store import default_tool_call_ledger, tool_call_from_result
from plotlot.harness.tool_router import HarnessToolCallRequest, default_tool_router

JSON_OBJECT_ADAPTER = TypeAdapter(JsonObject)


def tools_command(args: list[str]) -> int:
    try:
        match args:
            case [] | ["list"]:
                return _list_tools()
            case ["inspect", tool_name]:
                return _inspect_tool(tool_name)
            case ["call", tool_name, *raw_options]:
                return _call_tool(tool_name, raw_options)
            case ["calls", *raw_options]:
                return _list_tool_calls(raw_options)
            case _:
                return _usage()
    except RegistryLookupError as exc:
        print(json.dumps({"error": "tool_not_found", "detail": str(exc)}))
        return 1
    except ValidationError as exc:
        print(json.dumps({"error": "invalid_input", "detail": exc.errors()}))
        return 2
    except ValueError as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
        return 2


def _list_tools() -> int:
    print(json.dumps({"tools": [tool.model_dump(mode="json") for tool in list_tool_specs()]}))
    return 0


def _inspect_tool(tool_name: str) -> int:
    print(json.dumps({"tool": get_tool_spec(tool_name).model_dump(mode="json")}))
    return 0


def _call_tool(tool_name: str, raw_options: list[str]) -> int:
    options = parse_options(raw_options)
    raw_json = option_value(options, "--json")
    run_id = option_value(options, "--run-id")
    workspace_id = option_value(options, "--workspace-id")
    if raw_json is None or run_id is None or workspace_id is None:
        return _usage()
    result = default_tool_router().call(
        HarnessToolCallRequest(
            tool_name=tool_name,
            args=JSON_OBJECT_ADAPTER.validate_json(raw_json),
            context=ToolContext(
                workspace_id=workspace_id,
                actor_user_id=option_value(options, "--actor-user-id") or "cli",
                run_id=run_id,
                approved_approval_ids=set(options.items.get("--approved-approval-id", [])),
            ),
            source_mode=source_mode_option(options),
            execution_mode=ExecutionMode.CLI,
        )
    )
    record = default_tool_call_ledger().save_tool_call(tool_call_from_result(result))
    try:
        default_harness_run_store().append_events(result.run_id, result.events)
    except HarnessRunNotFoundError:
        pass
    payload = result.model_dump(mode="json")
    payload["tool_call_id"] = str(record.tool_call_id)
    print(json.dumps(payload))
    return 0 if result.ok else 1


def _list_tool_calls(raw_options: list[str]) -> int:
    options = parse_options(raw_options)
    run_id = option_value(options, "--run-id")
    if run_id is None:
        return _usage()
    tool_calls = default_tool_call_ledger().list_tool_calls(run_id=RunId(run_id))
    print(json.dumps({"tool_calls": [item.model_dump(mode="json") for item in tool_calls]}))
    return 0


def _usage() -> int:
    print(
        json.dumps(
            {
                "error": "usage",
                "usage": (
                    "plotlot tools <list|inspect|call|calls> [tool-name] "
                    "--run-id RUN_ID --workspace-id WORKSPACE_ID --json '{...}'"
                ),
            }
        )
    )
    return 2
