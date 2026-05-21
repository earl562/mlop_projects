"""Unit tests for deploy-artifact cleanup."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_cleanup_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / "clean_deploy_artifacts.py"
    spec = importlib.util.spec_from_file_location("plotlot_clean_deploy_artifacts", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cleanup = _load_cleanup_module()


def test_existing_transient_paths_only_returns_known_targets(tmp_path: Path):
    (tmp_path / ".mypy_cache").mkdir()
    (tmp_path / "plotlot" / "frontend" / ".next").mkdir(parents=True)
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    (tmp_path / "plotlot" / "frontend" / "src").mkdir(parents=True)

    found = {
        path.relative_to(tmp_path).as_posix() for path in cleanup.existing_transient_paths(tmp_path)
    }

    assert ".mypy_cache" in found
    assert "plotlot/frontend/.next" in found
    assert "frontend/node_modules" in found
    assert "plotlot/frontend/src" not in found


def test_clean_removes_only_transient_artifacts(tmp_path: Path):
    transient_dir = tmp_path / "plotlot" / "frontend" / ".next"
    transient_dir.mkdir(parents=True)
    (transient_dir / "trace").write_text("artifact", encoding="utf-8")

    transient_file = tmp_path / ".coverage"
    transient_file.write_text("coverage", encoding="utf-8")

    keep_dir = tmp_path / "plotlot" / "frontend" / "src"
    keep_dir.mkdir(parents=True)
    keep_file = keep_dir / "page.tsx"
    keep_file.write_text("export default function Page() { return null; }", encoding="utf-8")

    removed = cleanup.clean(tmp_path)

    removed_paths = {path.relative_to(tmp_path).as_posix() for path in removed}
    assert "plotlot/frontend/.next" in removed_paths
    assert ".coverage" in removed_paths
    assert not transient_dir.exists()
    assert not transient_file.exists()
    assert keep_file.exists()
