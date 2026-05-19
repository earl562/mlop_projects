"""Unit tests for branch shipping helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


def _load_ship_branch_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / "ship_branch.py"
    spec = importlib.util.spec_from_file_location("plotlot_ship_branch", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ship_branch = _load_ship_branch_module()


def test_validate_branch_name_accepts_standard_prefixes():
    for branch in (
        "codex/fix-deploy",
        "dev/workflow",
        "feat/plotlot",
        "fix/render",
        "hotfix/mainline",
    ):
        ship_branch.validate_branch_name(branch)


def test_validate_branch_name_rejects_main():
    with pytest.raises(ValueError, match="Refusing to ship from main"):
        ship_branch.validate_branch_name("main")


def test_validate_branch_name_rejects_nonstandard_prefix():
    with pytest.raises(ValueError, match="approved delivery prefix"):
        ship_branch.validate_branch_name("feature/custom")


def test_tracked_changes_present_only_flags_nonempty_output():
    assert ship_branch.tracked_changes_present("") is False
    assert ship_branch.tracked_changes_present(" M plotlot/render.yaml\n") is True


def test_build_pr_body_mentions_doctor_and_verify_steps():
    body = ship_branch.build_pr_body("codex/deploy-fixes", "main")

    assert "deploy-doctor" in body
    assert "verify-local" in body
    assert "codex/deploy-fixes" in body
