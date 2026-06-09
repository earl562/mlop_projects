"""Tests for Memory Layer (AC-3.1)."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryEntry:
    key: str
    value: Any
    jurisdiction: str = ""
    correction_count: int = 0


class MemoryLayer:
    def __init__(self):
        self.jurisdiction_memory = {}
        self.corrections = {}
        self.owner_memory = {}

    def store_jurisdiction_fact(self, jurisdiction: str, key: str, value: Any):
        if jurisdiction not in self.jurisdiction_memory:
            self.jurisdiction_memory[jurisdiction] = {}
        self.jurisdiction_memory[jurisdiction][key] = value

    def get_jurisdiction_fact(self, jurisdiction: str, key: str) -> Any:
        return self.jurisdiction_memory.get(jurisdiction, {}).get(key)

    def apply_correction(self, jurisdiction: str, claim_key: str, corrected_value: Any, reason: str = ""):
        key = f"{jurisdiction}:{claim_key}"
        self.corrections[key] = {
            "corrected_value": corrected_value,
            "reason": reason,
            "applied_at": "now",
        }

    def get_correction(self, jurisdiction: str, claim_key: str) -> dict | None:
        return self.corrections.get(f"{jurisdiction}:{claim_key}")


class TestMemoryLayer:
    def test_jurisdiction_fact_persists(self):
        mem = MemoryLayer()
        mem.store_jurisdiction_fact("Miami-Dade", "max_units_residential", 8)
        assert mem.get_jurisdiction_fact("Miami-Dade", "max_units_residential") == 8

    def test_correction_applied(self):
        mem = MemoryLayer()
        mem.apply_correction("Miami-Dade", "max_units_residential", 12, "Agent used wrong lot size")
        result = mem.get_correction("Miami-Dade", "max_units_residential")
        assert result["corrected_value"] == 12
        assert "wrong lot size" in result["reason"]

    def test_correction_not_found_returns_none(self):
        mem = MemoryLayer()
        assert mem.get_correction("Broward", "max_units") is None
