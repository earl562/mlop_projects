#!/usr/bin/env python3
"""Remove safe local artifacts that bloat repo-root Vercel uploads."""

from __future__ import annotations

import shutil
from pathlib import Path

TRANSIENT_PATHS = (
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".coverage",
    "plotlot/frontend/.next",
    "plotlot/frontend/playwright-report",
    "plotlot/frontend/test-results",
    "frontend/.next",
    "frontend/node_modules",
    "frontend/playwright-report",
    "frontend/test-results",
    "apps/plotlot/frontend/.next",
    "apps/plotlot/frontend/node_modules",
    "apps/plotlot/frontend/playwright-report",
    "apps/plotlot/frontend/test-results",
)


def existing_transient_paths(repo_root: Path) -> list[Path]:
    return [repo_root / relative_path for relative_path in TRANSIENT_PATHS if (repo_root / relative_path).exists()]


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
        return

    path.unlink()


def clean(repo_root: Path) -> list[Path]:
    removed_paths: list[Path] = []
    for path in existing_transient_paths(repo_root):
        remove_path(path)
        removed_paths.append(path)

    return removed_paths


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    removed_paths = clean(repo_root)

    if not removed_paths:
        print("No deploy artifacts needed cleaning.")
        return 0

    print("Removed local deploy artifacts:")
    for path in removed_paths:
        print(f"- {path.relative_to(repo_root).as_posix()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
