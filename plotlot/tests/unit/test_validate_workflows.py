from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_workflow_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / "validate_workflows.py"
    spec = importlib.util.spec_from_file_location("plotlot_validate_workflows", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


workflow_policy = _load_workflow_module()


def test_validate_workflow_text_flags_stale_official_action_major() -> None:
    # Given: a workflow uses stale official GitHub action majors.
    workflow = """
name: CI
on: [push]
jobs:
  quality:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v6
        with:
          persist-credentials: false
      - uses: actions/github-script@v8
        with:
          script: core.notice("ok")
"""

    # When: CI policy validates the workflow text.
    violations = workflow_policy.validate_workflow_text(".github/workflows/ci.yml", workflow)

    # Then: the stale official action refs are rejected.
    reasons = {violation.reason for violation in violations}
    assert "checkout-action-version" in reasons
    assert "official-action-version" in reasons


def test_validate_workflow_text_accepts_current_official_action_majors() -> None:
    # Given: a workflow uses verified current official action majors.
    workflow = """
name: CI
on: [push]
jobs:
  quality:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-node@v6
      - uses: actions/upload-artifact@v7
        with:
          name: artifacts
          path: test-results
      - uses: actions/github-script@v9
        with:
          script: core.notice("ok")
"""

    # When: CI policy validates the workflow text.
    violations = workflow_policy.validate_workflow_text(".github/workflows/ci.yml", workflow)

    # Then: current official action refs satisfy the workflow policy.
    assert violations == []


def test_validate_required_ci_workflow_text_flags_missing_release_gates() -> None:
    # Given: the CI workflow omits required lookup-correctness and frontend gates.
    workflow = """
name: CI
on: [push]
jobs:
  frontend-quality:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    permissions:
      contents: read
    steps:
      - run: npm run lint
      - run: npx tsc --noEmit
"""

    # When: required CI workflow commands are validated.
    violations = workflow_policy.validate_required_ci_workflow_text(workflow)

    # Then: the missing harness release gates are rejected.
    reasons = {violation.reason for violation in violations}
    assert "missing-ci-repo-hygiene" in reasons
    assert "missing-ci-workflow-policy" in reasons
    assert "missing-ci-backend-unit" in reasons
    assert "missing-ci-lookup-agentic-goldset" in reasons
    assert "missing-ci-frontend-build" in reasons
    assert "missing-ci-playwright-no-db" in reasons
    assert "missing-ci-playwright-db" in reasons
