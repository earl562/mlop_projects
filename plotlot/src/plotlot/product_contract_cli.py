from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from plotlot.domain.opportunity_contract import (
    evaluate_opportunity_decision,
    parse_opportunity_decision_input,
    product_contract_projection_hash,
)
from plotlot.domain.support_ledger import build_initial_support_ledger


def parse_evaluated_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("evaluated-at requires a UTC offset")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(prog="plotlot-product-contract")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("projection")
    evaluate = subcommands.add_parser("evaluate")
    evaluate.add_argument("input", type=Path)
    evaluate.add_argument("registry", type=Path)
    evaluate.add_argument("evaluated_at", type=parse_evaluated_at)
    args = parser.parse_args()

    if args.command == "projection":
        print(
            json.dumps(
                {
                    "projectionHash": product_contract_projection_hash(),
                    "supportLedgerEntries": len(build_initial_support_ledger()),
                },
                sort_keys=True,
            )
        )
        return 0

    raw = args.input.read_text(encoding="utf-8")
    from plotlot.domain.issued_support_registry import parse_issued_support_registry

    registry = parse_issued_support_registry(args.registry.read_text(encoding="utf-8"))
    result = evaluate_opportunity_decision(
        parse_opportunity_decision_input(raw),
        receipt_registry=registry,
        evaluated_at=args.evaluated_at,
    )
    print(result.model_dump_json(by_alias=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
