from __future__ import annotations

import json
from typing import NoReturn, TypeAlias
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError

from plotlot.harness.contracts import CalculationResult, JsonObject, RunId
from plotlot.harness.underwriting_calculators import (
    run_brrrr_refinance_analysis,
    run_construction_budget,
    run_feasibility,
    run_noi_valuation,
    run_pro_forma,
    run_residual_land_value,
    run_sensitivity_analysis,
)
from plotlot.harness.underwriting_models import (
    AsBuiltValueInput,
    AsBuiltValueResult,
    BRRRRRefinanceInput,
    BRRRRRefinanceResult,
    ConstructionBudgetInput,
    ConstructionBudgetResult,
    FeasibilityInput,
    FeasibilityResult,
    ProFormaInput,
    ProFormaResult,
    ResidualLandValueInput,
    ResidualLandValueResult,
    SensitivityInput,
    SensitivityResult,
)

UnderwritingCalculationOutput: TypeAlias = (
    AsBuiltValueResult
    | BRRRRRefinanceResult
    | ConstructionBudgetResult
    | FeasibilityResult
    | ProFormaResult
    | ResidualLandValueResult
    | SensitivityResult
)


def execute_underwriting_calculation(
    command: str,
    payload: JsonObject,
) -> UnderwritingCalculationOutput:
    match command:
        case "feasibility":
            return run_feasibility(FeasibilityInput.model_validate(payload))
        case "pro-forma":
            return run_pro_forma(ProFormaInput.model_validate(payload))
        case "noi-valuation":
            return run_noi_valuation(AsBuiltValueInput.model_validate(payload))
        case "residual-land-value":
            return run_residual_land_value(ResidualLandValueInput.model_validate(payload))
        case "brrrr":
            return run_brrrr_refinance_analysis(BRRRRRefinanceInput.model_validate(payload))
        case "construction-budget":
            return run_construction_budget(ConstructionBudgetInput.model_validate(payload))
        case "sensitivity":
            return run_sensitivity_analysis(SensitivityInput.model_validate(payload))
        case _:
            raise_unknown_calculator(command)


def build_calculation_result(
    *,
    run_id: RunId,
    inputs: JsonObject,
    output: UnderwritingCalculationOutput,
) -> CalculationResult:
    dumped = output.model_dump(mode="json")
    calculation_type = str(dumped["calculation_type"])
    formula_version = str(dumped["formula_version"])
    return CalculationResult(
        calculation_id=_calculation_id(run_id, calculation_type, inputs, dumped),
        run_id=run_id,
        calculation_type=calculation_type,
        inputs=inputs,
        assumptions={},
        outputs=_output_payload(output),
        formula_version=formula_version,
    )


def calculation_output_json(output: UnderwritingCalculationOutput) -> JsonObject:
    return output.model_dump(mode="json")


def raise_unknown_calculator(command: str) -> NoReturn:
    raise ValidationError.from_exception_data(
        title="unknown_calculator",
        line_errors=[
            {
                "type": "value_error",
                "loc": ("calculator",),
                "input": command,
                "ctx": {"error": "unknown calculator"},
            }
        ],
    )


def _output_payload(output: UnderwritingCalculationOutput) -> JsonObject:
    dumped = output.model_dump(
        mode="json",
        exclude={"calculation_type", "formula_version"},
    )
    return dumped


def _calculation_id(
    run_id: RunId,
    calculation_type: str,
    inputs: JsonObject,
    output: JsonObject,
) -> str:
    fingerprint = json.dumps(
        {
            "run_id": str(run_id),
            "calculation_type": calculation_type,
            "inputs": inputs,
            "outputs": output,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"calc_{uuid5(NAMESPACE_URL, fingerprint).hex[:12]}"
