"""Privacy-safe models and helpers for Drive-derived property evaluation cases."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


_EMAIL_PATTERN = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)"
    r"\d{3}[\s.-]?\d{4}(?!\d)"
)
_KEY_TOKEN_PATTERN = re.compile(r"[^a-z0-9]+")
_BANNED_KEY_MARKERS = (
    "email",
    "phone",
    "telephone",
    "mobile",
    "contact",
    "mailing",
    "owner_name",
    "seller_name",
    "prospect",
    "lead_name",
    "notes",
    "comments",
    "outreach",
)
_SAFE_IDENTIFIER_KEYS = {
    "case_id",
    "parcel_id",
    "source_file_id",
}

_ADDRESS_KEYS = (
    "input_property_address",
    "property_address",
    "street_address",
    "address",
)
_CITY_KEYS = (
    "input_property_city",
    "property_city",
    "city",
)
_STATE_KEYS = (
    "input_property_state",
    "property_state",
    "state",
)
_COUNTY_KEYS = (
    "input_property_county",
    "property_county",
    "county",
)
_PARCEL_KEYS = (
    "parcel_id",
    "parcel",
    "folio",
    "apn",
)
_ASKING_PRICE_KEYS = (
    "asking_price",
    "list_price",
    "purchase_price",
    "price",
)
_LOT_SQFT_KEYS = (
    "lot_size_sqft",
    "lot_sqft",
    "lot_size",
)
_LOT_ACRES_KEYS = (
    "lot_size_acres",
    "lot_acres",
    "acres",
)
_ZONING_KEYS = (
    "zoning_hint",
    "zoning_code",
    "zoning",
)


class LeadPrivacyError(ValueError):
    """Raised when a supposedly sanitized fixture contains contact data."""


class LeadEvaluationCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1, max_length=80)
    address: str = Field(min_length=1, max_length=300)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, min_length=2, max_length=2)
    county: str | None = Field(default=None, max_length=120)
    parcel_id: str | None = Field(default=None, max_length=160)
    asking_price: float | None = Field(default=None, ge=0)
    lot_size_sqft: float | None = Field(default=None, gt=0)
    zoning_hint: str | None = Field(default=None, max_length=120)
    workflow: str = Field(default="site_feasibility", min_length=1, max_length=80)
    source_file_id: str = Field(min_length=1, max_length=160)
    source_row: int = Field(ge=1)

    @field_validator(
        "address",
        "city",
        "county",
        "parcel_id",
        "zoning_hint",
        "workflow",
        "source_file_id",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("state", mode="before")
    @classmethod
    def _normalize_state(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class LeadFixtureManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str
    generated_at: str
    case_count: int = Field(ge=0)
    markets: tuple[str, ...]
    source_files: tuple[dict[str, Any], ...]
    privacy_exclusions: tuple[str, ...]


def _normalize_key(value: str) -> str:
    return _KEY_TOKEN_PATTERN.sub("_", value.casefold()).strip("_")


def _normalized_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {_normalize_key(str(key)): value for key, value in row.items()}


def _first(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    for alias in aliases:
        value = row.get(alias)
        if value is not None and value != "":
            return value
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned or cleaned in {"-", ".", "-."}:
        return None
    try:
        parsed = float(cleaned)
    except ValueError:
        return None
    return -parsed if negative and parsed > 0 else parsed


def _identity_part(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def stable_case_id(
    address: str,
    city: str | None,
    state: str | None,
) -> str:
    identity = "|".join(
        (
            _identity_part(address),
            _identity_part(city),
            _identity_part(state),
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"lead_{digest}"


def sanitize_lead_row(
    row: Mapping[str, Any],
    *,
    source_file_id: str,
    source_row: int,
    workflow: str = "site_feasibility",
) -> LeadEvaluationCase | None:
    """Map an arbitrary sheet row to an explicit property-only allowlist."""

    normalized = _normalized_row(row)
    address = _text(_first(normalized, _ADDRESS_KEYS))
    if not address:
        return None

    city = _text(_first(normalized, _CITY_KEYS))
    state = _text(_first(normalized, _STATE_KEYS))
    county = _text(_first(normalized, _COUNTY_KEYS))
    parcel_id = _text(_first(normalized, _PARCEL_KEYS))
    asking_price = _number(_first(normalized, _ASKING_PRICE_KEYS))
    lot_size_sqft = _number(_first(normalized, _LOT_SQFT_KEYS))
    if lot_size_sqft is None:
        lot_acres = _number(_first(normalized, _LOT_ACRES_KEYS))
        if lot_acres is not None and lot_acres > 0:
            lot_size_sqft = lot_acres * 43_560
    zoning_hint = _text(_first(normalized, _ZONING_KEYS))

    return LeadEvaluationCase(
        case_id=stable_case_id(address, city, state),
        address=address,
        city=city,
        state=state,
        county=county,
        parcel_id=parcel_id,
        asking_price=asking_price,
        lot_size_sqft=lot_size_sqft,
        zoning_hint=zoning_hint,
        workflow=workflow,
        source_file_id=source_file_id,
        source_row=source_row,
    )


def _assert_value_is_private_data_free(value: Any, *, key: str) -> None:
    if isinstance(value, Mapping):
        for child_key, child_value in value.items():
            normalized_key = _normalize_key(str(child_key))
            if any(marker in normalized_key for marker in _BANNED_KEY_MARKERS):
                raise LeadPrivacyError(
                    f"forbidden contact or outreach field: {normalized_key}"
                )
            _assert_value_is_private_data_free(child_value, key=normalized_key)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_value_is_private_data_free(item, key=key)
        return
    if not isinstance(value, str) or key in _SAFE_IDENTIFIER_KEYS:
        return
    if _EMAIL_PATTERN.search(value):
        raise LeadPrivacyError(f"email-like value found in {key}")
    if _PHONE_PATTERN.search(value):
        raise LeadPrivacyError(f"phone-like value found in {key}")


def assert_fixture_is_sanitized(cases: Sequence[Mapping[str, Any]]) -> None:
    """Fail closed when a fixture contains contact data or outreach notes."""

    for case in cases:
        _assert_value_is_private_data_free(case, key="case")


def load_lead_fixture(path: Path) -> tuple[LeadEvaluationCase, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("lead fixture must be a JSON array")
    assert_fixture_is_sanitized(payload)
    return tuple(LeadEvaluationCase.model_validate(item) for item in payload)


__all__ = [
    "LeadEvaluationCase",
    "LeadFixtureManifest",
    "LeadPrivacyError",
    "assert_fixture_is_sanitized",
    "load_lead_fixture",
    "sanitize_lead_row",
    "stable_case_id",
]
