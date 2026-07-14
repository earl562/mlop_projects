"""Tests for the harness CLI — the command-line face of the HarnessRuntime.

`calculate` is the ideal end-to-end fixture: it's a real registered handler,
READ_ONLY, and pure (no network), so `tools call calculate` exercises the whole
governed path (registry -> policy -> handler -> result) with zero mocking.
"""

import json

from plotlot import harness_cli


def test_known_commands_include_verbs():
    assert {"tools", "analyze", "screen", "help"} <= harness_cli.KNOWN_COMMANDS


def test_coerce_types():
    assert harness_cli._coerce("32.7") == 32.7
    assert harness_cli._coerce('["a","b"]') == ["a", "b"]
    # An arithmetic expression must survive as a literal string, not become math.
    assert harness_cli._coerce("2+2") == "2+2"


def test_parse_flags_defaults_and_overrides():
    flags = harness_cli._parse_flags(
        ["--json", "--budget-cents", "50", "--no-live-network", "--arg", "expression=7*8"]
    )
    assert flags.as_json is True
    assert flags.budget_cents == 50
    assert flags.live_network is False
    assert flags.kv == {"expression": "7*8"}


def test_tools_list_json(capsys):
    code = harness_cli.dispatch(["tools", "list", "--json"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    names = {c["name"] for c in out}
    # Handlers we just wired should all advertise on the CLI.
    assert {"calculate", "analyze_property", "geocode_address"} <= names
    for contract in out:
        assert "risk_class" in contract


def test_tools_list_human_readable(capsys):
    code = harness_cli.dispatch(["tools", "list"])
    assert code == 0
    out = capsys.readouterr().out
    assert "governed tools" in out
    assert "calculate" in out


def test_tools_call_calculate_end_to_end(capsys):
    """Full governed path: registry -> policy(READ_ONLY allow) -> handler -> ok."""
    code = harness_cli.dispatch(
        ["tools", "call", "calculate", "--arg", "expression=7*750000", "--json"]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["tool_name"] == "calculate"
    assert payload["status"] == "ok"
    assert payload["result"]["result"] == 5250000
    assert payload["decision"]["allowed"] is True


def test_tools_call_unknown_tool(capsys):
    code = harness_cli.dispatch(["tools", "call", "no_such_tool", "--json"])
    assert code == harness_cli._EXIT_ERROR
    assert "Unknown tool" in capsys.readouterr().out


def test_tools_call_bad_json_args(capsys):
    code = harness_cli.dispatch(["tools", "call", "calculate", "--json-args", "{not json}"])
    assert code == harness_cli._EXIT_ERROR
    assert "not valid JSON" in capsys.readouterr().out


def test_expensive_read_blocked_without_budget(capsys):
    """screen_properties is EXPENSIVE_READ (50c); a 0-budget, no-network run is gated."""
    code = harness_cli.dispatch(
        ["tools", "call", "screen_properties", "--json-args", '{"addresses":["x"]}',
         "--budget-cents", "0", "--no-live-network", "--json"]
    )
    payload = json.loads(capsys.readouterr().out)
    # Policy denies before the handler ever runs (network off + no budget).
    assert payload["status"] in {"blocked", "pending_approval"}
    assert code in {harness_cli._EXIT_BLOCKED, harness_cli._EXIT_PENDING}


def test_help_and_unknown_command(capsys):
    assert harness_cli.dispatch(["help"]) == 0
    assert "plotlot tools" in capsys.readouterr().out
    # Unknown command falls through to help, not a crash.
    assert harness_cli.dispatch(["frobnicate"]) == 0


def test_analyze_requires_address(capsys):
    code = harness_cli.dispatch(["analyze"])
    assert code == harness_cli._EXIT_ERROR
    assert "Usage" in capsys.readouterr().out


def test_screen_requires_addresses(capsys):
    code = harness_cli.dispatch(["screen"])
    assert code == harness_cli._EXIT_ERROR
    assert "Usage" in capsys.readouterr().out
