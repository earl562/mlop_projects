from __future__ import annotations

import json

from plotlot.cli_harness_support import option_value, parse_options
from plotlot.harness.approval_store import (
    ApprovalAlreadyResolvedError,
    ApprovalNotFoundError,
    InvalidApprovalDecisionError,
    default_approval_ledger,
)
from plotlot.harness.contracts import (
    ApprovalId,
    ApprovalStatus,
    PlotLotEventSource,
    RiskLevel,
    RunId,
)


def approvals_command(args: list[str]) -> int:
    if not args:
        return _usage()
    ledger = default_approval_ledger()
    try:
        match args[0]:
            case "request":
                options = parse_options(args[1:])
                run_id = option_value(options, "--run-id")
                action = option_value(options, "--action")
                risk_level = option_value(options, "--risk-level")
                reason = option_value(options, "--reason")
                if run_id is None or action is None or risk_level is None or reason is None:
                    return _usage()
                approval = ledger.request_approval(
                    run_id=RunId(run_id),
                    requested_action=action,
                    risk_level=RiskLevel(risk_level),
                    reason=reason,
                    source=PlotLotEventSource.CLI,
                )
                print(json.dumps(approval.model_dump(mode="json")))
                return 0
            case "list":
                options = parse_options(args[1:])
                run_id_value = option_value(options, "--run-id")
                status_value = option_value(options, "--status")
                approvals = ledger.list_approvals(
                    run_id=RunId(run_id_value) if run_id_value else None,
                    status=ApprovalStatus(status_value) if status_value else None,
                )
                print(
                    json.dumps(
                        {"approvals": [approval.model_dump(mode="json") for approval in approvals]}
                    )
                )
                return 0
            case "show" if len(args) >= 2:
                approval = ledger.get_approval(ApprovalId(args[1]))
                print(json.dumps(approval.model_dump(mode="json")))
                return 0
            case "approve" if len(args) >= 2:
                options = parse_options(args[2:])
                return _resolve(
                    ApprovalId(args[1]),
                    decision=ApprovalStatus.APPROVED,
                    resolved_by=option_value(options, "--resolved-by"),
                )
            case "deny" if len(args) >= 2:
                options = parse_options(args[2:])
                return _resolve(
                    ApprovalId(args[1]),
                    decision=ApprovalStatus.DENIED,
                    resolved_by=option_value(options, "--resolved-by"),
                )
            case _:
                return _usage()
    except ValueError as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
        return 2
    except ApprovalNotFoundError as exc:
        print(json.dumps({"error": "approval_not_found", "detail": str(exc)}))
        return 1
    except ApprovalAlreadyResolvedError as exc:
        print(json.dumps({"error": "approval_already_resolved", "detail": str(exc)}))
        return 1
    except InvalidApprovalDecisionError as exc:
        print(json.dumps({"error": "invalid_approval_decision", "detail": str(exc)}))
        return 2


def _resolve(
    approval_id: ApprovalId,
    *,
    decision: ApprovalStatus,
    resolved_by: str | None,
) -> int:
    approval = default_approval_ledger().resolve_approval(
        approval_id,
        decision=decision,
        resolved_by=resolved_by,
        source=PlotLotEventSource.CLI,
    )
    print(json.dumps(approval.model_dump(mode="json")))
    return 0


def _usage() -> int:
    print(
        json.dumps(
            {
                "error": "usage",
                "usage": (
                    "plotlot approvals <request|list|show|approve|deny> "
                    "[--run-id RUN_ID] [--action ACTION]"
                ),
            }
        )
    )
    return 2
