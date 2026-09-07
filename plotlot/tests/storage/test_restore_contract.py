from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_backup_and_restore_delegate_versioned_objects_to_application_archive() -> None:
    backup = (ROOT / "scripts" / "storage" / "backup_storage.sh").read_text(encoding="utf-8")
    restore = (ROOT / "scripts" / "storage" / "restore_storage.sh").read_text(encoding="utf-8")

    assert "plotlot.storage.backup" in backup
    assert "backup_crypto decrypt" in restore
    assert "archive validate" in restore
    assert "expected_database_sha" in restore
    assert "expected_objects_sha" in restore
    assert "plotlot.storage.archive restore" in restore
    assert "plotlot.storage.restore" in restore
    assert "STORAGE_OBJECT_DIR" not in backup
    assert "--database-url" not in restore
