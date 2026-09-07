from __future__ import annotations

import argparse
import json
from pathlib import Path

from plotlot.protocol.openapi import protocol_openapi_document


def export_openapi(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        protocol_openapi_document(),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    output.write_text(f"{serialized}\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    export_openapi(args.output)


if __name__ == "__main__":
    main()
