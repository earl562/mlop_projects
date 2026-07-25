from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from typing import Final

_SOLD_PRICE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:sold\s+for|sale\s+price|sold price|closed at)\s*\$?\s*([0-9][0-9,]{2,}(?:\.\d{2})?)",
    re.IGNORECASE,
)
_LOT_SIZE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"([0-9][0-9,]{2,}(?:\.\d+)?)\s*(?:sq\s*\.?\s*ft|sqft|square feet)",
    re.IGNORECASE,
)
_LOT_ACREAGE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"([0-9]+(?:\.\d+)?)\s*(?:acres?|ac\b)",
    re.IGNORECASE,
)
_LOT_DIMENSION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"([0-9]{2,4}(?:\.\d+)?)\s*(?:x|by)\s*([0-9]{2,4}(?:\.\d+)?)",
    re.IGNORECASE,
)
_MONTH_NAME_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?"
    r")\s+([0-9]{1,2}),\s*([0-9]{4})\b",
    re.IGNORECASE,
)
_ISO_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b([0-9]{4})-([0-9]{2})-([0-9]{2})\b")
_SLASH_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b([0-9]{1,2})/([0-9]{1,2})/([0-9]{4})\b")
_FL_MUNICIPALITY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r",\s*([A-Za-z][A-Za-z .'-]+?),\s*FL(?:\s+[0-9]{5})?\b",
    re.IGNORECASE,
)
_FL_ZIP_CODE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\bFL\s+([0-9]{5})(?:-[0-9]{4})?\b", re.IGNORECASE)
_ZIP_CODE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b([0-9]{5})(?:-[0-9]{4})?\b")
_SQFT_PER_ACRE: Final[float] = 43_560.0
_MAX_LOT_SIZE_VARIANCE_RATIO: Final[float] = 0.35


def extract_sold_price(raw_text: str) -> float | None:
    match = _SOLD_PRICE_PATTERN.search(raw_text)
    if match is None:
        return None
    return _normalized_number(match.group(1))


def extract_sale_date(raw_text: str, *, fallback_values: tuple[object, ...]) -> str | None:
    for pattern in (_ISO_DATE_PATTERN, _SLASH_DATE_PATTERN, _MONTH_NAME_DATE_PATTERN):
        match = pattern.search(raw_text)
        if match is None:
            continue
        parsed = _parse_date_match(match)
        if parsed is not None:
            return parsed.isoformat()
    for value in fallback_values:
        parsed = _parse_fallback_date(value)
        if parsed is not None:
            return parsed.isoformat()
    return None


def extract_lot_size_sqft(raw_text: str) -> float | None:
    sqft_match = _largest_sqft_match(raw_text)
    if sqft_match is not None:
        return sqft_match
    acreage_match = _largest_acreage_match(raw_text)
    if acreage_match is not None:
        return acreage_match
    return _largest_dimension_area(raw_text)


def is_subject_lot_size_similar(
    *,
    subject_lot_area_sf: float,
    comparable_lot_size_sqft: float,
) -> bool:
    variance_ratio = lot_size_variance_ratio(
        subject_lot_area_sf=subject_lot_area_sf,
        comparable_lot_size_sqft=comparable_lot_size_sqft,
    )
    if variance_ratio is None:
        return False
    return variance_ratio <= _MAX_LOT_SIZE_VARIANCE_RATIO


def lot_size_variance_ratio(
    *,
    subject_lot_area_sf: float,
    comparable_lot_size_sqft: float,
) -> float | None:
    if subject_lot_area_sf <= 0 or comparable_lot_size_sqft <= 0:
        return None
    return abs(comparable_lot_size_sqft - subject_lot_area_sf) / subject_lot_area_sf


def contextual_fit_score(
    *,
    subject_lot_area_sf: float,
    comparable_lot_size_sqft: float,
) -> float:
    variance_ratio = lot_size_variance_ratio(
        subject_lot_area_sf=subject_lot_area_sf,
        comparable_lot_size_sqft=comparable_lot_size_sqft,
    )
    if variance_ratio is None:
        return 0.0
    return round(max(0.0, 1.0 - variance_ratio), 3)


def is_sale_date_within_window(
    *,
    sale_date: str,
    search_window_months: object,
    reference_date: date | None,
) -> bool:
    if reference_date is None:
        return True
    if not isinstance(search_window_months, int) or search_window_months <= 0:
        return True
    parsed_sale_date = parse_iso_date(sale_date)
    if parsed_sale_date is None:
        return False
    cutoff = _subtract_months(reference_date, search_window_months)
    return parsed_sale_date >= cutoff


def parse_iso_date(value: str | None) -> date | None:
    if value is None:
        return None
    return _parse_fallback_date(value)


