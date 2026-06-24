from __future__ import annotations

import hashlib
from collections.abc import Iterable

from plotlot.core.lookup_snapshot import (
    CalculationTrace,
    EvidenceId,
    LookupSnapshot,
    LookupSnapshotId,
    RunId,
    SiteId,
)
from plotlot.core.types import ZoningReport
from plotlot.pipeline.lookup_snapshot_fields import (
    calculation_field,
    parcel_field,
    zoning_field,
)
from plotlot.pipeline.lookup_snapshot_source_metadata import build_source_metadata
from plotlot.pipeline.lookup_snapshot_zoning_fields import zoning_district_field

CALCULATOR_VERSION = "2026.06.21"


def build_lookup_snapshot(report: ZoningReport) -> LookupSnapshot:
    parcel_evidence_ids = _parcel_evidence_ids(report)
    ordinance_evidence_ids = _ordinance_evidence_ids(report)
    calculation_evidence_ids = _calculation_evidence_ids(
        parcel_evidence_ids,
        ordinance_evidence_ids,
        has_calculation=report.density_analysis is not None,
    )
    base = _stable_parts(report)

    fields = (
        parcel_field("parcel.apn", "APN", _parcel_value(report, "folio"), "", parcel_evidence_ids),
        parcel_field(
            "parcel.address",
            "Parcel address",
            _parcel_value(report, "address"),
            "",
            parcel_evidence_ids,
        ),
        parcel_field(
            "parcel.lot_area_sqft",
            "Lot area",
            _positive_float(_parcel_value(report, "lot_size_sqft")),
            "sqft",
            parcel_evidence_ids,
        ),
        parcel_field(
            "jurisdiction.municipality",
            "Municipality",
            report.municipality,
            "",
            parcel_evidence_ids,
        ),
        parcel_field("jurisdiction.county", "County", report.county, "", parcel_evidence_ids),
        zoning_district_field(report, parcel_evidence_ids, ordinance_evidence_ids),
        zoning_field(
            "zoning.description",
            "Zoning description",
            report.zoning_description,
            "",
            ordinance_evidence_ids,
        ),
        zoning_field(
            "uses.allowed", "Allowed uses", _joined(report.allowed_uses), "", ordinance_evidence_ids
        ),
        zoning_field(
            "standards.setbacks.front",
            "Front setback",
            report.setbacks.front,
            "ft",
            ordinance_evidence_ids,
        ),
        zoning_field(
            "standards.setbacks.side",
            "Side setback",
            report.setbacks.side,
            "ft",
            ordinance_evidence_ids,
        ),
        zoning_field(
            "standards.setbacks.rear",
            "Rear setback",
            report.setbacks.rear,
            "ft",
            ordinance_evidence_ids,
        ),
        zoning_field(
            "standards.height", "Maximum height", report.max_height, "ft", ordinance_evidence_ids
        ),
        zoning_field(
            "standards.density", "Maximum density", report.max_density, "", ordinance_evidence_ids
        ),
        zoning_field(
            "standards.lot_coverage",
            "Lot coverage",
            report.lot_coverage,
            "",
            ordinance_evidence_ids,
        ),
        zoning_field(
            "standards.parking", "Parking", report.parking_requirements, "", ordinance_evidence_ids
        ),
        calculation_field(
            "calc.max_units", "Maximum units", _max_units(report), "units", calculation_evidence_ids
        ),
        calculation_field(
            "calc.max_gla", "Maximum GLA", _max_gla(report), "sqft", calculation_evidence_ids
        ),
        calculation_field(
            "calc.governing_constraint",
            "Governing constraint",
            _governing_constraint(report),
            "",
            calculation_evidence_ids,
        ),
        calculation_field(
            "confidence", "Confidence", report.confidence, "", ordinance_evidence_ids
        ),
    )

    return LookupSnapshot(
        lookup_snapshot_id=LookupSnapshotId(f"ls_{_digest('lookup', base)}"),
        site_id=SiteId(f"site_{_digest('site', base)}"),
        run_id=RunId(f"run_{_digest('run', base, report.summary)}"),
        fields=fields,
        calculations=_calculation_traces(report, calculation_evidence_ids),
        warnings=tuple(report.validation_warnings),
        source_metadata=build_source_metadata(report, ordinance_evidence_ids),
    )


