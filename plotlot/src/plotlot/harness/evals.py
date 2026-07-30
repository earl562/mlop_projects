from __future__ import annotations

from plotlot.harness.eval_ordinance_suites import municode_suite
from plotlot.harness.eval_models import EvalCaseResult, EvalResult, EvalSuiteRunner, eval_result
from plotlot.harness.five_address_eval import south_florida_five_address_suite
from plotlot.harness.eval_suites import (
    evidence_suite,
    harness_suite,
    health_suite,
    manual_offer_suite,
    south_florida_address_paths_live_suite,
    south_florida_address_paths_suite,
    south_florida_gis_suite,
    training_discovery_suite,
    underwriting_suite,
)


def list_eval_suites() -> list[str]:
    return sorted(_EVAL_SUITES)


def run_all_eval_suites() -> list[EvalResult]:
    return [run_eval_suite(suite) for suite in list_eval_suites()]


def run_eval_suite(suite: str) -> EvalResult:
    runner = _EVAL_SUITES.get(suite)
    if runner is None:
        return eval_result(
            suite,
            [
                EvalCaseResult(
                    name="suite_registered",
                    passed=False,
                    failures=["unknown eval suite"],
                )
            ],
        )
    return runner()


_EVAL_SUITES: dict[str, EvalSuiteRunner] = {
    "evidence": evidence_suite,
    "harness": harness_suite,
    "health": health_suite,
    "manual-offer-workflows": manual_offer_suite,
    "municode": municode_suite,
    "south-florida-address-paths-live": south_florida_address_paths_live_suite,
    "south-florida-address-paths": south_florida_address_paths_suite,
    "south-florida-five-addresses": south_florida_five_address_suite,
    "south-florida-gis": south_florida_gis_suite,
    "training-discovery": training_discovery_suite,
    "underwriting": underwriting_suite,
}
