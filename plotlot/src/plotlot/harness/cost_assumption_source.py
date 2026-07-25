from __future__ import annotations

from plotlot.harness.contracts import (
    ApplicabilityScope,
    CountyName,
    SourceCatalogEntry,
    SourceLane,
    SourceMode,
)


def load_cost_assumption_source_catalog(source_mode: SourceMode) -> list[SourceCatalogEntry]:
    _require_fixture(source_mode)
    return [
        SourceCatalogEntry(
            source_id="src_cost_assumption_south_florida",
            lane=SourceLane.COST_ASSUMPTIONS,
            provider="plotlot_market_profile",
            source_type="cost_assumption_config",
            jurisdiction="South Florida",
            county=CountyName("Miami-Dade"),
            municipality=None,
            dataset_name="South Florida underwriting market profile",
            layer_name="Regional cost and rental assumptions",
            source_url="https://plotlot.local/cost-model/market:south_florida",
            code_url="https://plotlot.local/cost-model/market:south_florida",
            freshness_policy="fixture_market_profile_requires_verification",
            applicability_scope=ApplicabilityScope.COUNTYWIDE,
            access_status="public",
            metadata={
                "markets": ["Miami-Dade", "Broward", "Palm Beach"],
                "supports": [
                    "construction_cost_psf",
                    "soft_cost_pct",
                    "builder_margin_pct",
                    "impact_fees_per_unit",
                    "monthly_rent_per_unit",
                    "vacancy_pct",
                    "operating_expense_pct",
                    "cap_rate",
                ],
                "source_mode": source_mode.value,
                "verification_note": (
                    "Fixture-backed underwriting market profile; verify live rent, expense, "
                    "and cap-rate evidence before final recommendations."
                ),
            },
        ),
        SourceCatalogEntry(
            source_id="src_rental_market_south_florida",
            lane=SourceLane.COST_ASSUMPTIONS,
            provider="plotlot_market_profile",
            source_type="rental_market_profile",
            jurisdiction="South Florida",
            county=CountyName("Broward"),
            municipality=None,
            dataset_name="South Florida rental market evidence",
            layer_name="Rent, vacancy, opex, and cap-rate defaults",
            source_url="https://plotlot.local/cost-model/market:south_florida/rental",
            code_url="https://plotlot.local/cost-model/market:south_florida/rental",
            freshness_policy="fixture_rental_market_profile_requires_verification",
            applicability_scope=ApplicabilityScope.COUNTYWIDE,
            access_status="public",
            metadata={
                "markets": ["Miami-Dade", "Broward", "Palm Beach"],
                "supports": [
                    "monthly_rent_per_unit",
                    "vacancy_pct",
                    "operating_expense_pct",
                    "cap_rate",
                ],
                "source_mode": source_mode.value,
                "verification_note": (
                    "Fixture-backed rental market evidence; replace with cited live rental "
                    "sources before final underwriting."
                ),
            },
        ),
    ]


def _require_fixture(source_mode: SourceMode) -> None:
    if source_mode is not SourceMode.FIXTURE:
        raise ValueError("cost assumption source catalog is fixture-only in this harness slice")
