from __future__ import annotations

from pydantic import ConfigDict, Field

from plotlot.harness.contracts.base import HarnessContract, JsonObject


class PipelineStageSummary(HarnessContract):
    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    artifact_keys: list[str] = Field(default_factory=list)


def build_pipeline_stages(artifacts: JsonObject, analysis_type: str) -> list[PipelineStageSummary]:
    warnings = [
        str(item).strip()
        for item in artifacts.get("warnings", [])
        if isinstance(item, str) and str(item).strip()
    ]
    return [
        _site_stage(artifacts),
        _zoning_stage(artifacts, warnings),
        _comps_stage(artifacts, warnings),
        _feasibility_stage(artifacts, warnings, analysis_type),
        _underwriting_stage(artifacts, warnings, analysis_type),
    ]


def build_pipeline_stage_artifacts(stages: list[PipelineStageSummary]) -> JsonObject:
    underwriting_stage = next((stage for stage in stages if stage.key == "underwriting"), None)
    return {
        "pipeline_stage_statuses": {stage.key: stage.status for stage in stages},
        "underwriting_stage": (
            underwriting_stage.model_dump(mode="json") if underwriting_stage is not None else {}
        ),
    }


def _site_stage(artifacts: JsonObject) -> PipelineStageSummary:
    geocode = _artifact(artifacts, "geocode")
    property_record = _artifact(artifacts, "property_record")
    address = str(
        property_record.get("address") or geocode.get("formatted_address") or "Address resolved"
    ).strip()
    folio = str(property_record.get("folio") or property_record.get("parcel_id") or "").strip()
    summary = address if not folio else f"{address} ({folio})"
    return PipelineStageSummary(
        key="site_identification",
        title="Address and parcel",
        status="completed" if property_record else ("partial" if geocode else "missing"),
        summary=summary,
        artifact_keys=["geocode", "property_record"],
    )


def _zoning_stage(artifacts: JsonObject, warnings: list[str]) -> PipelineStageSummary:
    property_record = _artifact(artifacts, "property_record")
    ordinance = _artifact(artifacts, "ordinance_search") or _artifact(artifacts, "ordinance_rules")
    source_context = _artifact(artifacts, "gis_source") or _artifact(artifacts, "municode_search")
    zoning_code = str(
        property_record.get("zoning_code") or property_record.get("ordinance_district_code") or ""
    ).strip()
    status = (
        "completed" if ordinance else ("partial" if source_context or zoning_code else "missing")
    )
    if _warning_matches(warnings, "zoning", "ordinance", "municipal"):
        status = "warning" if status != "missing" else "missing"
    return PipelineStageSummary(
        key="zoning_evidence",
        title="Zoning and ordinance",
        status=status,
        summary=zoning_code or "Preliminary zoning context",
        artifact_keys=[
            "property_record",
            "gis_source",
            "municode_search",
            "ordinance_rules",
            "ordinance_search",
        ],
    )


def _comps_stage(artifacts: JsonObject, warnings: list[str]) -> PipelineStageSummary:
    comps = _artifact(artifacts, "comps")
    direct_count = len(_artifact_list(comps, "comparables"))
    unit_count = len(_artifact_list(comps, "unit_comparables"))
    status = "completed" if direct_count or unit_count else ("partial" if comps else "missing")
    if _warning_matches(warnings, "comp", "pricing", "market"):
        status = "warning" if comps else "missing"
    summary = "Comparable sales pending"
    if direct_count or unit_count:
        summary = f"{direct_count} sales comps, {unit_count} unit comps"
    return PipelineStageSummary(
        key="comparables",
        title="Comparable sales",
        status=status,
        summary=summary,
        artifact_keys=["comps"],
    )


def _feasibility_stage(
    artifacts: JsonObject,
    warnings: list[str],
    analysis_type: str,
) -> PipelineStageSummary:
    feasibility = _artifact(artifacts, "feasibility")
    if feasibility:
        status = "completed"
    elif analysis_type in {"acquisition_memo", "development_underwriting", "lender_package"}:
        status = (
            "warning"
            if _warning_matches(warnings, "feasibility", "maxfar", "maxunits")
            else "missing"
        )
    else:
        status = "not_required"
    result = _artifact_result(feasibility)
    units = result.get("estimated_units")
    buildable = result.get("max_gross_buildable_sf")
    summary = "Feasibility calculation pending"
    if units is not None or buildable is not None:
        summary = (
            f"Units: {units if units is not None else 'n/a'}"
            f" • Buildable sf: {buildable if buildable is not None else 'n/a'}"
        )
    return PipelineStageSummary(
        key="feasibility",
        title="Feasibility",
        status=status,
        summary=summary,
        artifact_keys=["feasibility"],
    )


def _underwriting_stage(
    artifacts: JsonObject,
    warnings: list[str],
    analysis_type: str,
) -> PipelineStageSummary:
    underwriting_mode = _artifact(artifacts, "underwriting_mode")
    mode = str(underwriting_mode.get("mode") or "").strip()
    noi = _artifact(artifacts, "noi_valuation")
    residual = _artifact(artifacts, "residual_land_value")
    pro_forma = _artifact(artifacts, "pro_forma")
    if noi and residual:
        status = "completed"
    elif mode == "sold_unit_exit" and pro_forma:
        status = "completed"
    elif noi or residual or pro_forma:
        status = "partial"
    elif analysis_type in {"acquisition_memo", "development_underwriting", "lender_package"}:
        status = (
            "warning"
            if _warning_matches(warnings, "noi", "residual", "underwriting", "rent")
            else "missing"
        )
    else:
        status = "not_required"
    residual_result = _artifact_result(residual)
    noi_result = _artifact_result(noi)
    pro_forma_result = _artifact_result(pro_forma)
    max_offer = residual_result.get("max_supportable_land_price")
    if max_offer is None:
        max_offer = pro_forma_result.get("max_supportable_land_price")
    value = noi_result.get("as_built_value")
    summary = "Underwriting outputs pending"
    if max_offer is not None or value is not None:
        summary = (
            f"As-built value: {value if value is not None else 'n/a'}"
            f" • Max land price: {max_offer if max_offer is not None else 'n/a'}"
        )
    if mode == "sold_unit_exit":
        summary = f"{summary} • Basis: sold-unit exit"
    elif mode == "income_cap_rate":
        summary = f"{summary} • Basis: income approach"
    return PipelineStageSummary(
        key="underwriting",
        title="Underwriting",
        status=status,
        summary=summary,
        artifact_keys=["noi_valuation", "residual_land_value"],
    )


def _artifact(artifacts: JsonObject, key: str) -> JsonObject:
    value = artifacts.get(key, {})
    return value if isinstance(value, dict) else {}


def _artifact_result(artifact: JsonObject) -> JsonObject:
    value = artifact.get("result")
    return value if isinstance(value, dict) else artifact


def _artifact_list(artifact: JsonObject, key: str) -> list[object]:
    value = artifact.get(key, [])
    return value if isinstance(value, list) else []


def _warning_matches(warnings: list[str], *needles: str) -> bool:
    return any(any(needle in warning.lower() for needle in needles) for warning in warnings)
