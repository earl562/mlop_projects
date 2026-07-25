from __future__ import annotations

from plotlot.harness.calculation_store import LocalCalculationLedger
from plotlot.harness.contracts import CalculationResult, RunId


def test_local_calculation_ledger_saves_lists_and_reads_by_id(tmp_path) -> None:
    # Given: an empty local calculation ledger and a typed calculation result.
    ledger = LocalCalculationLedger(tmp_path / "calculations.json")
    calculation = CalculationResult(
        calculation_id="calc_fixture_001",
        run_id=RunId("run_fixture_001"),
        calculation_type="residual_land_value",
        inputs={"as_built_value": 1_235_000},
        assumptions={},
        outputs={"max_supportable_land_price": 195_000},
        formula_version="residual_land_value.v1",
    )

    # When: the calculation is persisted.
    saved = ledger.save_calculation(calculation)

    # Then: it can be retrieved by id and by run without changing its typed payload.
    assert saved.calculation_id == "calc_fixture_001"
    assert ledger.get_calculation("calc_fixture_001") == calculation
    assert ledger.list_calculations(run_id=RunId("run_fixture_001")) == [calculation]


def test_local_calculation_ledger_orders_calculations_by_created_at(tmp_path) -> None:
    # Given: a local calculation ledger with two calculations for the same run.
    ledger = LocalCalculationLedger(tmp_path / "calculations.json")
    first = CalculationResult(
        calculation_id="calc_fixture_001",
        run_id=RunId("run_fixture_001"),
        calculation_type="noi_valuation",
        inputs={},
        assumptions={},
        outputs={"annual_noi": 74_100},
        formula_version="noi_valuation.v1",
    )
    second = CalculationResult(
        calculation_id="calc_fixture_002",
        run_id=RunId("run_fixture_001"),
        calculation_type="residual_land_value",
        inputs={},
        assumptions={},
        outputs={"max_supportable_land_price": 195_000},
        formula_version="residual_land_value.v1",
    )

    # When: both calculations are persisted.
    ledger.save_calculation(second)
    ledger.save_calculation(first)

    # Then: list output is deterministic by creation timestamp and id.
    assert [item.calculation_id for item in ledger.list_calculations()] == [
        "calc_fixture_001",
        "calc_fixture_002",
    ]
