"""Every ingestion path must derive typed standards, not just one of them.

The extractor was originally wired only into `acp_coordinator`. But the CLI
(`plotlot-ingest`) — the path that actually ingested all 14 San Diego cities —
reaches the database through `pipeline/ingest.py`, so bulk ingestion never
triggered extraction at all. That is the same defect shape that left
`district_dimensional_standards` empty for months: built, wired somewhere, never
invoked from the path that matters.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.pipeline import ingest as ing


class TestStandardsHook:
    @pytest.mark.asyncio
    async def test_a_successful_extraction_is_reported(self, caplog):
        report = type(
            "R", (), {"districts_found": 10, "summary": lambda self: "El Cajon: 10 districts"}
        )()
        with patch(
            "plotlot.ingestion.standards_extraction.backfill_dimensional_standards",
            new=AsyncMock(return_value=report),
        ) as bf:
            await ing._extract_standards_after_ingest("El Cajon", "CA", "San Diego")
        bf.assert_awaited_once_with("El Cajon", state="CA", county="San Diego")

    @pytest.mark.asyncio
    async def test_a_city_yielding_no_standards_is_warned_about_loudly(self, caplog):
        """Silence is what let this go unnoticed. A city that produced nothing must
        say so — its counts stay LLM-derived and can vary run to run."""
        report = type("R", (), {"districts_found": 0, "summary": lambda self: "x"})()
        with patch(
            "plotlot.ingestion.standards_extraction.backfill_dimensional_standards",
            new=AsyncMock(return_value=report),
        ):
            with caplog.at_level("WARNING"):
                await ing._extract_standards_after_ingest("Santee", "CA", "San Diego")
        assert "stay LLM-derived" in caplog.text

    @pytest.mark.asyncio
    async def test_extraction_failure_never_fails_the_ingest(self, caplog):
        """Chunks are already committed and searchable; losing the standards must
        not lose the ingest."""
        with patch(
            "plotlot.ingestion.standards_extraction.backfill_dimensional_standards",
            new=AsyncMock(side_effect=RuntimeError("db exploded")),
        ):
            with caplog.at_level("WARNING"):
                await ing._extract_standards_after_ingest("Poway", "CA", "San Diego")
        assert "stays on the LLM path" in caplog.text


def test_both_cli_ingestion_leaves_invoke_the_hook():
    """`ingest_county` and `ingest_all` both delegate to `ingest_municipality`, so
    these two leaves are the complete CLI surface. Asserted on the source so the
    wiring cannot be dropped without this failing."""
    import inspect

    for fn in (ing.ingest_municipality, ing.ingest_san_diego):
        src = inspect.getsource(fn)
        assert "_extract_standards_after_ingest" in src, (
            f"{fn.__name__} no longer derives dimensional standards — bulk ingest "
            "would silently leave the city on the non-deterministic LLM path"
        )
