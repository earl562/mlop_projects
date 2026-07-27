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
    "tests/storage/",
    "tests/unit/",
)
BYRIGHT_DEFERRED_TESTS: tuple[tuple[str, list[int]], ...] = (
    (
        "Broward live parcel adapter > reaches the official Broward ArcGIS parcel layer when enabled",
        [17, 32],
    ),
    (
        "City of Charlotte zoning adapter > reaches the official City of Charlotte zoning layer when enabled",
        [15],
    ),
    (
        "FEMA NFHL flood-zone adapter > reaches the official FEMA NFHL Flood Hazard Zones layer when enabled",
        [15],
    ),
    (
        "Gaston live parcel adapter > reaches the official Gaston ArcGIS parcel layer when enabled",
        [15],
    ),
    (
        "Mecklenburg live parcel adapter > reaches the official Mecklenburg POLARIS parcel endpoint when enabled",
        [15],
    ),
    (
        "Miami-Dade live parcel adapter > reaches the official Miami-Dade ArcGIS parcel layer when enabled",
        [16, 27],
    ),
    (
        "Palm Beach live parcel adapter > reaches the official Palm Beach ArcGIS parcel layer when enabled",
        [18, 33],
    ),
    (
        "workflow persistence > persists to Docker Postgres when explicitly enabled",
        [8, 10, 11],
    ),
    (
        "San Diego live parcel adapter > reaches the official SANDAG parcel layer when enabled",
        [15],
    ),
    (
        "source probing > probes registered official source paths when live source smoke is explicitly enabled",
        [15, 27, 32, 33],
    ),
)
BYRIGHT_SEPARATELY_REQUIRED_TESTS: tuple[tuple[str, str], ...] = (
    (
        "tenant persistence > leaves no partial row after a real PostgreSQL failure",
        "byright-persistence",
    ),
)


def byright_deferred_tests() -> list[JsonValue]:
    result: list[JsonValue] = []
    for title, owner_todos in BYRIGHT_DEFERRED_TESTS:
        owner_values: list[JsonValue] = [value for value in owner_todos]
        result.append(
            {
                "title": title,
                "ownerTodos": owner_values,
                "releaseStatus": "blocked-non-release",
            }
        )
    return result


def byright_separately_required_tests() -> list[JsonValue]:
    return [
        {"title": title, "lane": lane, "releaseStatus": "required"}
        for title, lane in BYRIGHT_SEPARATELY_REQUIRED_TESTS
    ]


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
