"""Unit tests for repository hygiene rules."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


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


def test_allows_static_product_media_in_canonical_public_directory():
    violations = repo_hygiene.find_violations(
        [
            "plotlot/frontend/public/plotlot-assets/hero-aerial-clean.png",
            "plotlot/frontend/public/plotlot-assets/card.jpg",
        ]
    )

    assert violations == []


def test_flags_tracked_duplicate_frontend_roots():
    violations = repo_hygiene.find_violations(
        [
            "frontend/package.json",
            "apps/plotlot/frontend/src/app/page.tsx",
            "apps/plotlot/frontend/public/generated.png",
            "plotlot/frontend/src/app/page.tsx",
        ]
    )

    assert ("frontend/package.json", "non-canonical-frontend-root") in violations
    assert (
        "apps/plotlot/frontend/src/app/page.tsx",
        "non-canonical-frontend-root",
    ) in violations
    assert (
        "apps/plotlot/frontend/public/generated.png",
        "non-canonical-frontend-root",
    ) in violations
    assert (
        "plotlot/frontend/src/app/page.tsx",
        "non-canonical-frontend-root",
    ) not in violations


def test_list_tracked_files_uses_repo_root_for_git_lookup(tmp_path: Path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, *, check, capture_output, text):
        assert check is True
        assert capture_output is True
        assert text is False
        calls.append(args)
        return SimpleNamespace(stdout=b"README.md\x00plotlot/frontend/package.json\x00")

    monkeypatch.setattr(repo_hygiene.subprocess, "run", fake_run)

    paths = repo_hygiene.list_tracked_files(tmp_path)

    assert paths == ["README.md", "plotlot/frontend/package.json"]
    assert calls == [["git", "-C", str(tmp_path), "ls-files", "-z"]]
