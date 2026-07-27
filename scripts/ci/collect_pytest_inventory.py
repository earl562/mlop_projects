#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from pair_gate_test_policy import classify_test_path
from pair_gate_types import JsonValue


class InventoryPlugin:
    def __init__(self) -> None:
        self.items: list[pytest.Item] = []

    def pytest_collection_modifyitems(
        self,
        session: pytest.Session,
        config: pytest.Config,
        items: list[pytest.Item],
    ) -> None:
        del session, config
        self.items = items


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    plugin = InventoryPlugin()
    exit_code = pytest.main(["tests/", "--collect-only", "-q"], plugins=[plugin])
    entries: list[JsonValue] = []
    for item in plugin.items:
        path = item.nodeid.split("::", 1)[0]
        entries.append({"nodeId": item.nodeid, **classify_test_path(path)})
    output = Path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema": "PytestInventoryV1",
                "total": len(entries),
                "skipped": 0,
                "tests": entries,
            },
            indent=2,
        )
        + "\n"
    )
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
