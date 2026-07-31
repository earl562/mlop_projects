from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from plotlot_baseline_lib import BaselineError, run_bounded

GENERATED_COMPONENTS = frozenset(
    {
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "htmlcov",
        "logs",
        "mlruns",
        "mutants",
        "node_modules",
        "playwright-report",
        "test-results",
        "tmp",
    }
)
SAFE_IGNORED_PREFIXES = (
    ".opencode/",
    ".playwright-mcp/",
    "outreach-agent/",
    "plotlot/.codegraph",
    "plotlot/.omx/",
    "plotlot/.ralph-archive/",
)
SAFE_IGNORED_SUFFIXES = (
    ".db",
    ".gif",
    ".jpeg",
    ".jpg",
    ".mov",
    ".mp4",
    ".png",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".tsbuildinfo",
    ".webp",
)
SAFE_IGNORED_NAMES = frozenset(
    {
        ".DS_Store",
        ".env",
        "AGENTS.md",
        "CACHEDIR.TAG",
        "coverage.xml",
        "next-env.d.ts",
    }
)
PROHIBITED_TRACKED_NAMES = frozenset(
    {
        ".DS_Store",
        ".env",
        "credentials.json",
        "firebase-debug.log",
        "npm-debug.log",
        "token.json",
        "yarn-debug.log",
        "yarn-error.log",
    }
)
PROHIBITED_TRACKED_SUFFIXES = (
    ".db",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".tsbuildinfo",
)


def discover_ignored_paths(repo: Path) -> list[str]:
    result = run_bounded(
        [
            "git",
            "-C",
            str(repo),
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
        ],
        timeout_seconds=15,
    )
    return sorted(set(result.stdout.splitlines()))


def _is_safe_ignored(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if path.startswith(SAFE_IGNORED_PREFIXES):
        return True
    if GENERATED_COMPONENTS.intersection(parts):
        return True
    if name in SAFE_IGNORED_NAMES or name.startswith(".env."):
        return True
    return name.endswith(SAFE_IGNORED_SUFFIXES)


def rejected_ignored_paths(repo: Path) -> list[str]:
    return [path for path in discover_ignored_paths(repo) if not _is_safe_ignored(path)]


def assert_ignored_paths_allowed(repo: Path) -> int:
    ignored = discover_ignored_paths(repo)
    rejected = [path for path in ignored if not _is_safe_ignored(path)]
    if rejected:
        raise BaselineError(
            f"unallowlisted ignored path rejected: {rejected[0]} "
            f"(rejected_count={len(rejected)})"
        )
    return len(ignored)


def _is_prohibited_tracked(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if name in PROHIBITED_TRACKED_NAMES:
        return True
    if name.endswith(PROHIBITED_TRACKED_SUFFIXES):
        return True
    if GENERATED_COMPONENTS.intersection(parts):
        return True
    return "/.omo/evidence/" in f"/{path}" or path.startswith("artifacts/")


def prohibited_tracked_artifacts(repo: Path) -> list[str]:
    result = run_bounded(
        ["git", "-C", str(repo), "ls-files"],
        timeout_seconds=15,
    )
    return [path for path in result.stdout.splitlines() if _is_prohibited_tracked(path)]


def assert_no_prohibited_tracked_artifacts(repo: Path) -> None:
    rejected = prohibited_tracked_artifacts(repo)
    if rejected:
        raise BaselineError(
            f"prohibited tracked artifact: {rejected[0]} "
            f"(rejected_count={len(rejected)})"
        )


def assert_records_exclude_artifacts(records: list[dict[str, str | int]]) -> None:
    rejected = [
        str(record["path"])
        for record in records
        if _is_prohibited_tracked(str(record["path"]))
    ]
    if rejected:
        raise BaselineError(f"manifest includes prohibited artifact: {rejected[0]}")


def reject_disposable_ignored_fixture() -> None:
    with tempfile.TemporaryDirectory(prefix="plotlot-ignored-policy-") as raw:
        repo = Path(raw)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / ".gitignore").write_text("*.ignored\n", encoding="utf-8")
        injected = repo / "plotlot/src/injected.ignored"
        injected.parent.mkdir(parents=True)
        injected.write_text("unexpected\n", encoding="utf-8")
        rejected = rejected_ignored_paths(repo)
        if rejected != ["plotlot/src/injected.ignored"]:
            raise BaselineError("ignored-path injection fixture was not discovered")
        raise BaselineError(f"unallowlisted ignored path rejected: {rejected[0]}")
