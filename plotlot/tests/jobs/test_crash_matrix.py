from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_crash_matrix_observes_real_restart_and_external_idempotency() -> None:
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
    payload = json.loads(result.stdout)
    assert len(payload["scenarios"]) == 5
    assert payload["services"]["engine_pid"] != payload["services"]["webhook_pid"]
    for scenario in payload["scenarios"]:
        assert scenario["api"]["before_pid"] != scenario["api"]["after_pid"]
        assert scenario["api"]["health_before"] == 200
        assert scenario["api"]["health_after"] == 200
        assert scenario["worker"]["before_pid"] != scenario["worker"]["after_pid"]
        assert len(set(scenario["worker"]["contender_pids"])) == 4
        assert scenario["worker"]["before_pid"] in scenario["worker"]["contender_pids"]
        assert scenario["worker"]["killed"]
        assert scenario["database"]["connection_severed"]
        assert scenario["database"]["before_start_time"] != scenario["database"]["after_start_time"]
        assert scenario["engine"]["effects"] == 1
        expected_engine_attempts = 2 if scenario["kill_point"] == "engine-returned" else 1
        assert scenario["engine"]["attempts"] == expected_engine_attempts
        assert scenario["terminal"]["results"] == 1
        assert scenario["terminal"]["engine_run_id"] == scenario["engine"]["run_id"]
        assert scenario["terminal"]["engine_revision_id"] == scenario["engine"]["revision_id"]
        assert scenario["outbox"]["host_link"] == scenario["engine"]["host_link"]
        assert scenario["webhook"]["effects"] == 1
        assert scenario["outbox"]["receipts"] == 1
        assert scenario["outbox"]["provider_receipt_id"] == scenario["webhook"]["receipt_id"]
        expected_attempts = 2 if scenario["kill_point"] == "webhook-sent" else 1
        assert scenario["webhook"]["attempts"] == expected_attempts
