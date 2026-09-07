from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from typing import assert_never

from plotlot.comps.models import DatePrecision


@dataclass(frozen=True, slots=True)
class EvidenceDate:
    start: date
    end: date


@dataclass(frozen=True, slots=True)
class DateAssessment:
    value: EvidenceDate | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class DateWindow:
    as_of: date
    months: int


def _subtract_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def parse_evidence_date(value: str, precision: DatePrecision) -> DateAssessment:
    if not value:
        return DateAssessment(None, "missing_sale_date")
    match precision:
        case "day":
            try:
                parsed_day = date.fromisoformat(value)
            except ValueError:
                return DateAssessment(None, "invalid_sale_date")
            if len(value) != 10:
                return DateAssessment(None, "invalid_sale_date")
            return DateAssessment(EvidenceDate(parsed_day, parsed_day), None)
        case "month":
            if len(value) != 7:
                return DateAssessment(None, "invalid_sale_date")
            try:
                year, month = (int(part) for part in value.split("-"))
                start = date(year, month, 1)
            except (TypeError, ValueError):
                return DateAssessment(None, "invalid_sale_date")
            end = date(year, month, monthrange(year, month)[1])
            return DateAssessment(EvidenceDate(start, end), None)
        case "unknown":
            return DateAssessment(None, "unknown_date_precision")
        case unreachable:
            assert_never(unreachable)


def assess_sale_date(value: str, precision: DatePrecision, window: DateWindow) -> DateAssessment:
    parsed = parse_evidence_date(value, precision)
    if parsed.value is None:
        return parsed
    if parsed.value.start > window.as_of:
        return DateAssessment(parsed.value, "future_sale_date")
    if parsed.value.end > window.as_of:
        return DateAssessment(parsed.value, "date_range_straddles_as_of")
    cutoff = _subtract_months(window.as_of, window.months)
    if parsed.value.end < cutoff:
        return DateAssessment(parsed.value, "outside_date_window")
    if parsed.value.start < cutoff <= parsed.value.end:
        return DateAssessment(parsed.value, "date_range_straddles_cutoff")
    return parsed


def evidence_date_sort_key(value: str, precision: DatePrecision) -> int:
    parsed = parse_evidence_date(value, precision)
    if parsed.value is None:
        return date.min.toordinal()
    return parsed.value.end.toordinal()
