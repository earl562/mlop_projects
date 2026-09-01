#!/usr/bin/env python3
"""Create a privacy-safe PlotLot lead fixture from an authenticated row export."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plotlot.evaluation.leads import (
    LeadFixtureManifest,
    assert_fixture_is_sanitized,
    sanitize_lead_row,
)


def _load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("rows")
    if not isinstance(payload, list) or not all(
        isinstance(item, dict) for item in payload
    ):
        raise ValueError("input must be a JSON array of row objects or {'rows': [...]}")
    return payload


def _source_reference(raw_source_id: str) -> str:
    digest = hashlib.sha256(raw_source_id.encode("utf-8")).hexdigest()[:16]
    return f"drive_sha256:{digest}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sanitize rows exported through an authenticated Drive/Sheets connector. "
            "The raw source ID is hashed before it enters the fixture."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-file-id", required=True)
    parser.add_argument("--source-label", default="drive_property_rows")
    parser.add_argument("--sheet", default="unknown")
    parser.add_argument("--workflow", default="site_feasibility")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = _load_rows(args.input)
    source_reference = _source_reference(args.source_file_id)
    cases_by_id = {}
    selected_rows: list[int] = []

    for row_number, row in enumerate(rows, start=2):
        case = sanitize_lead_row(
            row,
            source_file_id=source_reference,
            source_row=row_number,
            workflow=args.workflow,
        )
        if case is None:
            continue
        cases_by_id.setdefault(case.case_id, case)
        selected_rows.append(row_number)

    cases = list(cases_by_id.values())
    payload = [case.model_dump(mode="json") for case in cases]
    assert_fixture_is_sanitized(payload)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = LeadFixtureManifest(
        schema_version="1.0",
        generated_at=datetime.now(timezone.utc).isoformat(),
        case_count=len(cases),
        markets=tuple(
            sorted(
                {
                    f"{case.county}, {case.state}"
                    for case in cases
                    if case.county and case.state
                }
            )
        ),
        source_files=(
            {
                "source_file_id": source_reference,
                "label": args.source_label,
                "sheet": args.sheet,
                "selected_rows": selected_rows,
            },
        ),
        privacy_exclusions=(
            "owner names",
            "seller names",
            "phone numbers",
            "email addresses",
            "mailing addresses",
            "prospect notes",
            "outreach status",
            "free-text contact notes",
        ),
    )
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        manifest.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(cases)} sanitized cases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
