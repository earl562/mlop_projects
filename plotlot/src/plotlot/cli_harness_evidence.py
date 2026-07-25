from __future__ import annotations

import json

from plotlot.cli_harness_support import option_value, parse_options
from plotlot.harness.contracts import EvidenceId, RunId
from plotlot.harness.evidence_store import EvidenceNotFoundError, default_evidence_ledger


def evidence_command(args: list[str]) -> int:
    if not args:
        print(json.dumps({"error": "usage", "usage": "plotlot evidence <list|show>"}))
        return 2
    ledger = default_evidence_ledger()
    try:
        match args[0]:
            case "list":
                options = parse_options(args[1:])
                run_id = option_value(options, "--run-id")
                evidence = ledger.list_evidence(run_id=None if run_id is None else RunId(run_id))
                print(json.dumps({"evidence": [item.model_dump(mode="json") for item in evidence]}))
                return 0
            case "show" if len(args) >= 2:
                print(json.dumps(ledger.get_evidence(EvidenceId(args[1])).model_dump(mode="json")))
                return 0
            case _:
                print(json.dumps({"error": "usage", "usage": "plotlot evidence <list|show>"}))
                return 2
    except EvidenceNotFoundError as exc:
        print(json.dumps({"error": "evidence_not_found", "detail": str(exc)}))
        return 1
