"""Active Property Dossier projection.

The dossier is a typed, artifact-ready view of the existing ZoningReport truth
object. It must not perform its own lookup or analysis; Lookup creates the
report and this module projects the same facts for Agent grounding.
"""

from datetime import UTC, datetime
import re
from typing import Any


def _get(obj: Any, key: str, default: Any = "") -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _infer_state(report: Any) -> str:
    for value in (_get(report, "formatted_address"), _get(report, "address")):
        if not value:
            continue
        match = re.search(r",\s*([A-Z]{2})\s+\d{5}(?:-\d{4})?\b", str(value))
        if match:
            return match.group(1)

    county = str(_get(report, "county", "")).lower()
    if county in {"miami-dade", "broward", "palm beach"}:
        return "FL"
    if county in {"mecklenburg", "cabarrus", "iredell", "union"}:
        return "NC"
    return ""


def _freshness_timestamp(value: str | None) -> str:
    return value or datetime.now(UTC).isoformat()


def _evidence_refs(report: Any) -> list[dict[str, str]]:
    confidence = str(_get(report, "confidence", ""))
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for source_ref in _get(report, "source_refs", []) or []:
        section = str(_get(source_ref, "section", ""))
        title = str(_get(source_ref, "section_title", ""))
        preview = str(_get(source_ref, "chunk_text_preview", ""))
        label = " — ".join(part for part in (section, title) if part) or "Ordinance source"
        key = ("ordinance_section", label)
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            {
                "kind": "ordinance_section",
                "label": label,
                "source": section,
                "preview": preview,
                "confidence": confidence,
            }
        )

    for source in _get(report, "sources", []) or []:
        label = str(source)
        key = ("source", label)
        if not label or key in seen:
            continue
        seen.add(key)
        refs.append(
            {
                "kind": "source",
                "label": label,
                "source": label,
                "preview": "",
                "confidence": confidence,
            }
        )

    property_record = _get(report, "property_record")
    folio = str(_get(property_record, "folio", ""))
    if folio:
        refs.append(
            {
                "kind": "property_record",
                "label": f"County property record {folio}",
                "source": folio,
                "preview": "",
                "confidence": confidence,
            }
        )

    return refs


def build_active_property_dossier(
    report: Any,
    *,
    freshness_timestamp: str | None = None,
) -> dict[str, Any]:
    """Build the canonical dossier projection from a zoning report."""
    property_record = _get(report, "property_record")
    density = _get(report, "density_analysis")
    numeric = _get(report, "numeric_params")
    setbacks = _get(report, "setbacks")

    lot_width = _get(density, "lot_width_ft", None) or _get(numeric, "min_lot_width_ft", None)
    lot_depth = _get(density, "lot_depth_ft", None)

    return {
        "resolved_address": _get(report, "formatted_address") or _get(report, "address"),
        "parcel_id": _get(property_record, "folio", ""),
        "municipality": _get(report, "municipality", ""),
        "county": _get(report, "county", ""),
        "state": _infer_state(report),
        "zoning_district": _get(report, "zoning_district", ""),
        "zoning_description": _get(report, "zoning_description", ""),
        "lot_facts": {
            "lot_size_sqft": _get(property_record, "lot_size_sqft", None),
            "lot_dimensions": _get(property_record, "lot_dimensions", ""),
            "lot_width_ft": lot_width,
            "lot_depth_ft": lot_depth,
        },
        "dimensional_standards": {
            "setbacks": {
                "front": _get(setbacks, "front", ""),
                "side": _get(setbacks, "side", ""),
                "rear": _get(setbacks, "rear", ""),
            },
            "max_height": _get(report, "max_height", ""),
            "max_density": _get(report, "max_density", ""),
            "floor_area_ratio": _get(report, "floor_area_ratio", ""),
            "lot_coverage": _get(report, "lot_coverage", ""),
            "min_lot_size": _get(report, "min_lot_size", ""),
            "parking_requirements": _get(report, "parking_requirements", ""),
        },
        "max_units": _get(density, "max_units", None) if density else None,
        "governing_constraint": _get(density, "governing_constraint", "") if density else "",
        "evidence_refs": _evidence_refs(report),
        "confidence": _get(report, "confidence", "unknown") or "unknown",
        "freshness_timestamp": _freshness_timestamp(freshness_timestamp),
    }
