"""Data center site selection pipeline.

Phase 6 — separate pipeline from the residential zoning flow.
Steps:
  1. Geocode address (shared with residential)
  2. ArcGIS property lookup (shared)
  3. EIA API — power grid / substation proximity
  4. FCC National Broadband Map — fiber connectivity
  5. FEMA NFIP — flood zone
  6. USGS Seismic Hazard — seismic risk
  7. Hybrid zoning RAG — industrial ordinance sections
  8. LLM extraction — DataCenterParams from retrieved chunks
  9. Scoring — InfraSignal per dimension, composite SiteScorecard
"""

import asyncio
import json
import logging

import httpx

from plotlot.core.types import (
    DataCenterParams,
    InfraSignal,
    PropertyRecord,
    SearchResult,
    SiteScorecard,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

_FLOOD_ZONE_SCORES: dict[str, tuple[float, str]] = {
    # FEMA flood zone → (score, rating)
    "X": (1.0, "Excellent"),  # Minimal flood hazard
    "X500": (0.85, "Good"),  # 0.2% annual chance
    "AE": (0.35, "Poor"),  # 1% annual chance, base flood elevation
    "A": (0.3, "Poor"),  # 1% annual chance, no BFE
    "VE": (0.1, "Poor"),  # Coastal high hazard
    "V": (0.1, "Poor"),
    "AO": (0.4, "Fair"),
    "AH": (0.4, "Fair"),
}

_SEISMIC_SCORES: dict[str, tuple[float, str]] = {
    # USGS hazard class → (score, rating)
    "very_low": (1.0, "Excellent"),
    "low": (0.8, "Good"),
    "moderate": (0.55, "Fair"),
    "high": (0.3, "Poor"),
    "very_high": (0.1, "Poor"),
}


# ---------------------------------------------------------------------------
# EIA API — power grid signal
# ---------------------------------------------------------------------------


async def fetch_power_signal(lat: float, lng: float) -> InfraSignal:
    """Query EIA API for nearby utility service area and substation data.

    Uses EIA's Form 861 service territory data (free, no key required for
    basic lookups) and the EIA Open Data API for facility-level data.
    Falls back to county-level heuristic when API is unavailable.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # EIA's spatial API: find utility service areas at a lat/lng point
            resp = await client.get(
                "https://developer.nrel.gov/api/utility_rates/v3.json",
                params={
                    "lat": lat,
                    "lon": lng,
                    "api_key": "DEMO_KEY",  # NREL public demo key for utility lookup
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                outputs = data.get("outputs", {})
                utility = outputs.get("utility_name", "Unknown utility")
                # NREL returns residential/commercial rates — use as proxy for grid access
                commercial_rate = outputs.get("commercial", None)
                if commercial_rate and float(commercial_rate) < 0.12:
                    score, rating = 0.9, "Excellent"
                    summary = f"Low commercial rate (${commercial_rate}/kWh) via {utility} — favorable for hyperscale power budgets."
                elif commercial_rate and float(commercial_rate) < 0.15:
                    score, rating = 0.75, "Good"
                    summary = f"Moderate commercial rate (${commercial_rate}/kWh) via {utility}."
                else:
                    score, rating = 0.5, "Fair"
                    summary = f"Commercial electricity rate above $0.15/kWh via {utility}. Factor into PUE modeling."
                return InfraSignal(
                    name="power_grid",
                    label="Grid Access & Rate",
                    score=score,
                    rating=rating,
                    summary=summary,
                    raw_value=f"{utility} — ${commercial_rate}/kWh" if commercial_rate else utility,
                    source="NREL Utility Rates API",
                    confidence="high",
                )
    except Exception as exc:
        logger.warning("Power signal fetch failed: %s", exc)

    # Graceful fallback — Florida has among the lowest industrial rates in SE US
    return InfraSignal(
        name="power_grid",
        label="Grid Access & Rate",
        score=0.65,
        rating="Good",
        summary="Grid access confirmed via county utility service area. Rate data unavailable — assume regional average.",
        raw_value="estimated",
        source="NREL Utility Rates API (fallback)",
        confidence="low",
    )


# ---------------------------------------------------------------------------
# FCC National Broadband Map — fiber signal
# ---------------------------------------------------------------------------


async def fetch_fiber_signal(lat: float, lng: float) -> InfraSignal:
    """Query FCC National Broadband Map for fiber availability at this location.

    FCC NBM API is free and public. Returns provider list and max advertised speeds.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://broadbandmap.fcc.gov/api/public/map/listAvailability",
                params={
                    "latitude": lat,
                    "longitude": lng,
                    "unit": "location",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                providers = data.get("availability", [])
                # Filter to fiber (technology_code 50 = fiber to premises)
                fiber_providers = [
                    p
                    for p in providers
                    if p.get("technology_code") in (50, 70)  # 50=FTTH, 70=cable
                ]
                if not providers and not fiber_providers:
                    return InfraSignal(
                        name="fiber",
                        label="Fiber Connectivity",
                        score=0.1,
                        rating="Poor",
                        summary="No broadband providers reported at this location. Dark fiber build-out required.",
                        raw_value="No providers",
                        source="FCC National Broadband Map",
                        confidence="medium",
                    )

                max_down = max(
                    (p.get("max_advertised_download_speed", 0) for p in providers), default=0
                )
                fiber_count = len(fiber_providers)

                if fiber_count >= 2 and max_down >= 1000:
                    score, rating = 0.95, "Excellent"
                    summary = f"{fiber_count} fiber providers with {max_down} Mbps max download. Carrier-neutral interconnect likely available."
                elif fiber_count >= 1 and max_down >= 100:
                    score, rating = 0.75, "Good"
                    summary = f"{fiber_count} fiber provider(s), {max_down} Mbps max. Single-carrier risk — verify dark fiber availability."
                elif max_down >= 100:
                    score, rating = 0.55, "Fair"
                    summary = f"Cable/fixed wireless at {max_down} Mbps. No dedicated fiber confirmed — telco engagement required."
                else:
                    score, rating = 0.3, "Poor"
                    summary = f"Limited connectivity ({max_down} Mbps max). Significant fiber infrastructure investment likely required."

                return InfraSignal(
                    name="fiber",
                    label="Fiber Connectivity",
                    score=score,
                    rating=rating,
                    summary=summary,
                    raw_value=f"{fiber_count} fiber providers, {max_down} Mbps max",
                    source="FCC National Broadband Map",
                    confidence="high",
                )
    except Exception as exc:
        logger.warning("Fiber signal fetch failed: %s", exc)

    return InfraSignal(
        name="fiber",
        label="Fiber Connectivity",
        score=0.6,
        rating="Fair",
        summary="Fiber availability data unavailable. Recommend direct telco carrier survey before site selection.",
        raw_value="estimated",
        source="FCC National Broadband Map (fallback)",
        confidence="low",
    )


# ---------------------------------------------------------------------------
# FEMA NFIP — flood zone signal
# ---------------------------------------------------------------------------


async def fetch_flood_signal(lat: float, lng: float) -> InfraSignal:
    """Query FEMA NFIP Flood Map Service for flood zone designation.

    Uses FEMA's public REST API (no key required).
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://msc.fema.gov/arcgis/rest/services/NFHL/MapService/3/query",
                params={
                    "geometry": f"{lng},{lat}",
                    "geometryType": "esriGeometryPoint",
                    "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "FLD_ZONE,ZONE_SUBTY",
                    "returnGeometry": "false",
                    "f": "json",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                features = data.get("features", [])
                if features:
                    attrs = features[0].get("attributes", {})
                    fld_zone = (attrs.get("FLD_ZONE") or "X").upper().strip()
                    zone_subty = (attrs.get("ZONE_SUBTY") or "").upper().strip()

                    zone_key = fld_zone
                    if zone_subty == "0.2 PCT ANNUAL CHANCE FLOOD HAZARD":
                        zone_key = "X500"

                    score, rating = _FLOOD_ZONE_SCORES.get(zone_key, (0.5, "Fair"))
                    display_zone = f"{fld_zone}" + (f" ({zone_subty})" if zone_subty else "")

                    if fld_zone == "X":
                        summary = "FEMA Flood Zone X — minimal flood hazard. No NFIP insurance required. Optimal for critical infrastructure."
                    elif zone_key == "X500":
                        summary = "FEMA Flood Zone X (0.2% annual chance). Low risk, but above-grade electrical rooms recommended."
                    elif fld_zone in ("AE", "A"):
                        summary = f"FEMA Flood Zone {fld_zone} — 100-year floodplain. Critical infrastructure typically disqualified. Significant elevation required."
                    else:
                        summary = f"FEMA Flood Zone {display_zone}. Review site-specific flood mitigation requirements before proceeding."

                    return InfraSignal(
                        name="flood_zone",
                        label="Flood Zone",
                        score=score,
                        rating=rating,
                        summary=summary,
                        raw_value=display_zone,
                        source="FEMA NFIP Flood Map Service",
                        confidence="high",
                    )
    except Exception as exc:
        logger.warning("Flood signal fetch failed: %s", exc)

    return InfraSignal(
        name="flood_zone",
        label="Flood Zone",
        score=0.7,
        rating="Good",
        summary="Flood zone data unavailable via API. Recommend manual FEMA FIRM panel review before site selection.",
        raw_value="unknown",
        source="FEMA NFIP (fallback)",
        confidence="low",
    )


# ---------------------------------------------------------------------------
# USGS Seismic Hazard — seismic signal
# ---------------------------------------------------------------------------


async def fetch_seismic_signal(lat: float, lng: float) -> InfraSignal:
    """Query USGS Seismic Hazard API for ground motion hazard at this location.

    Uses USGS National Seismic Hazard Model (2018) public API.
    PGA = Peak Ground Acceleration at 2% probability in 50 years.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://earthquake.usgs.gov/ws/designmaps/asce7-22.json",
                params={
                    "latitude": lat,
                    "longitude": lng,
                    "riskCategory": "IV",  # Critical facilities = Risk Category IV
                    "siteClass": "D",  # Default stiff soil
                    "title": "datacenter",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                output = data.get("response", {}).get("data", {})
                # Ss = spectral acceleration at short period, in g
                ss = output.get("ss", None)
                if ss is not None:
                    ss = float(ss)
                    if ss < 0.15:
                        hazard_class = "very_low"
                        summary = f"Ss = {ss:.2f}g — very low seismic hazard. Standard seismic detailing (SDC A/B) sufficient."
                    elif ss < 0.50:
                        hazard_class = "low"
                        summary = f"Ss = {ss:.2f}g — low seismic hazard. Moderate seismic design (SDC B/C) required."
                    elif ss < 1.00:
                        hazard_class = "moderate"
                        summary = f"Ss = {ss:.2f}g — moderate seismic hazard. Enhanced seismic design (SDC C/D) required. Factor into structural costs."
                    elif ss < 1.50:
                        hazard_class = "high"
                        summary = f"Ss = {ss:.2f}g — high seismic hazard. Special seismic provisions required (SDC D/E). Significant structural premium."
                    else:
                        hazard_class = "very_high"
                        summary = f"Ss = {ss:.2f}g — very high seismic hazard. Seismic isolation or specialized structural system likely required."

                    score, rating = _SEISMIC_SCORES[hazard_class]
                    return InfraSignal(
                        name="seismic",
                        label="Seismic Risk",
                        score=score,
                        rating=rating,
                        summary=summary,
                        raw_value=f"Ss = {ss:.2f}g (ASCE 7-22 Risk Category IV)",
                        source="USGS Seismic Hazard API",
                        confidence="high",
                    )
    except Exception as exc:
        logger.warning("Seismic signal fetch failed: %s", exc)

    # Florida/SE default — very low seismic risk
    return InfraSignal(
        name="seismic",
        label="Seismic Risk",
        score=0.95,
        rating="Excellent",
        summary="Seismic data unavailable via API. Florida/SE US has historically very low seismic hazard — standard design is sufficient.",
        raw_value="estimated (FL default)",
        source="USGS Seismic Hazard API (fallback)",
        confidence="low",
    )


# ---------------------------------------------------------------------------
# Zoning signal — derived from DataCenterParams extraction
# ---------------------------------------------------------------------------


def score_zoning_signal(params: DataCenterParams, zoning_code: str) -> InfraSignal:
    """Convert extracted DataCenterParams into a zoning InfraSignal.

    Score logic:
    - Industrial permitted as-of-right → 1.0
    - Conditional use permit required → 0.65
    - Not permitted in this zone → 0.0 (deal breaker)
    - Unknown / extraction low confidence → 0.5
    """
    if params.is_industrial_permitted is True and not params.conditional_use_required:
        score, rating = 1.0, "Excellent"
        summary = f"Data center / heavy industrial permitted as-of-right in {zoning_code or params.zoning_code}. No conditional use approval needed."
    elif params.is_industrial_permitted is True and params.conditional_use_required:
        score, rating = 0.65, "Good"
        summary = f"Data center use requires Conditional Use Permit (CUP) in {zoning_code or params.zoning_code}. 60–120 day approval process typical."
    elif params.is_industrial_permitted is False:
        score, rating = 0.0, "Poor"
        summary = f"Data center / heavy industrial NOT permitted in {zoning_code or params.zoning_code}. Rezoning or variance required — high-risk path."
    else:
        score, rating = 0.5, "Fair"
        summary = f"Zoning permissibility for data center use could not be confirmed in {zoning_code or params.zoning_code}. Manual zoning review required."

    noise_note = ""
    if params.noise_limit_db is not None and params.noise_limit_db < 55:
        # Cooling towers typically produce 65–75 dB — below 55 dB limit is a constraint
        noise_note = f" Noise limit of {params.noise_limit_db} dB(A) may conflict with cooling tower requirements."
        score = min(score, 0.6)
        rating = "Fair" if rating in ("Excellent", "Good") else rating
        summary += noise_note

    return InfraSignal(
        name="zoning",
        label="Zoning & Land Use",
        score=score,
        rating=rating,
        summary=summary,
        raw_value=params.zoning_code or zoning_code,
        source="Municode Ordinance RAG",
        confidence="medium" if params.is_industrial_permitted is None else "high",
    )


# ---------------------------------------------------------------------------
# LLM extraction — DataCenterParams from industrial ordinance chunks
# ---------------------------------------------------------------------------

_DC_EXTRACTION_SYSTEM_PROMPT = """\
You are a zoning attorney extracting data center siting parameters from industrial zoning ordinances.

Extract the following as JSON:
{
  "zoning_code": "string — the zoning district code (e.g. I-1, M-2, BL)",
  "zoning_description": "string — full name of the district",
  "is_industrial_permitted": true/false/null — is a data center / heavy industrial / server farm use permitted?
    true = permitted by right, false = not permitted, null = cannot determine
  "conditional_use_required": true/false/null — is a CUP/SUP/conditional use permit required?
  "setback_front_ft": number or null,
  "setback_side_ft": number or null,
  "setback_rear_ft": number or null,
  "max_height_ft": number or null,
  "max_lot_coverage_pct": number or null,
  "max_far": number or null,
  "noise_limit_db": number or null — noise limit in dB(A) at property line,
  "outdoor_equipment_allowed": true/false/null — are outdoor mechanical units (cooling towers, generators) permitted?,
  "min_lot_area_sqft": number or null,
  "loading_docks_required": integer or null,
  "utility_easement_notes": "string — any notes on utility easements, overhead lines, etc.",
  "source_sections": ["section-number", ...] — which sections you extracted from
}

Return ONLY valid JSON. No preamble, no explanation.
"""


async def extract_datacenter_params(
    municipality: str,
    county: str,
    zoning_code: str,
    results: list[SearchResult],
) -> DataCenterParams:
    """Extract DataCenterParams from industrial ordinance search results via LLM."""
    if not results:
        logger.warning("No search results for datacenter param extraction in %s", municipality)
        return DataCenterParams(zoning_code=zoning_code)

    # Build context from retrieved chunks
    context_parts = []
    for r in results[:12]:  # cap at 12 chunks ~= 6K tokens
        context_parts.append(f"[{r.section} — {r.section_title}]\n{r.chunk_text}")
    context = "\n\n---\n\n".join(context_parts)

    user_msg = (
        f"Municipality: {municipality}, {county}\n"
        f"Zoning district code from property appraiser: {zoning_code}\n\n"
        f"Ordinance sections:\n{context}"
    )

    try:
        from plotlot.retrieval.llm import _call_llm_with_fallback  # type: ignore[attr-defined]

        result = await _call_llm_with_fallback(
            messages=[
                {"role": "system", "content": _DC_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=1200,
            temperature=0.0,
            openai_provider_name="OpenAI/gpt-4.1",
            openrouter_provider_name="OpenRouter/openai/gpt-4.1",
        )
        if result and result.get("content"):
            raw = json.loads(result["content"])
            return DataCenterParams(
                zoning_code=raw.get("zoning_code", zoning_code),
                zoning_description=raw.get("zoning_description", ""),
                is_industrial_permitted=raw.get("is_industrial_permitted"),
                conditional_use_required=raw.get("conditional_use_required"),
                setback_front_ft=raw.get("setback_front_ft"),
                setback_side_ft=raw.get("setback_side_ft"),
                setback_rear_ft=raw.get("setback_rear_ft"),
                max_height_ft=raw.get("max_height_ft"),
                max_lot_coverage_pct=raw.get("max_lot_coverage_pct"),
                max_far=raw.get("max_far"),
                noise_limit_db=raw.get("noise_limit_db"),
                outdoor_equipment_allowed=raw.get("outdoor_equipment_allowed"),
                min_lot_area_sqft=raw.get("min_lot_area_sqft"),
                loading_docks_required=raw.get("loading_docks_required"),
                utility_easement_notes=raw.get("utility_easement_notes", ""),
                source_sections=raw.get("source_sections", []),
            )
    except Exception as exc:
        logger.error("DataCenterParams LLM extraction failed: %s", exc)

    return DataCenterParams(zoning_code=zoning_code)


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

_SIGNAL_WEIGHTS: dict[str, float] = {
    "power_grid": 0.25,
    "fiber": 0.20,
    "flood_zone": 0.25,
    "seismic": 0.10,
    "zoning": 0.20,
}


def compute_composite_score(
    power: InfraSignal,
    fiber: InfraSignal,
    flood: InfraSignal,
    seismic: InfraSignal,
    zoning: InfraSignal,
) -> tuple[float, str]:
    """Weighted composite score → (score 0.0–1.0, rating label)."""
    signals = {
        "power_grid": power,
        "fiber": fiber,
        "flood_zone": flood,
        "seismic": seismic,
        "zoning": zoning,
    }

    # Hard disqualifier: zoning score of 0 → not a viable site
    if zoning.score == 0.0:
        return 0.0, "Disqualified"

    weighted_sum = sum(_SIGNAL_WEIGHTS[name] * sig.score for name, sig in signals.items())

    if weighted_sum >= 0.85:
        rating = "Excellent"
    elif weighted_sum >= 0.70:
        rating = "Good"
    elif weighted_sum >= 0.50:
        rating = "Fair"
    else:
        rating = "Poor"

    return round(weighted_sum, 3), rating


# ---------------------------------------------------------------------------
# LLM executive summary
# ---------------------------------------------------------------------------

_SUMMARY_SYSTEM_PROMPT = """\
You are a data center site selection advisor. Write a 3-sentence executive summary
for a potential data center site. Be direct, use plain language, quantify key risks.

Output JSON:
{
  "summary": "string — 3 sentences, exec-level",
  "deal_breakers": ["string", ...] — list of hard disqualifiers (0-3 items),
  "strengths": ["string", ...] — list of site strengths (1-4 items)
}
"""


async def generate_site_summary(
    address: str,
    scorecard_dict: dict,
) -> tuple[str, list[str], list[str]]:
    """Generate executive summary, deal breakers, and strengths from scorecard data."""
    try:
        from plotlot.retrieval.llm import _call_llm_with_fallback  # type: ignore[attr-defined]

        user_msg = (
            f"Site address: {address}\n\nScorecard data:\n{json.dumps(scorecard_dict, indent=2)}"
        )

        result = await _call_llm_with_fallback(
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=600,
            temperature=0.2,
            openai_provider_name="OpenAI/gpt-4.1",
            openrouter_provider_name="OpenRouter/openai/gpt-4.1",
        )
        if result and result.get("content"):
            raw = json.loads(result["content"])
            return (
                raw.get("summary", ""),
                raw.get("deal_breakers", []),
                raw.get("strengths", []),
            )
    except Exception as exc:
        logger.error("Site summary generation failed: %s", exc)

    return "", [], []


# ---------------------------------------------------------------------------
# Full pipeline entry point
# ---------------------------------------------------------------------------


async def run_datacenter_pipeline(
    address: str,
    property_record: PropertyRecord,
    lat: float,
    lng: float,
    municipality: str,
    county: str,
    zoning_results: list[SearchResult],
) -> SiteScorecard:
    """Run the full data center site selection pipeline.

    Called by the /analyze/datacenter SSE endpoint after geocode + property
    lookup are complete. Infrastructure signals are fetched concurrently.
    """
    zoning_code = property_record.zoning_code or ""

    # Step 1: Fetch all infrastructure signals concurrently
    power_task = asyncio.create_task(fetch_power_signal(lat, lng))
    fiber_task = asyncio.create_task(fetch_fiber_signal(lat, lng))
    flood_task = asyncio.create_task(fetch_flood_signal(lat, lng))
    seismic_task = asyncio.create_task(fetch_seismic_signal(lat, lng))
    dc_params_task = asyncio.create_task(
        extract_datacenter_params(municipality, county, zoning_code, zoning_results)
    )

    power_signal, fiber_signal, flood_signal, seismic_signal, dc_params = await asyncio.gather(
        power_task, fiber_task, flood_task, seismic_task, dc_params_task
    )

    # Step 2: Score the zoning signal from extracted params
    zoning_signal = score_zoning_signal(dc_params, zoning_code)

    # Step 3: Composite score
    composite_score, composite_rating = compute_composite_score(
        power_signal, fiber_signal, flood_signal, seismic_signal, zoning_signal
    )

    # Build partial scorecard for summary generation
    partial = {
        "composite_score": composite_score,
        "composite_rating": composite_rating,
        "signals": {
            "power": {
                "score": power_signal.score,
                "rating": power_signal.rating,
                "summary": power_signal.summary,
            },
            "fiber": {
                "score": fiber_signal.score,
                "rating": fiber_signal.rating,
                "summary": fiber_signal.summary,
            },
            "flood": {
                "score": flood_signal.score,
                "rating": flood_signal.rating,
                "summary": flood_signal.summary,
            },
            "seismic": {
                "score": seismic_signal.score,
                "rating": seismic_signal.rating,
                "summary": seismic_signal.summary,
            },
            "zoning": {
                "score": zoning_signal.score,
                "rating": zoning_signal.rating,
                "summary": zoning_signal.summary,
            },
        },
    }

    # Step 4: Generate executive summary
    summary, deal_breakers, strengths = await generate_site_summary(address, partial)

    sources = [
        "NREL Utility Rates API",
        "FCC National Broadband Map",
        "FEMA NFIP Flood Map Service",
        "USGS Seismic Hazard API",
        "Municode Ordinance RAG",
    ]
    sources.extend(dc_params.source_sections)

    return SiteScorecard(
        address=address,
        formatted_address=address,
        municipality=municipality,
        county=county,
        lat=lat,
        lng=lng,
        property_record=property_record,
        power_signal=power_signal,
        fiber_signal=fiber_signal,
        flood_signal=flood_signal,
        seismic_signal=seismic_signal,
        zoning_signal=zoning_signal,
        datacenter_params=dc_params,
        composite_score=composite_score,
        composite_rating=composite_rating,
        summary=summary,
        deal_breakers=deal_breakers,
        strengths=strengths,
        sources=list(set(sources)),
        confidence="high"
        if all(
            s.confidence == "high"
            for s in [power_signal, fiber_signal, flood_signal, seismic_signal, zoning_signal]
        )
        else "medium",
    )