def extract_municipality_hint(*values: object) -> str | None:
    for value in values:
        if not isinstance(value, str):
            continue
        match = _FL_MUNICIPALITY_PATTERN.search(value)
        if match is None:
            continue
        municipality = match.group(1).strip()
        if municipality:
            return municipality
    return None


def extract_zip_code(*values: object) -> str | None:
    for value in values:
        if not isinstance(value, str):
            continue
        fl_match = _FL_ZIP_CODE_PATTERN.search(value)
        if fl_match is not None:
            zip_code = fl_match.group(1).strip()
            if zip_code:
                return zip_code
        all_matches = _ZIP_CODE_PATTERN.findall(value)
        if all_matches:
            zip_code = all_matches[-1].strip()
            if zip_code:
                return zip_code
    return None


def zip_matches_subject(*, subject_zip_code: str | None, candidate_zip_code: str | None) -> bool | None:
    normalized_subject = (subject_zip_code or "").strip()
    if not normalized_subject:
        return None
    normalized_candidate = (candidate_zip_code or "").strip()
    if not normalized_candidate:
        return None
    return normalized_candidate == normalized_subject


def listing_parse_confidence(
    *,
    sale_price: float | None,
    sale_date: str | None,
    lot_size_sqft: float | None,
    municipality: str | None,
    zip_code: str | None,
) -> float:
    score = 0.0
    if isinstance(sale_price, float) and sale_price > 0:
        score += 0.3
    if isinstance(sale_date, str) and sale_date.strip():
        score += 0.25
    if isinstance(lot_size_sqft, float) and lot_size_sqft > 0:
        score += 0.25
    if municipality is not None and municipality.strip():
        score += 0.1
    if zip_code is not None and zip_code.strip():
        score += 0.1
    return round(score, 3)


def municipality_matches_subject(*, subject_municipality: str, candidate_municipality: str | None) -> bool:
    normalized_subject = subject_municipality.strip().casefold()
    if not normalized_subject:
        return True
    if candidate_municipality is None:
        return True
    return candidate_municipality.strip().casefold() == normalized_subject


def _largest_sqft_match(raw_text: str) -> float | None:
    matches = list(_LOT_SIZE_PATTERN.finditer(raw_text))
    if not matches:
        return None
    return max((_normalized_number(match.group(1)) for match in matches), default=None)


def _largest_acreage_match(raw_text: str) -> float | None:
    matches = list(_LOT_ACREAGE_PATTERN.finditer(raw_text))
    if not matches:
        return None
    acres = max((_normalized_number(match.group(1)) for match in matches), default=None)
    if acres is None or acres <= 0:
        return None
    return round(acres * _SQFT_PER_ACRE, 2)


def _largest_dimension_area(raw_text: str) -> float | None:
    areas: list[float] = []
    for match in _LOT_DIMENSION_PATTERN.finditer(raw_text):
        width = _normalized_number(match.group(1))
        depth = _normalized_number(match.group(2))
        if width is None or depth is None or width <= 0 or depth <= 0:
            continue
        areas.append(round(width * depth, 2))
    if not areas:
        return None
    return max(areas)


def _normalized_number(raw_value: str) -> float | None:
    normalized = raw_value.replace(",", "").strip()
    try:
        return float(normalized)
    except ValueError:
        return None


def _parse_date_match(match: re.Match[str]) -> date | None:
    groups = match.groups()
    try:
        if match.re is _ISO_DATE_PATTERN:
            year, month, day = (int(group) for group in groups)
            return date(year, month, day)
        if match.re is _SLASH_DATE_PATTERN:
            month, day, year = (int(group) for group in groups)
            return date(year, month, day)
        if match.re is _MONTH_NAME_DATE_PATTERN:
            month_name, day_text, year_text = groups
            for format_string in ("%B %d %Y", "%b %d %Y"):
                try:
                    return datetime.strptime(
                        f"{month_name} {day_text} {year_text}",
                        format_string,
                    ).date()
                except ValueError:
                    continue
            return None
    except ValueError:
        return None
    return None


def _parse_fallback_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    for parser in (
        lambda raw: datetime.strptime(raw, "%Y-%m-%d").date(),
        lambda raw: datetime.strptime(raw, "%m/%d/%Y").date(),
    ):
        try:
            return parser(normalized)
        except ValueError:
            continue
    month_match = _MONTH_NAME_DATE_PATTERN.fullmatch(normalized)
    if month_match is None:
        return None
    return _parse_date_match(month_match)


def _subtract_months(reference_date: date, months: int) -> date:
    zero_based_month = reference_date.month - 1 - months
    year = reference_date.year + zero_based_month // 12
    month = zero_based_month % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(reference_date.day, last_day))
