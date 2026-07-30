from __future__ import annotations

import json

from plotlot.cli_harness_support import option_value, parse_options
from plotlot.harness.evals import list_eval_suites, run_all_eval_suites, run_eval_suite


def eval_command(args: list[str]) -> int:
    if not args:
        return _usage()
    match args[0]:
        case "suites":
            print(json.dumps({"suites": list_eval_suites()}))
            return 0
        case "run":
            options = parse_options(args[1:])
            suite = option_value(options, "--suite")
            if suite:
                result = run_eval_suite(suite)
                print(
                    json.dumps({"passed": result.passed, "result": result.model_dump(mode="json")})
                )
                return 0 if result.passed else 1
            results = run_all_eval_suites()
            passed = all(result.passed for result in results)
            print(
                json.dumps(
                    {
                        "passed": passed,
                        "results": [result.model_dump(mode="json") for result in results],
                    }
                )
            )
            return 0 if passed else 1
        case _:
            return _usage()


def _usage() -> int:
    print(json.dumps({"error": "usage", "usage": "plotlot eval <suites|run> [--suite SUITE]"}))
    return 2
