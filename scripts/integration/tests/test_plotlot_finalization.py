from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTEGRATION_DIR))

from plotlot_baseline_lib import BaselineError  # noqa: E402
from plotlot_finalization import (  # noqa: E402
    FinalizationPaths,
    create_finalization_receipt,
    verify_finalization_receipt,
)


class PlotLotFinalizationTest(unittest.TestCase):
    def _fixture(self, root: Path) -> FinalizationPaths:
        clone = root / "clone"
        subprocess.run(["git", "init", "-q", str(clone)], check=True)
        subprocess.run(
            ["git", "-C", str(clone), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(clone), "config", "user.email", "test@example.com"],
            check=True,
        )
        tracked = clone / "tracked.txt"
        tracked.write_text("one\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(clone), "add", "tracked.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(clone), "commit", "-qm", "fixture"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(clone), "switch", "-qc", "feature/expected"],
            check=True,
        )
        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps({"required_clone_branch": "feature/expected"}),
            encoding="utf-8",
        )
        archive = root / "archive.tar.gz"
        archive.write_bytes(b"archive")
        completion = root / "archive-complete.json"
        completion.write_text('{"status":"complete"}\n', encoding="utf-8")
        return FinalizationPaths(
            clone=clone,
            manifest=manifest,
            archive=archive,
            completion_receipt=completion,
            finalization_receipt=root / "finalization.json",
        )

    def test_exact_commit_and_branch_validate(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = self._fixture(Path(raw))

            create_finalization_receipt(paths)

            verify_finalization_receipt(paths)

    def test_commit_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = self._fixture(Path(raw))
            create_finalization_receipt(paths)
            (paths.clone / "tracked.txt").write_text("two\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(paths.clone), "commit", "-qam", "drift"],
                check=True,
            )

            with self.assertRaisesRegex(BaselineError, "commit drift"):
                verify_finalization_receipt(paths)

    def test_branch_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            paths = self._fixture(Path(raw))
            create_finalization_receipt(paths)
            subprocess.run(
                ["git", "-C", str(paths.clone), "switch", "-qc", "feature/drift"],
                check=True,
            )

            with self.assertRaisesRegex(BaselineError, "branch drift"):
                verify_finalization_receipt(paths)


if __name__ == "__main__":
    unittest.main()
