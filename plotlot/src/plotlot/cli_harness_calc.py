from __future__ import annotations

import json

from pydantic import TypeAdapter, ValidationError

from plotlot.cli_harness_support import option_value, parse_options
from plotlot.harness.calculation_runner import (
    build_calculation_result,
    calculation_output_json,
    execute_underwriting_calculation,
)
from plotlot.harness.calculation_store import (
    CalculationNotFoundError,
    default_calculation_ledger,
)
from plotlot.harness.contracts import JsonObject
from plotlot.harness.contracts.base import RunId

JSON_OBJECT_ADAPTER = TypeAdapter(JsonObject)


def calc_command(args: list[str]) -> int:
    if len(args) < 3:
        print(
            json.dumps({"error": "usage", "usage": "plotlot calc <calculator> --json '<payload>'"})
        )
        return 2
    options = parse_options(args[1:])
    raw_json = option_value(options, "--json")
    if raw_json is None:
        print(
            json.dumps({"error": "usage", "usage": "plotlot calc <calculator> --json '<payload>'"})
        )
        return 2
    try:
        payload = JSON_OBJECT_ADAPTER.validate_json(raw_json)
        output = execute_underwriting_calculation(args[0], payload)
    except ValidationError as exc:
        print(json.dumps({"error": "invalid_input", "detail": exc.errors()}))
        return 2
    run_id = option_value(options, "--run-id")
    if run_id is None:
        print(json.dumps(calculation_output_json(output)))
        return 0
    calculation = build_calculation_result(
        run_id=RunId(run_id),
        inputs=payload,
        output=output,
    )
    default_calculation_ledger().save_calculation(calculation)
    print(json.dumps(calculation.model_dump(mode="json")))
    return 0


def calculations_command(args: list[str]) -> int:
    if not args:
        print(json.dumps({"error": "usage", "usage": "plotlot calculations <list|show>"}))
        return 2
    ledger = default_calculation_ledger()
    try:
        match args[0]:
            case "list":
                options = parse_options(args[1:])
                run_id = option_value(options, "--run-id")
                calculations = ledger.list_calculations(
                    run_id=None if run_id is None else RunId(run_id)
                )
                print(
                    json.dumps(
                        {"calculations": [item.model_dump(mode="json") for item in calculations]}
                    )
                )
                return 0
            case "show" if len(args) >= 2:
                print(json.dumps(ledger.get_calculation(args[1]).model_dump(mode="json")))
                return 0
            case _:
                print(json.dumps({"error": "usage", "usage": "plotlot calculations <list|show>"}))
                return 2
    except CalculationNotFoundError as exc:
        print(json.dumps({"error": "calculation_not_found", "detail": str(exc)}))
        return 1
