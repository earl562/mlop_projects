"""Tests for LLM-proposed, deterministically-verified local density overrides.

The LLM only proposes; the deterministic verifier is the safety mechanism. These
tests prove a fabricated quote, a misread number, or a wrong-field quote are all
rejected, and that only a genuinely corroborated override is applied.
"""

from dataclasses import dataclass

import pytest

from plotlot.core.types import DensityUplift, UpliftProgram
from plotlot.pipeline.local_overrides import (
    apply_local_overrides,
    get_local_overrides,
    propose_local_overrides,
    verify_local_overrides,
)


@dataclass
class _Chunk:
    chunk_text: str
    section: str = "Sec. 143.1"


# Real-ish San Diego-style local provision.
ORDINANCE = (
    "Within a Transit Priority Area, up to 4 accessory dwelling units are permitted "
    "on a lot in addition to the base density. The Complete Communities program "
    "provides a density bonus of 75 percent for qualifying affordable projects."
)


def _results():
    return [_Chunk(ORDINANCE)]


class TestVerifier:
    def test_verified_when_quote_real_and_number_present(self):
        proposed = [
            {
                "field": "local_adu_additional",
                "value": 4,
                "quote": "up to 4 accessory dwelling units are permitted on a lot",
            }
        ]
        out = verify_local_overrides(proposed, _results())
        assert out[0].status == "verified"

    def test_fabricated_quote_rejected(self):
        proposed = [
            {
                "field": "local_adu_additional",
                "value": 8,
                "quote": "up to 8 accessory dwelling units are permitted by special bonus",
            }
        ]
        out = verify_local_overrides(proposed, _results())
        assert out[0].status == "unverified"
        assert "not found verbatim" in out[0].note

    def test_number_not_in_quote_rejected(self):
        # Quote is real, but the proposed value (6) isn't in it.
        proposed = [
            {
                "field": "local_adu_additional",
                "value": 6,
                "quote": "up to 4 accessory dwelling units are permitted on a lot",
            }
        ]
        out = verify_local_overrides(proposed, _results())
        assert out[0].status == "unverified"
        assert "does not appear" in out[0].note

    def test_wrong_field_keywords_rejected(self):
        # Real quote with the number, but it's not about ADUs.
        proposed = [
            {
                "field": "local_adu_additional",
                "value": 75,
                "quote": "provides a density bonus of 75 percent for qualifying affordable projects",
            }
        ]
        out = verify_local_overrides(proposed, _results())
        assert out[0].status == "unverified"
        assert "expected terms" in out[0].note

    def test_density_bonus_verified(self):
        proposed = [
            {
                "field": "local_density_bonus_pct",
                "value": 75,
                "quote": "density bonus of 75 percent for qualifying affordable projects",
            }
        ]
        out = verify_local_overrides(proposed, _results())
        assert out[0].status == "verified"


class TestApply:
    def test_verified_override_adds_local_program(self):
        uplift = DensityUplift(
            base_units=10,
            state="CA",
            programs=[UpliftProgram(name="ADU (detached)", statute="x", potential_units=12)],
            max_potential_units=12,
        )
        verified = verify_local_overrides(
            [
                {
                    "field": "local_density_bonus_pct",
                    "value": 75,
                    "quote": "density bonus of 75 percent for qualifying affordable projects",
                }
            ],
            _results(),
        )
        apply_local_overrides(uplift, verified)
        local = next(p for p in uplift.programs if p.source == "local")
        assert local.additional_units == 7  # floor(10 × 0.75)
        assert local.potential_units == 17
        assert uplift.max_potential_units == 17  # local beats state ADU's 12

    def test_unverified_override_not_applied_but_noted(self):
        uplift = DensityUplift(base_units=10, state="CA", max_potential_units=10)
        unverified = verify_local_overrides(
            [{"field": "local_adu_additional", "value": 9, "quote": "fabricated text"}],
            _results(),
        )
        apply_local_overrides(uplift, unverified)
        assert all(p.source != "local" for p in uplift.programs)
        assert any("not verified" in n.lower() for n in uplift.notes)
        assert uplift.max_potential_units == 10  # unchanged


class TestProposerGuards:
    async def test_no_text_returns_empty(self):
        assert await propose_local_overrides("San Diego", "RM-3-7", []) == []

    async def test_llm_failure_degrades_to_empty(self, monkeypatch):
        async def _boom(*a, **k):
            raise RuntimeError("provider down")

        monkeypatch.setattr("plotlot.retrieval.llm.call_llm", _boom)
        assert await propose_local_overrides("San Diego", "RM-3-7", _results()) == []

    async def test_get_local_overrides_never_raises_on_failure(self, monkeypatch):
        async def _boom(*a, **k):
            raise RuntimeError("provider down")

        monkeypatch.setattr("plotlot.retrieval.llm.call_llm", _boom)
        uplift = DensityUplift(base_units=10, state="CA", max_potential_units=10)
        await get_local_overrides(uplift, "San Diego", "RM-3-7", _results())
        assert uplift.max_potential_units == 10  # untouched

    async def test_fabricated_llm_proposal_is_rejected_end_to_end(self, monkeypatch):
        async def _fake_call(messages, tools=None):
            return {
                "tool_calls": [
                    {
                        "function": {
                            "name": "report_local_density_overrides",
                            "arguments": (
                                '{"local_adu_additional": 12, '
                                '"local_adu_quote": "the city grants 12 bonus ADUs everywhere", '
                                '"local_density_bonus_pct": null, '
                                '"local_density_bonus_quote": ""}'
                            ),
                        }
                    }
                ]
            }

        monkeypatch.setattr("plotlot.retrieval.llm.call_llm", _fake_call)
        uplift = DensityUplift(base_units=10, state="CA", max_potential_units=10)
        await get_local_overrides(uplift, "San Diego", "RM-3-7", _results())
        # The fabricated quote isn't in the ordinance → rejected, base untouched.
        assert all(p.source != "local" for p in uplift.programs)
        assert uplift.max_potential_units == 10


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
