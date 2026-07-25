import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getHarnessRunMock = vi.fn();
const getHarnessRunEventsMock = vi.fn();
const getHarnessRunVerificationMock = vi.fn();

vi.mock("../../src/lib/api", () => ({
  getHarnessRun: (...args: unknown[]) => getHarnessRunMock(...args),
  getHarnessRunEvents: (...args: unknown[]) => getHarnessRunEventsMock(...args),
  getHarnessRunVerification: (...args: unknown[]) => getHarnessRunVerificationMock(...args),
}));

import HarnessRunDetail from "../../src/components/HarnessRunDetail";

describe("HarnessRunDetail", () => {
  beforeEach(() => {
    getHarnessRunMock.mockReset();
    getHarnessRunEventsMock.mockReset();
    getHarnessRunVerificationMock.mockReset();
  });

  it("loads and renders a persisted harness run with verification and event history", async () => {
    getHarnessRunMock.mockResolvedValue({
      run_id: "run_fixture_detail_001",
      analysis_type: "acquisition_memo",
      status: "completed",
      events_url: "/api/v1/harness/runs/run_fixture_detail_001/events",
      report_id: "report_fixture_detail_001",
      evidence_ids: ["ev_market_1", "ev_zone_1"],
      verification_status: "passed_with_warnings",
      source_mode: "live",
      preliminary: false,
      claims: [
        {
          claim_id: "claim_1",
          claim_type: "comp_value_signal",
          claim_text: "Comparable sales support a land value range for this site.",
          confidence: 0.82,
          source_mode: "live",
        },
      ],
      evidence_items: [
        {
          evidence_id: "ev_market_1",
          source_type: "market_comp",
          source_name: "Miami-Dade comparable sale",
          source_identifier: "19646 NE 14 CT",
          county: "Miami-Dade",
          municipality: "Miami Gardens",
          freshness_status: "fresh",
          applicability: "contextual",
        },
      ],
      calculations: [
        {
          calculation_id: "calc_1",
          calculation_type: "residual_land_value",
          formula_version: "residual_land_value.v1",
        },
      ],
      events: [],
      artifacts: {
        acquisition_guidance: {
          recommended_action: "offer_range",
          basis: "county_reconciled_land_signal",
          land_signal_strength: "county_reconciled",
          market_signal_verification_status: "county_reconciled",
          recommendation_confidence: "medium",
          requires_market_signal_validation: false,
        },
        comp_support_summary: {
          status: "warning",
          reason: "offer guidance depends on county-reconciled public listing support rather than direct land comps",
          recommendation_confidence: "medium",
          recommended_action: "offer_range",
          requires_market_signal_validation: false,
          land_signal_tier: "none",
          public_listing_signal_tier: "county_reconciled",
        },
        comp_search_strategy: {
          selected_months: 24,
          selected_reason: "direct_land_comp_signal",
          attempts: [
            {
              months: 12,
              radius_miles: 3,
              land_comp_count: 0,
              unit_comp_count: 2,
              estimated_land_value: 0,
              adv_per_unit: 446250,
              confidence: 0.55,
              selected: false,
              selection_reason: "qualified_exit_comp_fallback_candidate",
            },
            {
              months: 24,
              radius_miles: 5,
              land_comp_count: 1,
              unit_comp_count: 2,
              estimated_land_value: 154391.78,
              adv_per_unit: 505000,
              confidence: 0.55,
              selected: true,
              selection_reason: "direct_land_comp_signal",
            },
          ],
        },
      },
      pipeline_stages: [
        {
          key: "site_identification",
          title: "Address and parcel",
          status: "completed",
          summary: "171 NE 209th Ter, Miami, FL 33179 (30-2206-013-0310)",
          artifact_keys: ["geocode", "property_record"],
        },
        {
          key: "comparables",
          title: "Comparable sales",
          status: "completed",
          summary: "4 sales comps, 2 unit comps",
          artifact_keys: ["comps"],
        },
      ],
    });

    getHarnessRunEventsMock.mockResolvedValue({
      run_id: "run_fixture_detail_001",
      events: [
        { event_id: "evt_1", type: "run.created", source: "harness", status: "completed" },
        { event_id: "evt_2", type: "verification.completed", source: "verifier", status: "completed" },
        { event_id: "evt_3", type: "run.completed", source: "harness", status: "completed" },
      ],
    });

    getHarnessRunVerificationMock.mockResolvedValue({
      verification_id: "ver_1",
      run_id: "run_fixture_detail_001",
      report_id: "report_fixture_detail_001",
      status: "passed_with_warnings",
      checks: {
        evidence_complete: "passed",
        math_recomputed: "passed",
        municipal_verification: "warning",
        comp_support: "warning",
      },
      missing_evidence: [],
      stale_evidence: ["miami_21_section_freshness"],
      unsupported_claims: [],
      mock_or_fixture_blockers: [],
    });

    render(
      <HarnessRunDetail
        runId="run_fixture_detail_001"
        projectId="project_fixture_001"
        siteId="site_fixture_001"
      />,
    );

    expect(await screen.findByText("Harness analysis detail")).toBeInTheDocument();

    await waitFor(() => {
      expect(getHarnessRunMock).toHaveBeenCalledWith("run_fixture_detail_001");
      expect(getHarnessRunEventsMock).toHaveBeenCalledWith("run_fixture_detail_001");
      expect(getHarnessRunVerificationMock).toHaveBeenCalledWith("run_fixture_detail_001");
    });

    expect(screen.getByText("run_fixture_detail_001")).toBeInTheDocument();
    expect(screen.getAllByText("passed_with_warnings")[0]).toBeInTheDocument();
    expect(screen.getByText("Comparable sales support a land value range for this site.")).toBeInTheDocument();
    expect(screen.getByText("Miami-Dade comparable sale")).toBeInTheDocument();
    expect(screen.getByText("residual land value")).toBeInTheDocument();
    expect(screen.getByText("municipal verification")).toBeInTheDocument();
    expect(screen.getByText("run.completed")).toBeInTheDocument();
    expect(screen.getByText("Stale evidence: miami_21_section_freshness")).toBeInTheDocument();
    expect(screen.getByText("Pipeline trace")).toBeInTheDocument();
    expect(screen.getByText("Address and parcel")).toBeInTheDocument();
    expect(screen.getByText("4 sales comps, 2 unit comps")).toBeInTheDocument();
    expect(screen.getAllByText("county reconciled")).toHaveLength(4);
    expect(screen.getAllByText("medium confidence")).toHaveLength(2);
    expect(screen.getByText("county reconciled land signal")).toBeInTheDocument();
    expect(screen.getByText("Validation")).toBeInTheDocument();
    expect(screen.getByText("Not required")).toBeInTheDocument();
    expect(screen.getByText("Comparable sales strategy")).toBeInTheDocument();
    expect(screen.getByText("Selected")).toBeInTheDocument();
    expect(screen.getAllByText("direct land comp signal")).toHaveLength(2);
    expect(screen.getByText("qualified exit comp fallback candidate")).toBeInTheDocument();
    expect(screen.getByText("24 mo • 5.0 mi")).toBeInTheDocument();
    expect(screen.getByText("$154,391.78")).toBeInTheDocument();
    expect(screen.getByText("Comparable support")).toBeInTheDocument();
    expect(screen.getByText("Support reason")).toBeInTheDocument();
    expect(screen.getByText("offer guidance depends on county-reconciled public listing support rather than direct land comps")).toBeInTheDocument();
    expect(screen.getByText("Recommended action")).toBeInTheDocument();
    expect(screen.getByText("Land signal tier")).toBeInTheDocument();
    expect(screen.getByText("Public listing tier")).toBeInTheDocument();
    expect(screen.getByText("comp support")).toBeInTheDocument();
  });
});
