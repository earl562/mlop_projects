from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from plotlot.core.lookup_snapshot import DisplayState
from plotlot.pipeline.lookup_snapshot_eval import (
    LOOKUP_CORRECTNESS_SUITE,
    ExpectedLookupField,
    LookupSnapshotGoldenCase,
)
from plotlot.pipeline.lookup_snapshot_json import JsonScalar, JsonValue


class LookupGoldenFixtureInputs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    address: str = Field(min_length=1)


class LookupGoldenFixtureSample(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    inputs: LookupGoldenFixtureInputs
    expectations: dict[str, JsonValue] = Field(default_factory=dict)
    outputs: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("expectations", "outputs", mode="before")
    @classmethod
    def _null_maps_are_empty(cls, value: JsonValue | None) -> dict[str, JsonValue]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        raise ValueError("fixture expectations and outputs must be JSON objects")


@dataclass(frozen=True, slots=True)
class LookupSnapshotGoldenFixture:
    address: str
    source_path: str
    case: LookupSnapshotGoldenCase


def lookup_snapshot_golden_case_by_address(address: str) -> LookupSnapshotGoldenCase | None:
    fixture = _golden_fixtures_by_address().get(_normalize_address(address))
    if fixture is None:
        return None
    return fixture.case


def lookup_snapshot_golden_case_by_id(case_id: str) -> LookupSnapshotGoldenCase | None:
    fixture = _golden_fixtures_by_id().get(case_id)
    if fixture is None:
        return None
    return fixture.case


def load_lookup_snapshot_golden_fixtures(
    paths: tuple[Path, ...] | None = None,
) -> tuple[LookupSnapshotGoldenFixture, ...]:
    fixtures: list[LookupSnapshotGoldenFixture] = []
    for path in paths or default_lookup_snapshot_golden_paths():
        if not path.exists():
            continue
        payload = _load_json_list(path)
        for index, item in enumerate(payload):
            sample = LookupGoldenFixtureSample.model_validate(item)
            fixture = _fixture_from_sample(sample, path, index)
            if fixture is not None:
                fixtures.append(fixture)
    return tuple(_dedupe_by_case_id(fixtures))


def default_lookup_snapshot_golden_paths() -> tuple[Path, ...]:
    root = Path(__file__).resolve().parents[3]
    return (
        root / "data" / "golden" / "golden_data.json",
        root / "tests" / "eval" / "data" / "southfl_golden.json",
    )


@cache
def _golden_fixtures_by_address() -> dict[str, LookupSnapshotGoldenFixture]:
    return {
        _normalize_address(fixture.address): fixture
        for fixture in load_lookup_snapshot_golden_fixtures()
    }


@cache
def _golden_fixtures_by_id() -> dict[str, LookupSnapshotGoldenFixture]:
    return {fixture.case.case_id: fixture for fixture in load_lookup_snapshot_golden_fixtures()}


def _fixture_from_sample(
    sample: LookupGoldenFixtureSample,
    path: Path,
    index: int,
) -> LookupSnapshotGoldenFixture | None:
    expected_fields = _expected_fields(sample)
    if not expected_fields:
        return None

    county = _string_value(sample.expectations, sample.outputs, "county")
    municipality = _string_value(sample.expectations, sample.outputs, "municipality")
    tags = (LOOKUP_CORRECTNESS_SUITE, f"fixture:{path.stem}", f"row:{index}")
    case = LookupSnapshotGoldenCase(
        case_id=_case_id(path, sample.inputs.address),
        jurisdiction=_jurisdiction(municipality, county),
        expected_fields=tuple(expected_fields),
        required_calculations=_required_calculations(sample),
        tags=tags,
    )
    return LookupSnapshotGoldenFixture(
        address=sample.inputs.address,
        source_path=str(path),
        case=case,
    )


def _expected_fields(sample: LookupGoldenFixtureSample) -> list[ExpectedLookupField]:
    fields: list[ExpectedLookupField] = []
    _append_string_field(
        fields,
        "jurisdiction.municipality",
        _string_value(sample.expectations, sample.outputs, "municipality"),
    )
    _append_string_field(
        fields,
        "jurisdiction.county",
        _string_value(sample.expectations, sample.outputs, "county"),
    )
    _append_string_field(
        fields,
        "zoning.district",
        _string_value(sample.expectations, sample.outputs, "zoning_district"),
    )
    _append_scalar_field(
        fields,
        "calc.max_units",
        _number_value(sample.expectations, sample.outputs, "max_units"),
    )
    _append_string_field(
        fields,
        "calc.governing_constraint",
        _string_value(sample.expectations, sample.outputs, "governing_constraint"),
    )
    return fields


def _append_string_field(
    fields: list[ExpectedLookupField],
    key: str,
    value: str | None,
) -> None:
    if value is None:
        return
    _append_scalar_field(fields, key, value)


def _append_scalar_field(
    fields: list[ExpectedLookupField],
    key: str,
    value: JsonScalar,
) -> None:
    if value is None:
        return
    fields.append(
        ExpectedLookupField(
            key=key,
            value=value,
            display_state=DisplayState.VERIFIED,
        )
    )


def _required_calculations(sample: LookupGoldenFixtureSample) -> tuple[str, ...]:
    has_max_units = _number_value(sample.expectations, sample.outputs, "max_units") is not None
    has_constraint = (
        _string_value(sample.expectations, sample.outputs, "governing_constraint") is not None
    )
    if has_max_units or has_constraint:
        return ("max_units",)
    return ()


def _string_value(
    primary: dict[str, JsonValue],
    fallback: dict[str, JsonValue],
    key: str,
) -> str | None:
    value = primary.get(key, fallback.get(key))
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _number_value(
    primary: dict[str, JsonValue],
    fallback: dict[str, JsonValue],
    key: str,
) -> int | float | None:
    value = primary.get(key, fallback.get(key))
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _jurisdiction(municipality: str | None, county: str | None) -> str:
    if municipality and county:
        return f"{municipality}, {county} County"
    if municipality:
        return municipality
    if county:
        return f"{county} County"
    return "Unknown jurisdiction"


def _case_id(path: Path, address: str) -> str:
    normalized = _normalize_address(address)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:72]
    digest = hashlib.sha256(f"{path.name}:{normalized}".encode()).hexdigest()[:10]
    return f"{path.stem.replace('_', '-')}-{slug}-{digest}"


def _normalize_address(address: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", address.lower())
    return " ".join(cleaned.split())


def _dedupe_by_case_id(
    fixtures: list[LookupSnapshotGoldenFixture],
) -> list[LookupSnapshotGoldenFixture]:
    seen: set[str] = set()
    deduped: list[LookupSnapshotGoldenFixture] = []
    for fixture in fixtures:
        if fixture.case.case_id in seen:
            continue
        seen.add(fixture.case.case_id)
        deduped.append(fixture)
    return deduped


def _load_json_list(path: Path) -> list[JsonValue]:
    with path.open() as handle:
        payload = cast(JsonValue, json.load(handle))
    if isinstance(payload, list):
        return payload
    raise ValueError(f"lookup snapshot golden fixture must be a JSON list: {path}")
