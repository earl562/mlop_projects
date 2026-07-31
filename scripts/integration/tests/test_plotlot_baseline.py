from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTEGRATION_DIR))

from plotlot_baseline_lib import (  # noqa: E402
    BaselineError,
    create_archive,
    file_record,
    load_manifest,
    run_bounded,
    scan_secret_bytes,
    validate_records,
    verify_restore,
)
from plotlot_git_integrity import source_fingerprint  # noqa: E402
from plotlot_repository_policy import (  # noqa: E402
    assert_no_prohibited_tracked_artifacts,
    rejected_ignored_paths,
)

CLI = INTEGRATION_DIR / "plotlot_freeze_baseline.py"


class PlotLotBaselineTest(unittest.TestCase):
    def test_allowlist_hash_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "plotlot/src/plotlot/example.py"
            target.parent.mkdir(parents=True)
            target.write_text("SAFE = True\n", encoding="utf-8")
            record = file_record(root, "plotlot/src/plotlot/example.py")
            target.write_text("SAFE = False\n", encoding="utf-8")

            with self.assertRaisesRegex(BaselineError, "hash mismatch"):
                validate_records(root, [record])

    def test_secret_shape_is_rejected_without_echoing_value(self) -> None:
        value = b"OPENAI_API_KEY=sk-proj-" + (b"A" * 48)

        with self.assertRaises(BaselineError) as raised:
            scan_secret_bytes(value, "fixture.env")

        self.assertNotIn(value.decode(), str(raised.exception))

    def test_malformed_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest = Path(raw) / "manifest.json"
            manifest.write_text('{"schema": "Wrong"}', encoding="utf-8")

            with self.assertRaisesRegex(BaselineError, "schema"):
                load_manifest(manifest)

    def test_symlink_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            link = root / "plotlot/src/escape.py"
            link.parent.mkdir(parents=True)
            link.symlink_to("../../../../outside")

            with self.assertRaisesRegex(BaselineError, "symlink"):
                file_record(root, "plotlot/src/escape.py")

    def test_restore_mismatch_is_nonzero_after_archive_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            source = temp / "source"
            target = source / "plotlot/src/plotlot/example.py"
            target.parent.mkdir(parents=True)
            target.write_text("VALUE = 1\n", encoding="utf-8")
            records = [file_record(source, "plotlot/src/plotlot/example.py")]
            archive = temp / "baseline.tar.gz"
            receipt = temp / "complete.json"
            create_archive(source, records, archive, receipt)
            restore = temp / "restore"
            restore.mkdir()
            with tarfile.open(archive, "r:gz") as bundle:
                bundle.extractall(restore, filter="data")
            (restore / records[0]["path"]).write_text("VALUE = 2\n", encoding="utf-8")

            with self.assertRaisesRegex(BaselineError, "hash mismatch"):
                verify_restore(restore, records)

    def test_interrupted_archive_has_no_completion_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            source = temp / "source"
            first = source / "plotlot/src/first.py"
            second = source / "plotlot/src/second.py"
            first.parent.mkdir(parents=True)
            first.write_text("FIRST = 1\n", encoding="utf-8")
            second.write_text("SECOND = 2\n", encoding="utf-8")
            records = [
                file_record(source, "plotlot/src/first.py"),
                file_record(source, "plotlot/src/second.py"),
            ]
            receipt = temp / "complete.json"

            with self.assertRaisesRegex(BaselineError, "interrupted"):
                create_archive(
                    source,
                    records,
                    temp / "baseline.tar.gz",
                    receipt,
                    interrupt_after=1,
                )

            self.assertFalse(receipt.exists())

    def test_bounded_command_times_out(self) -> None:
        command = [sys.executable, "-c", "import time; time.sleep(2)"]

        with self.assertRaisesRegex(BaselineError, "timed out"):
            run_bounded(command, timeout_seconds=0.05)

    def test_archive_rejects_unlisted_member(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            archive = temp / "baseline.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                info = tarfile.TarInfo("plotlot/src/unlisted.py")
                payload = b"UNLISTED = True\n"
                info.size = len(payload)
                bundle.addfile(info, io.BytesIO(payload))
            records: list[dict[str, str | int]] = []

            with self.assertRaisesRegex(BaselineError, "unlisted"):
                verify_restore(temp / "restore", records, archive=archive)

    def test_unallowlisted_ignored_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / ".gitignore").write_text("*.ignored\n", encoding="utf-8")
            injected = repo / "plotlot/src/injected.ignored"
            injected.parent.mkdir(parents=True)
            injected.write_text("unexpected\n", encoding="utf-8")

            rejected = rejected_ignored_paths(repo)

            self.assertEqual(rejected, ["plotlot/src/injected.ignored"])

    def test_cli_ignored_injection_discovers_and_rejects_fixture(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "verify",
                "--source",
                "/disposable/source",
                "--clone",
                "/disposable/clone",
                "--manifest",
                "/disposable/manifest.json",
                "--archive",
                "/disposable/archive.tar.gz",
                "--receipt",
                "/disposable/receipt.json",
                "--finalization-receipt",
                "/disposable/finalization.json",
                "--inject-unallowlisted-ignored",
            ],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            "unallowlisted ignored path rejected: plotlot/src/injected.ignored",
            result.stdout,
        )

    def test_tracked_database_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            database = repo / "runtime.db"
            database.write_bytes(b"SQLite format 3\x00")
            subprocess.run(
                ["git", "-C", str(repo), "add", "-f", "runtime.db"],
                check=True,
            )

            with self.assertRaisesRegex(
                BaselineError,
                "prohibited tracked artifact: runtime.db",
            ):
                assert_no_prohibited_tracked_artifacts(repo)

    def test_source_fingerprint_excludes_root_omo_runtime_records(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.name", "Test"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
                check=True,
            )
            tracked = repo / "tracked.txt"
            tracked.write_text("stable\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-qm", "fixture"],
                check=True,
            )
            ledger = repo / ".omo/start-work/ledger.jsonl"
            ledger.parent.mkdir(parents=True)
            ledger.write_text('{"event": 1}\n', encoding="utf-8")
            before = source_fingerprint(repo)
            ledger.write_text('{"event": 2}\n', encoding="utf-8")
            evidence = repo / ".omo/evidence/new-runtime-record.json"
            evidence.parent.mkdir(parents=True)
            evidence.write_text("{}\n", encoding="utf-8")

            self.assertEqual(source_fingerprint(repo), before)

    def test_source_fingerprint_detects_nested_product_omo_records(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.name", "Test"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
                check=True,
            )
            tracked = repo / "tracked.txt"
            tracked.write_text("stable\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-qm", "fixture"],
                check=True,
            )
            baseline = source_fingerprint(repo)
            product = repo / "plotlot/src/plotlot/.omo/product-contract.json"
            product.parent.mkdir(parents=True)
            product.write_text('{"version": 1}\n', encoding="utf-8")
            added = source_fingerprint(repo)
            product.write_text('{"version": 2}\n', encoding="utf-8")
            modified = source_fingerprint(repo)

            self.assertNotEqual(added, baseline)
            self.assertEqual(added["dirty_record_count"], 1)
            self.assertNotEqual(modified, added)

    def test_manifest_requires_exact_record_shape(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manifest = Path(raw) / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": "PlotLotBaselineV1",
                        "source": {"head": "a" * 40, "branch": "feature/test"},
                        "records": [{"path": "../escape"}],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(BaselineError, "record"):
                load_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
