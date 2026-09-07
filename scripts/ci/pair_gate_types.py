from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class GateError(RuntimeError):
    code: str
    exit_code: int
    detail: str

    def __str__(self) -> str:
        return self.detail


ERROR_CODES = {
    "PAIR_E_MANIFEST": 10,
    "PAIR_E_SIGNATURE": 11,
    "PAIR_E_ARTIFACT_ROOT": 12,
    "PAIR_E_SHA": 20,
    "PAIR_E_DIRTY_DEPENDENCY": 21,
    "PAIR_E_DIRTY_TREE": 22,
    "PAIR_E_CONTRACT_DRIFT": 30,
    "PAIR_E_MIGRATION_DRIFT": 31,
    "PAIR_E_CLIENT_DRIFT": 32,
    "PAIR_E_COMMAND": 40,
    "PAIR_E_SKIPPED_TEST": 41,
    "PAIR_E_ZERO_TEST": 42,
    "PAIR_E_BROWSER_ARTIFACT": 43,
    "PAIR_E_FIXTURE_LIVE": 50,
    "PAIR_E_SECRET": 51,
    "PAIR_E_PRIVACY": 52,
    "PAIR_E_SBOM_CRITICAL": 53,
    "PAIR_E_ROLLBACK": 54,
    "PAIR_E_PROVENANCE": 55,
    "PAIR_E_STALE_EVIDENCE": 56,
    "PAIR_E_SBOM_KEV": 57,
    "PAIR_E_SBOM_DIRECT_FIXABLE": 58,
    "PAIR_E_SBOM_ENRICHMENT": 59,
}


def gate_error(code: str, detail: str) -> GateError:
    return GateError(code=code, exit_code=ERROR_CODES[code], detail=detail)


def require_object(value: JsonValue, label: str) -> JsonObject:
    if not isinstance(value, dict):
        raise gate_error("PAIR_E_MANIFEST", f"{label} must be an object")
    return value


def require_list(value: JsonValue, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise gate_error("PAIR_E_MANIFEST", f"{label} must be a list")
    return value


def require_string(value: JsonValue, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise gate_error("PAIR_E_MANIFEST", f"{label} must be a non-empty string")
    return value


def require_int(value: JsonValue, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise gate_error("PAIR_E_MANIFEST", f"{label} must be an integer")
    return value


def require_path(value: JsonValue, label: str) -> Path:
    return Path(require_string(value, label)).resolve()
