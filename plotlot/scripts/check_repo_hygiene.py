#!/usr/bin/env python3
"""Fail when generated artifacts or banned media are tracked in git."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath

BANNED_DIR_PREFIXES = (
    ".playwright-mcp/",
    "frontend/playwright-report/",
    "frontend/test-results/",
    "frontend/tests/screenshots/",
    "tests/screenshots/",
    "plotlot/frontend/playwright-report/",
    "plotlot/frontend/test-results/",
    "plotlot/frontend/tests/screenshots/",
    "plotlot/tests/screenshots/",
)

# Static product assets in the canonical Next.js public/ directory are
# intentionally tracked. Generated test output remains banned above.
ALLOWED_DIR_PREFIXES = ("plotlot/frontend/public/",)

BANNED_MEDIA_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webm",
    ".zip",
}

NON_CANONICAL_FRONTEND_PREFIXES = (
    "frontend/",
    "apps/plotlot/frontend/",
)


def list_tracked_files(repo_root: Path | None = None) -> list[str]:
    resolved_repo_root = repo_root or Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "-C", str(resolved_repo_root), "ls-files", "-z"],
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

        if any(
            normalized == prefix.removesuffix("/") or normalized.startswith(prefix)
            for prefix in NON_CANONICAL_FRONTEND_PREFIXES
        ):
            violations.append((normalized, "non-canonical-frontend-root"))
            continue

        if any(
            normalized == prefix.removesuffix("/") or normalized.startswith(prefix)
            for prefix in ALLOWED_DIR_PREFIXES
        ):
            continue

        suffix = PurePosixPath(normalized).suffix.lower()
        if suffix in BANNED_MEDIA_SUFFIXES:
            violations.append((normalized, "tracked-media"))

    return violations


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    violations = find_violations(list_tracked_files(repo_root))
    if not violations:
        print("Repository hygiene check passed.")
        return 0

    print("Repository hygiene check failed.", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "The following tracked files violate the no-media / no-generated-artifacts policy:",
        file=sys.stderr,
    )
    for path, reason in violations:
        print(f"- {path} [{reason}]", file=sys.stderr)

    print("", file=sys.stderr)
    print(
        "Move screenshots, Playwright outputs, and other large generated artifacts to ignored local paths or GitHub Actions artifacts instead of git history.",
        file=sys.stderr,
    )
    print(
        "Keep tracked frontend code under plotlot/frontend/. Duplicate tracked frontend roots are not allowed.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
