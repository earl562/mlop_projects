#!/usr/bin/env python3
"""Fail when generated artifacts or banned media are tracked in git."""

from __future__ import annotations

import subprocess
import sys
from pathlib import PurePosixPath

BANNED_DIR_PREFIXES = (
    ".playwright-mcp/",
    "plotlot/frontend/playwright-report/",
    "plotlot/frontend/test-results/",
    "plotlot/frontend/tests/screenshots/",
    "plotlot/tests/screenshots/",
)

BANNED_MEDIA_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webm",
    ".zip",
}


def list_tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=False,
    )
    return [path for path in result.stdout.decode("utf-8").split("\x00") if path]


def find_violations(paths: list[str]) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for path in paths:
        normalized = path.replace("\\", "/")
        if any(
            normalized == prefix.removesuffix("/") or normalized.startswith(prefix)
            for prefix in BANNED_DIR_PREFIXES
        ):
            violations.append((normalized, "generated-artifact-directory"))
            continue

        suffix = PurePosixPath(normalized).suffix.lower()
        if suffix in BANNED_MEDIA_SUFFIXES:
            violations.append((normalized, "tracked-media"))

    return violations


def main() -> int:
    violations = find_violations(list_tracked_files())
    if not violations:
        print("Repository hygiene check passed.")
        return 0

    print("Repository hygiene check failed.", file=sys.stderr)
    print("", file=sys.stderr)
    print("The following tracked files violate the no-media / no-generated-artifacts policy:", file=sys.stderr)
    for path, reason in violations:
        print(f"- {path} [{reason}]", file=sys.stderr)

    print("", file=sys.stderr)
    print(
        "Move screenshots, Playwright outputs, and other large generated artifacts to ignored local paths or GitHub Actions artifacts instead of git history.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
