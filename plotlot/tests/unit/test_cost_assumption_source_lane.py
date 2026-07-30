from __future__ import annotations

from plotlot.harness.contracts import SourceLane, SourceMode
from plotlot.harness.cost_assumption_source import load_cost_assumption_source_catalog


def test_cost_assumption_fixture_source_catalog_entries_use_cost_assumptions_lane() -> None:
    catalog = load_cost_assumption_source_catalog(SourceMode.FIXTURE)

    assert catalog
    assert all(entry.lane is SourceLane.COST_ASSUMPTIONS for entry in catalog)
    assert {entry.source_type for entry in catalog} == {
        "cost_assumption_config",
        "rental_market_profile",
    }
    assert any(entry.county == "Miami-Dade" for entry in catalog)
    assert any(entry.county == "Broward" for entry in catalog)
