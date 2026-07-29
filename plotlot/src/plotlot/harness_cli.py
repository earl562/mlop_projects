"""PlotLot harness CLI - the command-line face of the agent harness.

Every governed verb here routes tool calls through the SAME HarnessRuntime
that backs the REST and MCP transports, so a CLI invocation gets the identical
policy gate, risk budget, evidence, and audit path. This is the token-cheap way
for an external agent harness (Claude Code, a GPT agent) to use PlotLot: it
shells out to `plotlot tools call ... --json` on demand instead of preloading
25 fat tool schemas into its context the way an MCP client must.

Verbs:
    plotlot tools list [--json]
    plotlot tools call <name> [--arg k=v ...] [--json-args '{...}'] [flags]
    plotlot analyze <address> [--json] [flags]
    plotlot screen <addr> [<addr> ...] [--json] [flags]
    plotlot help

Governance flags (shared):
    --budget-cents N     risk budget for expensive reads (default 1000)
    --no-live-network    disallow live-network tools this run
    --approve ID         supply an approval id for a gated external write
    --json               emit machine-readable JSON (for external harnesses)
    --verbose            show pipeline diagnostics (quiet by default)

Exit codes: 0 ok | 1 error/unknown | 2 blocked | 3 pending approval.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

# Verbs this module owns. cli.main() delegates to dispatch() for these and
# otherwise falls back to the legacy `plotlot <address>` lookup.
KNOWN_COMMANDS = frozenset({"tools", "analyze", "screen", "help", "--help", "-h"})

_DEFAULT_BUDGET_CENTS = 1000

# Exit codes — distinct so scripts and calling harnesses can branch on outcome.
_EXIT_OK = 0
_EXIT_ERROR = 1
_EXIT_BLOCKED = 2
_EXIT_PENDING = 3


class _Flags:
    """Parsed shared flags plus leftover positionals/kv args."""

    def __init__(self) -> None:
        self.as_json = False
        self.budget_cents = _DEFAULT_BUDGET_CENTS
        self.live_network = True
        self.approve: str | None = None
        self.json_args: str | None = None
        self.verbose = False
        self.kv: dict[str, Any] = {}
        self.positionals: list[str] = []


def _configure_logging(verbose: bool) -> None:
    """Quiet by default: a CLI run should print its result, not its plumbing.

    The pipeline logs handled degradations at WARNING/ERROR — a Groq rate-limit
    that falls back to the primary provider, an optional wetlands layer that
    404s, an unactivated comps key that 403s. Each is recovered from and each is
    already reflected in the returned payload (`lot_size_source`, `adv_source`,
    `verification`), so surfacing the raw log lines makes a successful run read
    like a failed one. `--verbose` restores them for diagnosis.
    """
    import logging

    logging.basicConfig(
        level=logging.INFO if verbose else logging.CRITICAL,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("plotlot").setLevel(logging.INFO if verbose else logging.CRITICAL)


def _coerce(value: str) -> Any:
    """Best-effort typing for --arg values: JSON first, raw string otherwise.

    Lets `--arg lat=32.7` become a float and `--arg addresses=["a","b"]` a list,
    while `--arg expression=2+2` stays the literal string it needs to be.
    """
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value


def _parse_flags(rest: list[str]) -> _Flags:
    """Parse shared flags. Also applies the logging policy, since every caller
    parses flags before doing any work that could log."""
    flags = _Flags()
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok == "--json":
            flags.as_json = True
        elif tok == "--no-live-network":
            flags.live_network = False
        elif tok in ("--verbose", "-v"):
            flags.verbose = True
        elif tok == "--budget-cents":
            i += 1
            flags.budget_cents = int(rest[i]) if i < len(rest) else flags.budget_cents
        elif tok == "--approve":
            i += 1
            flags.approve = rest[i] if i < len(rest) else None
        elif tok == "--json-args":
            i += 1
            flags.json_args = rest[i] if i < len(rest) else None
        elif tok == "--arg":
            i += 1
            if i < len(rest) and "=" in rest[i]:
                key, raw = rest[i].split("=", 1)
                flags.kv[key] = _coerce(raw)
        else:
            flags.positionals.append(tok)
        i += 1
    _configure_logging(flags.verbose)
    return flags


def _build_context(flags: _Flags):
    from plotlot.land_use.models import ToolContext

    return ToolContext(
        workspace_id="cli",
        actor_user_id="cli-operator",
        run_id=str(uuid.uuid4()),
        risk_budget_cents=flags.budget_cents,
        live_network_allowed=flags.live_network,
        approved_approval_ids={flags.approve} if flags.approve else set(),
    )


async def _call_tool(tool_name: str, args: dict[str, Any], flags: _Flags):
    """Route one tool call through the shared governed runtime."""
    from plotlot.harness.default_runtime import get_default_runtime

    runtime = get_default_runtime()
    return await runtime.call_tool(
        tool_name=tool_name,
        tool_args=args,
        context=_build_context(flags),
        approval_id=flags.approve,
    )


def _exit_for_status(status: str) -> int:
    if status == "ok":
        return _EXIT_OK
    if status == "blocked":
        return _EXIT_BLOCKED
    if status == "pending_approval":
        return _EXIT_PENDING
    return _EXIT_ERROR


def _render_result(result, flags: _Flags) -> int:
    """Print a ToolCallResult and return the process exit code."""
    if flags.as_json:
        print(
            json.dumps(
                {
                    "tool_name": result.tool_name,
                    "status": result.status,
                    "decision": {
                        "allowed": result.decision.allowed,
                        "approval_required": result.decision.approval_required,
                        "reason": result.decision.reason,
                        "approval_id": result.decision.approval_id,
                    },
                    "result": result.result,
                    "message": result.message,
                }
            )
        )
        return _exit_for_status(result.status)

    print(f"tool:   {result.tool_name}")
    print(f"status: {result.status}")
    if result.decision.reason:
        print(f"policy: {result.decision.reason}")
    if result.status == "pending_approval":
        print(f"approval_id: {result.decision.approval_id}")
        print("  re-run with --approve <approval_id> once granted.")
    if result.message:
        print(f"message: {result.message}")
    if result.result is not None:
        print("result:")
        print(json.dumps(result.result, indent=2))
    return _exit_for_status(result.status)


def _cmd_tools(rest: list[str]) -> int:
    from plotlot.harness.default_runtime import get_default_runtime
    from plotlot.harness.tool_registry import list_tool_contracts, tool_exists

    if not rest:
        print("Usage: plotlot tools <list|call> ...")
        return _EXIT_ERROR

    sub, rest = rest[0], rest[1:]
    runtime = get_default_runtime()

    if sub == "list":
        flags = _parse_flags(rest)
        # Only advertise tools that have a registered handler in this runtime.
        contracts = [c for c in list_tool_contracts() if runtime.has_handler(c.name)]
        if flags.as_json:
            print(json.dumps([c.model_dump() for c in contracts], indent=2))
            return _EXIT_OK
        print(f"{len(contracts)} governed tools:\n")
        for c in contracts:
            print(f"  {c.name:<28} [{c.risk_class}]")
            print(f"  {'':<28} {c.description}")
        return _EXIT_OK

    if sub == "call":
        if not rest:
            print("Usage: plotlot tools call <name> [--arg k=v ...] [--json-args '{...}']")
            return _EXIT_ERROR
        name, rest = rest[0], rest[1:]
        flags = _parse_flags(rest)
        if not tool_exists(name):
            print(f"Unknown tool: {name} (see: plotlot tools list)")
            return _EXIT_ERROR
        args: dict[str, Any] = dict(flags.kv)
        if flags.json_args:
            try:
                args.update(json.loads(flags.json_args))
            except (json.JSONDecodeError, ValueError) as exc:
                print(f"--json-args is not valid JSON: {exc}")
                return _EXIT_ERROR
        result = asyncio.run(_call_tool(name, args, flags))
        return _render_result(result, flags)

    print(f"Unknown tools subcommand: {sub} (use 'list' or 'call')")
    return _EXIT_ERROR


def _cmd_analyze(rest: list[str]) -> int:
    flags = _parse_flags(rest)
    address = " ".join(flags.positionals).strip()
    if not address:
        print('Usage: plotlot analyze "<address>" [--json]')
        return _EXIT_ERROR
    result = asyncio.run(_call_tool("analyze_property", {"address": address}, flags))
    return _render_result(result, flags)


def _cmd_screen(rest: list[str]) -> int:
    flags = _parse_flags(rest)
    addresses = [a for a in flags.positionals if a.strip()]
    if not addresses:
        print('Usage: plotlot screen "<addr1>" "<addr2>" ... [--json]')
        return _EXIT_ERROR
    result = asyncio.run(_call_tool("screen_properties", {"addresses": addresses}, flags))
    return _render_result(result, flags)


def _print_help() -> int:
    print(__doc__)
    return _EXIT_OK


def dispatch(argv: list[str]) -> int:
    """Dispatch a harness CLI command. argv is sys.argv[1:]. Returns exit code."""
    if not argv:
        return _print_help()
    cmd, rest = argv[0], argv[1:]
    if cmd in ("help", "--help", "-h"):
        return _print_help()
    if cmd == "tools":
        return _cmd_tools(rest)
    if cmd == "analyze":
        return _cmd_analyze(rest)
    if cmd == "screen":
        return _cmd_screen(rest)
    print(f"Unknown command: {cmd}")
    return _print_help()
