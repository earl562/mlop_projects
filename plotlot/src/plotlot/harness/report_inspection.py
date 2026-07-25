from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from plotlot.harness.contracts import JsonObject, Report

UNDERWRITING_SECTION_ID: Final = "underwriting_summary"
COMP_SUPPORT_KEYS: Final[tuple[str, ...]] = (
    "status",
    "reason",
    "comping_underwriting_status",
    "comping_underwriting_blocker",
    "land_support_source",
    "land_support_fit_score",
    "land_support_quality_score",
    "land_support_market_scope",
    "land_support_sale_date",
    "land_support_recency_tier",
    "land_support_parse_confidence",
    "land_micro_market_confidence",
    "exit_support_fit_score",
    "exit_support_quality_score",
    "exit_support_distance_miles",
    "exit_support_market_scope",
    "exit_support_sale_date",
    "exit_support_recency_tier",
    "exit_micro_market_confidence",
    "combined_support_tier",
)
ZONING_SUPPORT_KEYS: Final[tuple[str, ...]] = (
    "status",
    "reason",
    "ordinance_rules_resolved",
    "ordinance_source",
    "requires_official_verification",
    "authority_source_type",
    "authority_resolution",
    "authority_confidence",
    "authority_jurisdiction",
    "authority_is_live",
    "authority_is_official",
    "gis_applicability",
)


def latest_report(reports: Sequence[Report]) -> Report | None:
    if not reports:
        return None
    return max(reports, key=lambda report: (report.generated_at, str(report.report_id)))


def underwriting_section(report: Report) -> JsonObject:
    for section in report.sections:
        if not isinstance(section, dict):
            continue
        if section.get("section_id") == UNDERWRITING_SECTION_ID:
            return section
    return {}


def underwriting_mode(report: Report) -> JsonObject:
    section = underwriting_section(report)
    mode = section.get("underwriting_mode")
    if isinstance(mode, dict):
        return mode
    return {}


def comp_support_summary(report: Report) -> JsonObject:
    section = underwriting_section(report)
    summary = section.get("comp_support_summary")
    if isinstance(summary, dict):
        return summary
    return {}


def zoning_support_summary(report: Report) -> JsonObject:
    section = underwriting_section(report)
    summary = section.get("zoning_support_summary")
    if isinstance(summary, dict):
        return summary
    return {}


def comp_support_snapshot(report: Report | None) -> JsonObject:
    if report is None:
        return {}
    summary = comp_support_summary(report)
    if not summary:
        return {}
    snapshot: JsonObject = {
        "report_id": str(report.report_id),
        "report_status": report.status.value,
        "report_source_mode": report.source_mode.value,
    }
    for key in COMP_SUPPORT_KEYS:
        value = summary.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        snapshot[key] = value
    return snapshot


def zoning_support_snapshot(report: Report | None) -> JsonObject:
    if report is None:
        return {}
    summary = zoning_support_summary(report)
    if not summary:
        return {}
    snapshot: JsonObject = {
        "report_id": str(report.report_id),
        "report_status": report.status.value,
        "report_source_mode": report.source_mode.value,
    }
    for key in ZONING_SUPPORT_KEYS:
        value = summary.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        snapshot[key] = value
    return snapshot
