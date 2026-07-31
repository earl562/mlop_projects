from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTEGRATION_DIR))

from plotlot_repository_policy import prohibited_tracked_artifacts  # noqa: E402


class PlotLotRepositoryPolicyTest(unittest.TestCase):
    def test_firebase_debug_logs_are_prohibited_when_tracked(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            root_log = repo / "firebase-debug.log"
            nested_log = repo / "plotlot/firebase-debug.log"
            nested_log.parent.mkdir()
            root_log.write_text("firebase cli debug traffic\n", encoding="utf-8")
            nested_log.write_text("firebase cli debug traffic\n", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(repo), "add", "-f", "."],
                check=True,
            )

            self.assertEqual(
                prohibited_tracked_artifacts(repo),
                ["firebase-debug.log", "plotlot/firebase-debug.log"],
            )

    def test_curated_log_fixtures_and_docs_are_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            fixture = repo / "plotlot/tests/fixtures/expected-output.log"
            example = repo / "docs/examples/session.log"
            fixture.parent.mkdir(parents=True)
            example.parent.mkdir(parents=True)
            fixture.write_text("expected fixture\n", encoding="utf-8")
            example.write_text("curated example\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)

            self.assertEqual(prohibited_tracked_artifacts(repo), [])


if __name__ == "__main__":
    unittest.main()
