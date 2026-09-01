#!/usr/bin/env python3
"""Fail when non-product state, generated artifacts, or banned media are tracked."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PurePosixPath

AGENT_WORKSPACE_PREFIXES = (
    ".claude/",
    ".omo/",
    "plotlot/.omx/",
)

PERSONAL_INSTRUCTION_FILES = {
    "CLAUDE.md",
    "GEMINI.md",
    "plotlot/CLAUDE.md",
}

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


def _matches_prefix(path: str, prefix: str) -> bool:
    return path == prefix.removesuffix("/") or path.startswith(prefix)


def find_violations(paths: list[str]) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for path in paths:
        normalized = path.replace("\\", "/")

        if any(_matches_prefix(normalized, prefix) for prefix in AGENT_WORKSPACE_PREFIXES):
            violations.append((normalized, "agent-workspace-state"))
            continue

        if normalized in PERSONAL_INSTRUCTION_FILES:
            violations.append((normalized, "personal-instruction-file"))
            continue

        if any(_matches_prefix(normalized, prefix) for prefix in BANNED_DIR_PREFIXES):
            violations.append((normalized, "generated-artifact-directory"))
            continue

        if any(
            _matches_prefix(normalized, prefix)
            for prefix in NON_CANONICAL_FRONTEND_PREFIXES
        ):
            violations.append((normalized, "non-canonical-frontend-root"))
            continue

        if any(_matches_prefix(normalized, prefix) for prefix in ALLOWED_DIR_PREFIXES):
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
    print("Tracked non-product or generated files:", file=sys.stderr)
    for path, reason in violations:
        print(f"- {path} [{reason}]", file=sys.stderr)

    print("", file=sys.stderr)
    print(
        "Remove AI workspace state and personal instruction files from git; keep one "
        "neutral AGENTS.md as the repository contract.",
        file=sys.stderr,
    )
    print(
        "Store screenshots, Playwright output, and generated evaluation evidence in "
        "ignored paths or GitHub Actions artifacts.",
        file=sys.stderr,
    )
    print(
        "Keep tracked frontend code under plotlot/frontend/ only.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
