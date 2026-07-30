from __future__ import annotations

import json

from plotlot.cli_harness_support import (
    ParsedOption,
    assumptions_from_options,
    option_value,
    parse_options,
    source_mode_option,
)
from plotlot.harness.contracts import ExecutionMode, JobId
from plotlot.harness.fixture_runs import FixtureDealRunRequest
from plotlot.harness.job_execution import JobExecutionFailure, StaticJobFailureRunner
from plotlot.harness.job_queue import (
    HarnessJobCancellationRequest,
    HarnessJobNotFoundError,
    JobCancellationBlockedError,
    LocalHarnessJobQueue,
    default_harness_job_queue,
)
from plotlot.harness.run_persistence import default_fixture_run_persistence_stores


def jobs_command(args: list[str]) -> int:
    if not args:
        print(json.dumps({"error": "usage", "usage": _jobs_usage()}))
        return 2
    queue = default_harness_job_queue()
    try:
        match args[0]:
            case "create":
                return _jobs_create(args[1:], queue)
            case "list":
                print(
                    json.dumps({"jobs": [job.model_dump(mode="json") for job in queue.list_jobs()]})
                )
                return 0
            case "show" if len(args) >= 2:
                print(json.dumps(queue.get_job(JobId(args[1])).model_dump(mode="json")))
                return 0
            case "events" if len(args) >= 2:
                events = [
                    event.model_dump(mode="json") for event in queue.get_events(JobId(args[1]))
                ]
                print(json.dumps({"job_id": args[1], "events": events}))
                return 0
            case "cancel" if len(args) >= 2:
                options = parse_options(args[2:])
                cancelled_job = queue.cancel_job(
                    HarnessJobCancellationRequest(
                        job_id=JobId(args[1]),
                        actor_user_id=option_value(options, "--actor-user-id") or "cli",
                        reason=option_value(options, "--reason") or "Cancellation requested.",
                        execution_mode=ExecutionMode.CLI,
                    )
                )
                print(json.dumps(cancelled_job.model_dump(mode="json")))
                return 0
            case "run-next":
                options = parse_options(args[1:])
                fixture_failure = option_value(options, "--fixture-failure")
                if fixture_failure is None:
                    next_job = queue.run_next(default_fixture_run_persistence_stores())
                else:
                    next_job = queue.run_next(
                        default_fixture_run_persistence_stores(),
                        runner=StaticJobFailureRunner(
                            JobExecutionFailure(
                                code="fixture_failure",
                                message=fixture_failure,
                            )
                        ),
                    )
                print(
                    json.dumps(
                        {"status": "idle"} if next_job is None else next_job.model_dump(mode="json")
                    )
                )
                return 0
            case _:
                print(json.dumps({"error": "usage", "usage": _jobs_usage()}))
                return 2
    except HarnessJobNotFoundError as exc:
        print(json.dumps({"error": "job_not_found", "detail": str(exc)}))
        return 1
    except JobCancellationBlockedError as exc:
        print(
            json.dumps(
                {
                    "error": "job_cancellation_blocked",
                    "detail": str(exc),
                    "current_status": exc.current_status,
                }
            )
        )
        return 1


def _jobs_create(args: list[str], queue: LocalHarnessJobQueue) -> int:
    options = parse_options(args)
    address = option_value(options, "--address")
    if address is None:
        print(json.dumps({"error": "missing_address"}))
        return 2
    max_attempts = _max_attempts_option(options)
    if max_attempts is None:
        print(
            json.dumps(
                {
                    "error": "invalid_max_attempts",
                    "detail": "--max-attempts must be a positive integer.",
                }
            )
        )
        return 2
    analysis_type = (option_value(options, "--analysis-type") or "acquisition_memo").replace(
        "-", "_"
    )
    job = queue.create_analysis_job(
        FixtureDealRunRequest(
            address=address,
            analysis_type=analysis_type,
            source_mode=source_mode_option(options),
            execution_mode=ExecutionMode.WORKER,
            assumptions=assumptions_from_options(options),
        ),
        idempotency_key=option_value(options, "--idempotency-key"),
        max_attempts=max_attempts,
    )
    print(json.dumps(job.model_dump(mode="json")))
    return 0


def _max_attempts_option(options: ParsedOption) -> int | None:
    value = option_value(options, "--max-attempts")
    if value is None:
        return 3
    if not value.isdigit():
        return None
    parsed = int(value)
    if parsed < 1:
        return None
    return parsed


def _jobs_usage() -> str:
    return "plotlot jobs <create|list|show|events|cancel|run-next> [--max-attempts N]"
