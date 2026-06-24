import type { ZoningReportData } from "../../src/lib/api";

export const metrics = {
  evidence_coverage: 1,
  source_quality_traceability: 1,
  calculation_lineage_traceability: 1,
  trace_replayability: 1,
  specialist_lane_coverage: 1,
  artifact_citation_coverage: 1,
  opportunity_hypothesis_completeness: 1,
  assumption_label_coverage: 1,
  escalation_visibility: 1,
  ready_for_synthesis_gate: 1,
  unsupported_claim_rate: 0,
} as const;

export function evalPayload() {
  return {
    run_id: "run_frontend_agent",
    lookup_snapshot_id: "lookup_frontend",
    eval_run_id: "eval_frontend_agent",
    eval_case_result_id: "case_frontend_agent",
    status: "passed",
    metrics,
  };
}

export function jsonResponse(payload: object): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

export function reportWithoutSnapshot(): ZoningReportData {
  return {
    address: "7940 Plantation Blvd, Miramar, FL 33023",
    formatted_address: "7940 Plantation Blvd, Miramar, FL 33023",
    municipality: "Miramar",
    county: "Broward",
    lat: 26,
    lng: -80,
    zoning_district: "RS-4",
    zoning_description: "Residential",
    allowed_uses: [],
    conditional_uses: [],
    prohibited_uses: [],
    setbacks: { front: "", side: "", rear: "" },
    max_height: "35 ft",
    max_density: "",
    floor_area_ratio: "",
    lot_coverage: "",
    min_lot_size: "",
    parking_requirements: "",
    property_record: null,
    numeric_params: null,
    density_analysis: null,
    comp_analysis: null,
    pro_forma: null,
    site_risk: null,
    deal_analysis: null,
    summary: "",
    sources: [],
    confidence: "medium",
  };
}

export function reportWithSnapshot(): ZoningReportData {
  return {
    ...reportWithoutSnapshot(),
    lookup_snapshot: {
      lookup_snapshot_id: "lookup_frontend",
      site_id: "site_frontend",
      run_id: "lookup_run_frontend",
      fields: [
        {
          key: "parcel.apn",
          label: "APN",
          value: "504210230010",
          unit: "",
          display_state: "verified",
          evidence_ids: ["evidence-parcel"],
          source_priority: ["parcel_appraiser"],
          fallback_sources: ["county_gis"],
          failure_behavior: "escalate",
          confidence: 1,
          freshness: "current",
          warnings: [],
        },
        {
          key: "zoning.district",
          label: "Zoning district",
          value: "RS-4",
          unit: "",
          display_state: "verified",
          evidence_ids: ["evidence-zoning"],
          source_priority: ["official_zoning_map"],
          fallback_sources: ["planning_department_pdf"],
          failure_behavior: "unknown",
          confidence: 1,
          freshness: "current",
          warnings: [],
        },
        {
          key: "parking.minimum",
          label: "Parking",
          value: "2 spaces per dwelling",
          unit: "",
          display_state: "stale",
          evidence_ids: ["evidence-parking"],
          source_priority: ["official_zoning_ordinance"],
          fallback_sources: [],
          failure_behavior: "warn",
          confidence: 0.82,
          freshness: "stale",
          warnings: ["Confirm adopted parking table."],
        },
        {
          key: "standards.lot_coverage",
          label: "Lot coverage",
          value: null,
          unit: "",
          display_state: "requires_human_review",
          evidence_ids: [],
          source_priority: ["official_zoning_ordinance"],
          fallback_sources: ["planning_department_pdf"],
          failure_behavior: "escalate",
          confidence: 0,
          freshness: "unknown",
          warnings: ["missing_evidence"],
        },
      ],
      calculations: [
        {
          calculator_name: "max_units",
          calculator_version: "1",
          formula: "density",
          input_evidence_ids: ["evidence-zoning"],
          output_label: "max_units=2",
          warnings: [],
        },
      ],
      warnings: [],
      source_metadata: [
        {
          evidence_id: "evidence-parcel",
          source_url: "https://bcpa.net/parcel/504210230010",
          source_title: "Official parcel appraiser",
          effective_date: "2026-01-01",
        },
        {
          evidence_id: "evidence-zoning",
          source_url: "https://miramarfl.gov/zoning-map",
          source_title: "Official zoning map",
          effective_date: "2026-01-15",
        },
      ],
    },
  };
}
