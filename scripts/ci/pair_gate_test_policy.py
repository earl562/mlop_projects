from __future__ import annotations

from pathlib import Path

from pair_gate_types import JsonObject, JsonValue, gate_error

LIVE_EVAL_PATHS = {
    "tests/eval/test_eval_live.py",
    "tests/eval/test_ingestion_golden_queries.py",
}
REQUIRED_PREFIXES = (
    "tests/architecture/",
    "tests/contracts/",
    "tests/eval/",
    "tests/security/",
    "tests/unit/",
)


def classify_test_path(path: str) -> JsonObject:
    if path in LIVE_EVAL_PATHS:
        return {
            "classification": "deferred-authorized-live",
            "ownerTodos": [27, 29, 32, 33],
            "releaseStatus": "blocked-non-release",
        }
    if path.startswith("tests/integration/"):
        return {
            "classification": "deferred-integration",
            "ownerTodos": [8, 9, 10, 15, 16, 17, 18, 27, 32, 33],
            "releaseStatus": "blocked-non-release",
        }
    if path.startswith(REQUIRED_PREFIXES):
        return {
            "classification": "required-deterministic",
            "ownerTodos": [12],
            "releaseStatus": "required",
        }
    raise gate_error("PAIR_E_MANIFEST", f"unclassified PlotLot test path: {path}")


def source_inventory(plotlot: Path) -> list[JsonValue]:
    tests = plotlot / "plotlot/tests"
    inventory: list[JsonValue] = []
    for source in sorted(tests.glob("**/test_*.py")):
        relative = source.relative_to(plotlot / "plotlot").as_posix()
        entry = {"path": relative, **classify_test_path(relative)}
        inventory.append(entry)
    if not inventory:
        raise gate_error("PAIR_E_MANIFEST", "PlotLot test source inventory is empty")
    return inventory
