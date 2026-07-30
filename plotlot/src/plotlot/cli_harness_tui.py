from __future__ import annotations

import json

from plotlot.cli_harness_support import (
    ParsedOption,
    option_value,
    parse_options,
    source_mode_option,
)
from plotlot.harness.approval_store import (
    ApprovalAlreadyResolvedError,
    ApprovalNotFoundError,
    InvalidApprovalDecisionError,
    default_approval_ledger,
)
from plotlot.harness.contracts import ApprovalId, RunId
from plotlot.harness.run_store import HarnessRunNotFoundError
from plotlot.harness.tui import (
    TuiRenderRequest,
    TuiRunRequiredError,
    TuiScreen,
    TuiScreenName,
    default_tui_stores,
    format_tui_screen,
    render_tui_screen,
)
from plotlot.harness.tui_approvals import (
    TuiApprovalAction,
    TuiApprovalIdRequiredError,
    TuiApprovalRequest,
    TuiApprovalRunRequiredError,
    render_tui_approval_screen,
)


def tui_command(args: list[str]) -> int:
    options = parse_options(args)
    json_output = "--json" in options.flags
    screen_raw = option_value(options, "--screen")
    try:
        if _is_approval_screen(screen_raw):
            screen = render_tui_approval_screen(
                TuiApprovalRequest(
                    action=_approval_action(options),
                    run_id=_run_id(option_value(options, "--run-id")),
                    approval_id=_approval_id(options),
                    resolved_by=option_value(options, "--resolved-by"),
                ),
                default_approval_ledger(),
            )
            return _print_screen(screen, json_output)
        request = TuiRenderRequest(
            screen=_screen_name(screen_raw),
            run_id=_run_id(option_value(options, "--run-id")),
            source_mode=source_mode_option(options),
        )
        screen = render_tui_screen(request, default_tui_stores())
    except HarnessRunNotFoundError as exc:
        _print_error("run_not_found", str(exc), json_output)
        return 1
    except TuiRunRequiredError as exc:
        _print_error("missing_run_id", str(exc), json_output)
        return 2
    except TuiApprovalRunRequiredError as exc:
        _print_error("missing_run_id", str(exc), json_output)
        return 2
    except TuiApprovalIdRequiredError as exc:
        _print_error("missing_approval_id", str(exc), json_output)
        return 2
    except ApprovalNotFoundError as exc:
        _print_error("approval_not_found", str(exc), json_output)
        return 1
    except ApprovalAlreadyResolvedError as exc:
        _print_error("approval_already_resolved", str(exc), json_output)
        return 1
    except InvalidApprovalDecisionError as exc:
        _print_error("invalid_approval_decision", str(exc), json_output)
        return 2
    except ValueError as exc:
        _print_error("invalid_input", str(exc), json_output)
        return 2
    return _print_screen(screen, json_output)


def _print_screen(screen: TuiScreen, json_output: bool) -> int:
    if json_output:
        print(json.dumps(screen.model_dump(mode="json")))
    else:
        print(format_tui_screen(screen), end="")
    return 0


def _screen_name(raw: str | None) -> TuiScreenName:
    if raw is None:
        return TuiScreenName.HOME
    return TuiScreenName(raw.replace("-", "_"))


def _run_id(raw: str | None) -> RunId | None:
    if raw is None:
        return None
    return RunId(raw)


def _is_approval_screen(raw: str | None) -> bool:
    return raw is not None and raw.replace("-", "_") == TuiScreenName.APPROVALS.value


def _approval_action(options: ParsedOption) -> TuiApprovalAction:
    if option_value(options, "--approve") is not None:
        return TuiApprovalAction.APPROVE
    if option_value(options, "--deny") is not None:
        return TuiApprovalAction.DENY
    return TuiApprovalAction.LIST


def _approval_id(options: ParsedOption) -> ApprovalId | None:
    approve_id = option_value(options, "--approve")
    deny_id = option_value(options, "--deny")
    selected = approve_id or deny_id
    if selected is None:
        return None
    return ApprovalId(selected)


def _print_error(code: str, detail: str, json_output: bool) -> None:
    if json_output:
        print(json.dumps({"error": code, "detail": detail}))
    else:
        print(f"{code}: {detail}")
