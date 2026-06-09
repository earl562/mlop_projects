from datetime import datetime
from typing import Any


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
            "applied_at": datetime.utcnow().isoformat(),
        }

    def get_correction(self, jurisdiction: str, claim_key: str) -> dict | None:
        return self.corrections.get(f"{jurisdiction}:{claim_key}")
