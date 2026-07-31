"""Contract test for the MLflow test fixture (slice 0.2).

The autouse fixture in tests/conftest.py::_disable_mlflow_tracing enables MLflow
tracing in teardown against a file-store URI. Newer MLflow versions put file-store
in maintenance mode and refuse enable() unless MLFLOW_ALLOW_FILE_STORE=true.

This test pins that the fixture is self-contained: it sets the opt-in env var
itself, so the gate is green regardless of shell environment. Regression guard
for the 1672-error teardown failure that blocked `make verify-local` on dev.
"""

from __future__ import annotations

import mlflow


def test_disable_mlflow_fixture_does_not_raise_on_filestore_teardown():
    """Fixture teardown must succeed against a file-store URI.

    Reproduces the original failure: MLflow raises MlflowTracingException when
    tracing.enable() targets a file:// URI without MLFLOW_ALLOW_FILE_STORE=true.
    The fixture (or the verify script) must set this env var so the gate passes
    on a pristine checkout with no shell configuration.
    """
    # Point MLflow at a file-store URI (what the fixture + verify script do).
    file_uri = "file:///tmp/plotlot-mlflow-tests"
    mlflow.set_tracking_uri(file_uri)

    # This must not raise MlflowTracingException. If the fixture sets the env
    # var itself, enable() succeeds against the file-store URI.
    try:
        mlflow.tracing.disable()
        mlflow.tracing.enable()
    finally:
        mlflow.tracing.disable()


def test_verify_script_sets_allow_file_store_env():
    """The verify_local_success.sh gate must export MLFLOW_ALLOW_FILE_STORE=true
    alongside MLFLOW_TRACKING_URI=file:///... so the gate is green on pristine dev."""
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts" / "verify_local_success.sh"
    content = script.read_text()
    assert "MLFLOW_ALLOW_FILE_STORE=true" in content, (
        "verify_local_success.sh must set MLFLOW_ALLOW_FILE_STORE=true when "
        "using a file:// MLFLOW_TRACKING_URI, or MLflow teardown raises on "
        "every test. See slice 0.2."
    )
