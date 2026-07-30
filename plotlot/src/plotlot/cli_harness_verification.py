from __future__ import annotations

import json

from plotlot.cli_harness_support import option_value, parse_options
from plotlot.harness.contracts import ReportId, RunId, VerificationId
from plotlot.harness.report_store import ReportNotFoundError, default_report_ledger
from plotlot.harness.verification_inspection import (
    verification_payload as build_verification_payload,
)
from plotlot.harness.verification_store import (
    VerificationNotFoundError,
    default_verification_ledger,
)


def verification_command(args: list[str]) -> int:
    if not args:
        print(json.dumps({"error": "usage", "usage": "plotlot verification <list|show>"}))
        return 2
    ledger = default_verification_ledger()
    try:
        match args[0]:
            case "list":
                options = parse_options(args[1:])
                run_id = option_value(options, "--run-id")
                results = ledger.list_verifications(
                    run_id=None if run_id is None else RunId(run_id)
                )
                print(
                    json.dumps({"verifications": [_verification_payload(item) for item in results]})
                )
                return 0
            case "show":
                return _verification_show(args[1:])
            case _:
                print(json.dumps({"error": "usage", "usage": "plotlot verification <list|show>"}))
                return 2
    except VerificationNotFoundError as exc:
        print(json.dumps({"error": "verification_not_found", "detail": str(exc)}))
        return 1


def _verification_show(args: list[str]) -> int:
    options = parse_options(args)
    ledger = default_verification_ledger()
    report_id = option_value(options, "--report-id")
    if report_id is not None:
        verification = ledger.get_latest_for_report(ReportId(report_id))
        print(json.dumps(_verification_payload(verification)))
        return 0
    if args:
        verification = ledger.get_verification(VerificationId(args[0]))
        print(json.dumps(_verification_payload(verification)))
        return 0
    print(
        json.dumps(
            {
                "error": "usage",
                "usage": "plotlot verification show <verification-id|--report-id ID>",
            }
        )
    )
    return 2


def _verification_payload(verification) -> dict[str, object]:
    try:
        report = default_report_ledger().get_report(verification.report_id)
    except ReportNotFoundError:
        report = None
    return build_verification_payload(verification, report=report)
