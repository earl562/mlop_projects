from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from plotlot.harness.calculation_runner import UnderwritingCalculationOutput, build_calculation_result
from plotlot.harness.calculation_store import CalculationNotFoundError, default_calculation_ledger
from plotlot.harness.contracts import JsonObject, RunId
from plotlot.harness.underwriting_calculators import (
    run_brrrr_refinance_analysis,
    run_construction_budget,
    run_feasibility,
    run_pro_forma,
    run_residual_land_value,
    run_sensitivity_analysis,
)
from plotlot.harness.underwriting_models import (
    AsBuiltValueInput,
    BRRRRRefinanceInput,
    ConstructionBudgetInput,
    FeasibilityInput,
    ProFormaInput,
    ResidualLandValueInput,
    SensitivityInput,
)

router = APIRouter(prefix="/api/v1", tags=["harness-calculations"])


class FeasibilityCalculationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str | None = None
    input: FeasibilityInput


class NoiValuationCalculationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str | None = None
    input: AsBuiltValueInput


class ProFormaCalculationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str | None = None
    input: ProFormaInput


class ResidualLandValueCalculationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str | None = None
    input: ResidualLandValueInput


class BRRRRRefinanceCalculationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str | None = None
    input: BRRRRRefinanceInput


class ConstructionBudgetCalculationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str | None = None
    input: ConstructionBudgetInput


class SensitivityCalculationRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str | None = None
    input: SensitivityInput


@router.post("/deal-analysis/feasibility")
async def deal_analysis_feasibility(body: FeasibilityCalculationRequest) -> JsonObject:
    output = run_feasibility(body.input)
    return _persisted_or_output(body.run_id, body.input.model_dump(mode="json"), output)


@router.post("/deal-analysis/pro-forma")
async def deal_analysis_pro_forma(body: ProFormaCalculationRequest) -> JsonObject:
    output = run_pro_forma(body.input)
    return _persisted_or_output(body.run_id, body.input.model_dump(mode="json"), output)


@router.post("/deal-analysis/residual-land-value")
async def deal_analysis_residual_land_value(
    body: ResidualLandValueCalculationRequest,
) -> JsonObject:
    output = run_residual_land_value(body.input)
    return _persisted_or_output(body.run_id, body.input.model_dump(mode="json"), output)


@router.post("/deal-analysis/brrrr-refinance")
async def deal_analysis_brrrr_refinance(body: BRRRRRefinanceCalculationRequest) -> JsonObject:
    output = run_brrrr_refinance_analysis(body.input)
    return _persisted_or_output(body.run_id, body.input.model_dump(mode="json"), output)


@router.post("/deal-analysis/construction-budget")
async def deal_analysis_construction_budget(
    body: ConstructionBudgetCalculationRequest,
) -> JsonObject:
    output = run_construction_budget(body.input)
    return _persisted_or_output(body.run_id, body.input.model_dump(mode="json"), output)


@router.post("/deal-analysis/sensitivity")
async def deal_analysis_sensitivity(body: SensitivityCalculationRequest) -> JsonObject:
    output = run_sensitivity_analysis(body.input)
    return _persisted_or_output(body.run_id, body.input.model_dump(mode="json"), output)


@router.get("/harness/runs/{run_id}/calculations")
async def harness_run_calculations(run_id: str) -> JsonObject:
    calculations = default_calculation_ledger().list_calculations(run_id=RunId(run_id))
    return {"run_id": run_id, "calculations": [item.model_dump(mode="json") for item in calculations]}


@router.get("/calculations/{calculation_id}")
async def harness_calculation(calculation_id: str) -> JsonObject:
    try:
        calculation = default_calculation_ledger().get_calculation(calculation_id)
    except CalculationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return calculation.model_dump(mode="json")


def _persisted_or_output(
    run_id: str | None,
    inputs: JsonObject,
    output: UnderwritingCalculationOutput,
) -> JsonObject:
    if run_id is None:
        return output.model_dump(mode="json")
    calculation = build_calculation_result(
        run_id=RunId(run_id),
        inputs=inputs,
        output=output,
    )
    saved = default_calculation_ledger().save_calculation(calculation)
    return saved.model_dump(mode="json")
