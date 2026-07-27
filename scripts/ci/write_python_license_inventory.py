#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path


def license_value(metadata: importlib.metadata.PackageMetadata) -> str:
    expression = metadata.get("License-Expression")
    if expression:
        return expression
    classifiers = metadata.get_all("Classifier") or []
    classified = "; ".join(
        classifier.removeprefix("License :: ").strip()
        for classifier in classifiers
        if classifier.startswith("License :: ")
    )
    if classified:
        return classified
    declared = metadata.get("License")
    if (
        declared
        and declared != "UNKNOWN"
        and "@" not in declared
        and "\n" not in declared
        and len(declared) <= 120
    ):
        return declared
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()
    packages = []
    for distribution in sorted(
        importlib.metadata.distributions(),
        key=lambda value: (value.metadata.get("Name") or "").lower(),
    ):
        name = distribution.metadata.get("Name")
        if name:
            packages.append(
                {
                    "name": name,
                    "version": distribution.version,
                    "license": license_value(distribution.metadata),
                }
            )
    output = Path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"schema": "PythonLicenseInventoryV1", "packages": packages}, indent=2) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
