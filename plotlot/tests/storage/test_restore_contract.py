from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_backup_and_restore_enforce_encryption_and_hash_manifest() -> None:
    backup = (ROOT / "scripts" / "storage" / "backup_storage.sh").read_text(encoding="utf-8")
    restore = (ROOT / "scripts" / "storage" / "restore_storage.sh").read_text(encoding="utf-8")

    assert "aes-256-cbc" in backup
    assert "rpo_minutes" in backup
    assert "rto_hours" in backup
    assert "expected_database_sha" in restore
    assert "expected_objects_sha" in restore
