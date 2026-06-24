from __future__ import annotations

from typing import Any

from plotlot.harness.default_runtime_support import ev_id, project_id
from plotlot.land_use.models import EvidenceConfidence, EvidenceItem, SourceType, ToolContext


async def handle_geocode_address(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from plotlot.land_use.citations import geocode_citation
    from plotlot.retrieval.geocode import geocode_address

    address = str(args.get("address", "")).strip()
    try:
        result = await geocode_address(address)
    except Exception as e:
        return {"status": "error", "message": f"Geocoding failed: {type(e).__name__}: {e}"}
    if not result:
        return {"status": "not_found", "result": {}}

    evidence_id = ev_id()
    citation = geocode_citation(
        title="Geocoding result",
        publisher="Geocodio/Census",
        raw_text_for_hash=f"{address}:{result.get('lat')}:{result.get('lng')}",
    )
    evidence_item = EvidenceItem(
        id=evidence_id,
        workspace_id=context.workspace_id,
        project_id=project_id(context),
        site_id=context.site_id,
        analysis_id=context.analysis_id,
        analysis_run_id=context.analysis_run_id,
        tool_run_id=context.tool_run_id,
        claim_key="site.geocode",
        payload={"address": address, **result},
        source_type=SourceType.WEB_PAGE,
        tool_name="geocode_address",
        confidence=EvidenceConfidence.MEDIUM,
        citation=citation,
    )

    return {
        "status": "success",
        "result": result,
        "evidence": [evidence_item.model_dump(mode="json")],
    }


async def handle_lookup_property_info(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from plotlot.land_use.citations import county_record_citation
    from plotlot.retrieval.property import lookup_property
    from plotlot.retrieval.zoning_crosswalk import crosswalk_zoning_code

    address = str(args.get("address", "")).strip()
    county = str(args.get("county", "")).strip()
    state = str(args.get("state", "") or "").strip()
    lat = args.get("lat")
    lng = args.get("lng")
    if lat is None or lng is None:
        return {"status": "error", "message": "lat and lng are required"}

    try:
        record = await lookup_property(address, county, lat=float(lat), lng=float(lng), state=state)
    except Exception as e:
        return {"status": "error", "message": f"Property lookup failed: {type(e).__name__}: {e}"}
    if not record:
        return {"status": "not_found", "result": {}}

    gis_zoning_code = record.zoning_code or ""
    crosswalk = crosswalk_zoning_code(
        gis_zoning_code,
        state=state,
        county=record.county or county,
        municipality=record.municipality or "",
    )
    ordinance_district_code = crosswalk.search_code if crosswalk.matched else gis_zoning_code

    property_payload: dict[str, Any] = {
        "folio": record.folio,
        "address": record.address,
        "municipality": record.municipality,
        "county": record.county,
        "owner": record.owner,
        "zoning_code": record.zoning_code,
        "ordinance_district_code": ordinance_district_code,
        "zoning_description": record.zoning_description,
        "lot_size_sqft": record.lot_size_sqft,
        "lot_dimensions": record.lot_dimensions,
        "year_built": record.year_built,
        "assessed_value": record.assessed_value,
        "lat": record.lat,
        "lng": record.lng,
        "zoning_layer_url": record.zoning_layer_url,
    }
    result: dict[str, Any] = {"status": "success", "result": property_payload}

    evidence_id = ev_id()
    citation = county_record_citation(
        title="County property appraiser record",
        url=record.zoning_layer_url or None,
        jurisdiction=record.county,
        publisher=None,
        raw_text_for_hash=f"{record.folio}:{record.owner}:{record.zoning_code}:{record.lot_size_sqft}",
    )
    evidence_item = EvidenceItem(
        id=evidence_id,
        workspace_id=context.workspace_id,
        project_id=project_id(context),
        site_id=context.site_id,
        analysis_id=context.analysis_id,
        analysis_run_id=context.analysis_run_id,
        tool_run_id=context.tool_run_id,
        claim_key="site.property_record",
        payload=property_payload,
        source_type=SourceType.COUNTY_RECORD,
        tool_name="lookup_property_info",
        confidence=EvidenceConfidence.MEDIUM,
        citation=citation,
    )

    result["evidence"] = [evidence_item.model_dump(mode="json")]
    return result
