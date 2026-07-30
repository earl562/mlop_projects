from __future__ import annotations

import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from plotlot.harness.contracts import JobId
from plotlot.harness.fixture_runs import FixtureDealRunRequest
from plotlot.harness.job_models import HarnessJob, HarnessJobQueueSnapshot

JOB_STORE_PATH_ENV = "PLOTLOT_HARNESS_JOB_STORE_PATH"


class LocalHarnessJobQueueStorage:
    def __init__(self, path: Path) -> None:
        self._path = path

    def read_snapshot(self) -> HarnessJobQueueSnapshot:
        if not self._path.exists():
            return HarnessJobQueueSnapshot()
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return HarnessJobQueueSnapshot()
        return HarnessJobQueueSnapshot.model_validate_json(raw)

    def save_job(self, snapshot: HarnessJobQueueSnapshot, job: HarnessJob) -> None:
        jobs = dict(snapshot.jobs)
        jobs[str(job.job_id)] = job
        self.write_snapshot(HarnessJobQueueSnapshot(jobs=jobs))

    def write_snapshot(self, snapshot: HarnessJobQueueSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


def find_job_by_idempotency_key(
    snapshot: HarnessJobQueueSnapshot,
    idempotency_key: str,
) -> HarnessJob | None:
    return next(
        (job for job in snapshot.jobs.values() if job.idempotency_key == idempotency_key),
        None,
    )


def new_job_id(request: FixtureDealRunRequest, idempotency_key: str | None) -> JobId:
    if idempotency_key is None:
        return JobId(f"job_{uuid4().hex[:12]}")
    raw = f"{request.address}:{request.analysis_type}:{idempotency_key}"
    return JobId(f"job_{uuid5(NAMESPACE_URL, raw).hex[:12]}")


def default_harness_job_store_path() -> Path:
    configured = os.environ.get(JOB_STORE_PATH_ENV)
    if configured:
        return Path(configured).expanduser()
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return base / "plotlot" / "harness-jobs.json"
