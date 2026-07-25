from __future__ import annotations

from plotlot.harness.contracts import SourceMode
from plotlot.harness.eval_models import EvalCaseResult, EvalResult, eval_result
from plotlot.harness.municode_source import (
    extract_ordinance_rules,
    get_municode_section,
    search_municode,
)


def municode_suite() -> EvalResult:
    results = search_municode(
        jurisdiction="miami",
        query="parking",
        source_mode=SourceMode.FIXTURE,
    )
    failures: list[str] = []
    if not results:
        failures.append("Municode parking fixture search returned no results")
    if results and results[0].freshness_status.value != "requires_official_verification":
        failures.append("Municode fixture result lost official verification caveat")
    section = get_municode_section("municode_miami_parking_fixture", source_mode=SourceMode.FIXTURE)
    rules = extract_ordinance_rules(section)
    if rules.rules.get("parking_spaces_per_dwelling_unit") != 1.5:
        failures.append("Municode fixture parking rule extraction changed")
    return eval_result(
        "municode",
        [
            EvalCaseResult(
                name="fixture_ordinance_rules",
                passed=not failures,
                failures=failures,
                metrics={"result_count": len(results), "rule_count": len(rules.rules)},
            )
        ],
    )
