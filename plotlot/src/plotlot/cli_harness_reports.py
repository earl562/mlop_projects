from __future__ import annotations

import json

from plotlot.cli_harness_support import option_value, parse_options
from plotlot.harness.contracts import ClaimId, ReportId, RunId
from plotlot.harness.report_inspection import comp_support_snapshot
from plotlot.harness.report_export import (
    ReportArtifactExportRequest,
    ReportExportFormat,
    export_report_artifact,
)
from plotlot.harness.report_finalization import ReportFinalizationBlockedError, finalize_report
from plotlot.harness.report_store import ClaimNotFoundError, ReportNotFoundError, default_report_ledger
from plotlot.harness.run_store import default_harness_run_store
from plotlot.harness.verification_store import default_verification_ledger


def claims_command(args: list[str]) -> int:
    if not args:
        print(json.dumps({"error": "usage", "usage": "plotlot claims <list|show>"}))
        return 2
    ledger = default_report_ledger()
    try:
        match args[0]:
            case "list":
                options = parse_options(args[1:])
                run_id = option_value(options, "--run-id")
                claims = ledger.list_claims(run_id=None if run_id is None else RunId(run_id))
                print(json.dumps({"claims": [claim.model_dump(mode="json") for claim in claims]}))
                return 0
            case "show" if len(args) >= 2:
                print(json.dumps(ledger.get_claim(ClaimId(args[1])).model_dump(mode="json")))
                return 0
            case _:
                print(json.dumps({"error": "usage", "usage": "plotlot claims <list|show>"}))
                return 2
    except ClaimNotFoundError as exc:
        print(json.dumps({"error": "claim_not_found", "detail": str(exc)}))
        return 1


def reports_command(args: list[str]) -> int:
    if not args:
        print(json.dumps({"error": "usage", "usage": "plotlot reports <list|show|export|finalize>"}))
        return 2
    ledger = default_report_ledger()
    try:
        match args[0]:
            case "list":
                options = parse_options(args[1:])
                run_id = option_value(options, "--run-id")
                reports = ledger.list_reports(run_id=None if run_id is None else RunId(run_id))
                print(json.dumps({"reports": [report.model_dump(mode="json") for report in reports]}))
                return 0
            case "show" if len(args) >= 2:
                report = ledger.get_report(ReportId(args[1]))
                payload = report.model_dump(mode="json")
                payload["comp_support_snapshot"] = comp_support_snapshot(report)
                print(json.dumps(payload))
                return 0
            case "export" if len(args) >= 2:
                options = parse_options(args[2:])
                export_format = ReportExportFormat(
                    option_value(options, "--format") or ReportExportFormat.MARKDOWN.value
                )
                export = export_report_artifact(
                    ReportArtifactExportRequest(
                        report_id=ReportId(args[1]),
                        export_format=export_format,
                    ),
                    report_ledger=ledger,
                    run_store=default_harness_run_store(),
                )
                print(json.dumps(export.model_dump(mode="json")))
                return 0
            case "finalize" if len(args) >= 2:
                report = finalize_report(
                    ReportId(args[1]),
                    report_ledger=ledger,
                    verification_ledger=default_verification_ledger(),
                )
                print(json.dumps(report.model_dump(mode="json")))
                return 0
            case _:
                print(
                    json.dumps(
                        {
                            "error": "usage",
                            "usage": "plotlot reports <list|show|export|finalize>",
                        }
                    )
                )
                return 2
    except ReportNotFoundError as exc:
        print(json.dumps({"error": "report_not_found", "detail": str(exc)}))
        return 1
    except ValueError as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
        return 2
    except ReportFinalizationBlockedError as exc:
        verification_id = None if exc.verification is None else str(exc.verification.verification_id)
        print(
            json.dumps(
                {
                    "error": "report_finalization_blocked",
                    "detail": str(exc),
                    "reason": exc.reason,
                    "verification_id": verification_id,
                }
            )
        )
        return 1
