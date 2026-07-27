from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from plotlot.storage.migration_guard import MigrationGraphError, validate_revision_graph


ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "alembic" / "versions"


@pytest.mark.parametrize("locale_name", ["C", "C.UTF-8"])
def test_alembic_has_one_head_under_supported_locales(locale_name: str) -> None:
    env = {**os.environ, "LC_ALL": locale_name}
    result = subprocess.run(
        ["uv", "run", "alembic", "heads"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert len([line for line in result.stdout.splitlines() if "(head)" in line]) == 1


def test_duplicate_revision_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "versions"
    shutil.copytree(VERSIONS, target)
    duplicate = target / "duplicate.py"
    duplicate.write_text(
        'revision = "001"\ndown_revision = None\n',
        encoding="utf-8",
    )

    with pytest.raises(MigrationGraphError, match="duplicate revision"):
        validate_revision_graph(target)


def test_runtime_database_initialization_has_no_ddl() -> None:
    source = (ROOT / "src" / "plotlot" / "storage" / "db.py").read_text(encoding="utf-8")

    assert "create_all" not in source
    assert "CREATE TABLE" not in source
    assert "CREATE EXTENSION" not in source
