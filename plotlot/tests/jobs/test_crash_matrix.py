from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from plotlot.harness.job_queue_storage import PostgresJobQueueStorage


ROOT = Path(__file__).resolve().parents[2]


def test_crash_matrix_reports_one_terminal_revision_and_receipt(
    job_store: PostgresJobQueueStorage,
) -> None:
    del job_store
    result = subprocess.run(
        [
            sys.executable,
            "scripts/test/job_crash_matrix.py",
            "--workers",
            "4",
            "--kill-points",
            "claimed,started,engine-returned,outbox-written,webhook-sent",
            "--restart",
            "api,worker,database",
        ],
        cwd=ROOT,
        env=os.environ,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert '"terminal_results": 1' in result.stdout
    assert '"notification_receipts": 1' in result.stdout
    assert '"double_claims": 0' in result.stdout
