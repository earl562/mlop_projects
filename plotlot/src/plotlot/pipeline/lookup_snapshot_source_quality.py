from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

UNACCEPTED_SOURCE_AUTHORITY_FLAG: Final = "unaccepted_source_authority"
MISSING_SOURCE_URL_FLAG: Final = "missing_source_url"
MISSING_RETRIEVED_AT_FLAG: Final = "missing_retrieved_at"
INVALID_RETRIEVED_AT_FLAG: Final = "invalid_retrieved_at"
MISSING_EFFECTIVE_DATE_FLAG: Final = "missing_effective_date"
INVALID_EFFECTIVE_DATE_FLAG: Final = "invalid_effective_date"
STALE_SOURCE_FLAG: Final = "stale_source"
MISSING_PARSER_VERSION_FLAG: Final = "missing_parser_version"
MISSING_SCHEMA_VERSION_FLAG: Final = "missing_schema_version"
DEFAULT_MAX_SOURCE_AGE_DAYS: Final = 730
ACCEPTED_SOURCE_AUTHORITIES: Final = frozenset(
    {
        "official_assessor",
        "official_gis",
        "official_zoning_ordinance",
        "municipal_web_page",
        "municipal_pdf",
        "municode_adopted_code_publisher",
    }
)


@dataclass(frozen=True, slots=True)
class SourceQualityScore:
    score: float
    flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceMetadataQualityInput:
    source_url: str
    source_authority: str
    retrieved_at: str
    effective_date: str
    parser_version: str
    schema_version: str
    confidence: float
    max_age_days: int = DEFAULT_MAX_SOURCE_AGE_DAYS


def score_source_metadata(source: SourceMetadataQualityInput) -> SourceQualityScore:
    flags = _source_quality_flags(source)
    return SourceQualityScore(
        score=_source_quality_score(source.confidence, flags),
        flags=flags,
    )


def _source_quality_flags(source: SourceMetadataQualityInput) -> tuple[str, ...]:
    flags: list[str] = []
    retrieved_on = _source_date(source.retrieved_at)
    effective_on = _source_date(source.effective_date)
    if not _authority_is_accepted(source.source_authority):
        flags.append(UNACCEPTED_SOURCE_AUTHORITY_FLAG)
    if not source.source_url:
        flags.append(MISSING_SOURCE_URL_FLAG)
    if not source.retrieved_at:
        flags.append(MISSING_RETRIEVED_AT_FLAG)
    if source.retrieved_at and retrieved_on is None:
        flags.append(INVALID_RETRIEVED_AT_FLAG)
    if not source.effective_date:
        flags.append(MISSING_EFFECTIVE_DATE_FLAG)
    if source.effective_date and effective_on is None:
        flags.append(INVALID_EFFECTIVE_DATE_FLAG)
    if _source_is_stale(source, retrieved_on, effective_on):
        flags.append(STALE_SOURCE_FLAG)
    if not source.parser_version:
        flags.append(MISSING_PARSER_VERSION_FLAG)
    if not source.schema_version:
        flags.append(MISSING_SCHEMA_VERSION_FLAG)
    return tuple(flags)


def _source_quality_score(confidence: float, quality_flags: tuple[str, ...]) -> float:
    if UNACCEPTED_SOURCE_AUTHORITY_FLAG in quality_flags:
        return 0.0
    if MISSING_SOURCE_URL_FLAG in quality_flags:
        return 0.0
    if MISSING_PARSER_VERSION_FLAG in quality_flags or MISSING_SCHEMA_VERSION_FLAG in quality_flags:
        return 0.0
    if MISSING_RETRIEVED_AT_FLAG in quality_flags or INVALID_RETRIEVED_AT_FLAG in quality_flags:
        return 0.0
    if (
        MISSING_EFFECTIVE_DATE_FLAG in quality_flags
        or INVALID_EFFECTIVE_DATE_FLAG in quality_flags
        or STALE_SOURCE_FLAG in quality_flags
    ):
        return min(confidence, 0.5)
    return confidence


def _authority_is_accepted(source_authority: str) -> bool:
    return source_authority in ACCEPTED_SOURCE_AUTHORITIES or source_authority.startswith(
        "codifier:"
    )


def _source_is_stale(
    source: SourceMetadataQualityInput,
    retrieved_on: date | None,
    effective_on: date | None,
) -> bool:
    if retrieved_on is None or effective_on is None:
        return False
    return (retrieved_on - effective_on).days > source.max_age_days


def _source_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None
