"""Unit tests for repository hygiene rules."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_hygiene_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / "check_repo_hygiene.py"
    spec = importlib.util.spec_from_file_location("plotlot_repo_hygiene", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repo_hygiene = _load_hygiene_module()


def test_flags_tracked_media_extensions():
    violations = repo_hygiene.find_violations(
        [
            "plotlot/frontend/public/logo.svg",
            "docs/mockup.png",
            "plotlot/tests/screenshots/state.json",
        ]
    )

    assert ("docs/mockup.png", "tracked-media") in violations


def test_flags_generated_artifact_directories_even_without_media_suffixes():
    violations = repo_hygiene.find_violations(
        [
            "plotlot/frontend/playwright-report/index.html",
            "plotlot/frontend/test-results/.last-run.json",
        ]
    )

    assert (
        "plotlot/frontend/playwright-report/index.html",
        "generated-artifact-directory",
    ) in violations
    assert (
        "plotlot/frontend/test-results/.last-run.json",
        "generated-artifact-directory",
    ) in violations


def test_allows_normal_source_and_docs_files():
    violations = repo_hygiene.find_violations(
        [
            "README.md",
            "plotlot/frontend/public/next.svg",
            "plotlot/src/plotlot/api/main.py",
        ]
    )

    assert violations == []
