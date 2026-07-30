from __future__ import annotations

from collections.abc import Callable

from pydantic import Field

from plotlot.harness.contracts import JsonObject, RunId
from plotlot.harness.contracts.base import HarnessContract


class EvalCaseResult(HarnessContract):
    name: str = Field(min_length=1)
    passed: bool
    run_id: RunId | None = None
    failures: list[str] = Field(default_factory=list)
    metrics: JsonObject = Field(default_factory=dict)


class EvalResult(HarnessContract):
    suite: str = Field(min_length=1)
    passed: bool
    cases: list[EvalCaseResult]


EvalSuiteRunner = Callable[[], EvalResult]


def eval_result(suite: str, cases: list[EvalCaseResult]) -> EvalResult:
    return EvalResult(suite=suite, passed=all(case.passed for case in cases), cases=cases)
