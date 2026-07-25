from __future__ import annotations

import pytest

from plotlot.domain.types import ToolContext
from plotlot.harness.contracts import ExecutionMode, SourceMode
from plotlot.harness.tool_call_store import (
    LocalToolCallLedger,
    ToolCallNotFoundError,
    tool_call_from_result,
)
from plotlot.harness.tool_router import HarnessToolCallRequest, default_tool_router


def test_tool_call_ledger_persists_router_result(tmp_path) -> None:
    result = default_tool_router().call(
        HarnessToolCallRequest(
            tool_name="search_municode",
            args={"jurisdiction": "miami", "query": "parking"},
            context=ToolContext(
                workspace_id="ws_fixture",
                actor_user_id="analyst_fixture",
                run_id="run_fixture_tool_calls",
            ),
            source_mode=SourceMode.FIXTURE,
            execution_mode=ExecutionMode.CLI,
        )
    )
    ledger = LocalToolCallLedger(tmp_path / "tool-calls.json")

    record = ledger.save_tool_call(tool_call_from_result(result))
    listed = ledger.list_tool_calls(run_id="run_fixture_tool_calls")
    loaded = ledger.get_tool_call(record.tool_call_id)

    assert record.tool_name == "search_municode"
    assert record.status == "completed"
    assert record.permission_decision["allowed"] is True
    assert record.result_payload["results"][0]["section_id"] == "municode_miami_parking_fixture"
    assert listed == [record]
    assert loaded == record


def test_tool_call_ledger_raises_typed_error_for_missing_record(tmp_path) -> None:
    ledger = LocalToolCallLedger(tmp_path / "tool-calls.json")

    with pytest.raises(ToolCallNotFoundError):
        ledger.get_tool_call("tool_call_missing")
