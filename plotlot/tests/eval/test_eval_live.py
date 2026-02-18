"""Live evaluation — runs the full pipeline against golden addresses.

Requires: running PostgreSQL with ingested data, API keys for geocoding
and LLM providers. Scores live pipeline output against golden expectations.

Run:
    uv run pytest tests/eval/test_eval_live.py -m "eval and e2e" -v
"""

from dataclasses import fields

import mlflow.genai
import pytest

from plotlot.core.types import ZoningReport
from plotlot.pipeline.lookup import lookup_address


def report_to_outputs(report: ZoningReport) -> dict:
    """Flatten a ZoningReport into the golden data outputs schema."""
    outputs = {
        "zoning_district": report.zoning_district,
        "municipality": report.municipality,
        "county": report.county,
        "confidence": report.confidence,
        "has_summary": bool(report.summary),
        "has_allowed_uses": len(report.allowed_uses) > 0,
        "num_sources": len(report.sources),
    }

    if report.density_analysis:
        outputs["max_units"] = report.density_analysis.max_units
        outputs["governing_constraint"] = report.density_analysis.governing_constraint

    if report.numeric_params:
        params = {}
        for f in fields(report.numeric_params):
            val = getattr(report.numeric_params, f.name)
            if val is not None:
                params[f.name] = val
        outputs["numeric_params"] = params
    else:
        outputs["numeric_params"] = {}

    return outputs


@pytest.mark.eval
@pytest.mark.e2e
class TestLiveEval:
    """Run the full pipeline for each golden address and score results."""

    @pytest.mark.asyncio
    async def test_live_pipeline(self, golden_data, all_scorers):
        """Run pipeline for each golden address, evaluate against expectations."""
        live_data = []

        for sample in golden_data:
            address = sample["inputs"]["address"]
            report = await lookup_address(address)

            if report is None:
                outputs = {
                    "zoning_district": "",
                    "municipality": "",
                    "county": "",
                    "confidence": "low",
                    "max_units": 0,
                    "governing_constraint": "",
                    "numeric_params": {},
                    "has_summary": False,
                    "has_allowed_uses": False,
                    "num_sources": 0,
                }
            else:
                outputs = report_to_outputs(report)

            live_data.append({
                "inputs": sample["inputs"],
                "outputs": outputs,
                "expectations": sample["expectations"],
            })

        result = mlflow.genai.evaluate(data=live_data, scorers=all_scorers)

        # Core identity fields must match
        for key in ["zoning_district_match/mean", "municipality_match/mean"]:
            assert key in result.metrics
            assert result.metrics[key] > 0, f"Live eval failed: {key} = 0"

        # Max units should match for at least one sample
        assert result.metrics.get("max_units_match/mean", 0) > 0