def _calculation_traces(
    report: ZoningReport,
    evidence_ids: tuple[EvidenceId, ...],
) -> tuple[CalculationTrace, ...]:
    if report.density_analysis is None:
        return ()

    if report.density_analysis.max_gla_sqft is not None:
        calculator_name = "max_gla"
        formula = "lot_area_sqft * far or buildable_area_sqft by coverage"
        output_label = f"max_gla_sqft={report.density_analysis.max_gla_sqft:g}"
    else:
        calculator_name = "max_units"
        formula = "lot_area_sqft constrained by density, lot area, parking, and dimensions"
        output_label = f"max_units={report.density_analysis.max_units}"

    return (
        CalculationTrace(
            calculator_name=calculator_name,
            calculator_version=CALCULATOR_VERSION,
            formula=formula,
            input_evidence_ids=evidence_ids,
            output_label=output_label,
            warnings=tuple(report.density_analysis.notes),
        ),
    )


def _parcel_evidence_ids(report: ZoningReport) -> tuple[EvidenceId, ...]:
    if report.property_record is None:
        return ()
    record = report.property_record
    return (EvidenceId(f"ev_parcel_{_digest(record.folio, record.address, record.county)}"),)


def _ordinance_evidence_ids(report: ZoningReport) -> tuple[EvidenceId, ...]:
    ids: list[EvidenceId] = []
    for ref in report.source_refs:
        ids.append(
            EvidenceId(
                f"ev_ordinance_{_digest(ref.section, ref.section_title, ref.chunk_text_preview)}"
            )
        )
    return tuple(ids)


def _calculation_evidence_ids(
    parcel_evidence_ids: tuple[EvidenceId, ...],
    ordinance_evidence_ids: tuple[EvidenceId, ...],
    *,
    has_calculation: bool,
) -> tuple[EvidenceId, ...]:
    if not has_calculation:
        return ()
    if not parcel_evidence_ids or not ordinance_evidence_ids:
        return ()
    return _unique_evidence((*parcel_evidence_ids, *ordinance_evidence_ids))


def _unique_evidence(evidence_ids: Iterable[EvidenceId]) -> tuple[EvidenceId, ...]:
    seen: set[str] = set()
    unique: list[EvidenceId] = []
    for evidence_id in evidence_ids:
        value = str(evidence_id)
        if value in seen:
            continue
        seen.add(value)
        unique.append(evidence_id)
    return tuple(unique)


def _stable_parts(report: ZoningReport) -> str:
    return "|".join(
        (
            report.formatted_address,
            report.address,
            report.county,
            report.municipality,
            report.zoning_district,
            _parcel_value(report, "folio") or "",
        )
    )


def _digest(*parts: str) -> str:
    payload = "|".join(str(part).strip().lower() for part in parts if str(part).strip())
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _parcel_value(report: ZoningReport, name: str) -> str:
    if report.property_record is None:
        return ""
    value = getattr(report.property_record, name)
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return f"{value:g}"
    return ""


def _positive_float(value: str) -> float | None:
    try:
        parsed = float(value)
    except ValueError:
        return None
    if parsed <= 0:
        return None
    return parsed


def _joined(values: Iterable[str]) -> str:
    return "; ".join(value for value in values if value)


def _max_units(report: ZoningReport) -> int | None:
    if report.density_analysis is None:
        return None
    return report.density_analysis.max_units


def _max_gla(report: ZoningReport) -> float | None:
    if report.density_analysis is None:
        return None
    return report.density_analysis.max_gla_sqft


def _governing_constraint(report: ZoningReport) -> str:
    if report.density_analysis is None:
        return ""
    return report.density_analysis.governing_constraint
