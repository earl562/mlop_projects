import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const createAnalysisLifecycleRecordMock = vi.fn();
const runLifecycleAwareHarnessAnalysisMock = vi.fn();

vi.mock("../../src/lib/harness-analysis-lifecycle", () => ({
  createAnalysisLifecycleRecord: (...args: unknown[]) => createAnalysisLifecycleRecordMock(...args),
  runLifecycleAwareHarnessAnalysis: (...args: unknown[]) => runLifecycleAwareHarnessAnalysisMock(...args),
}));

import HarnessAnalystWorkbench from "../../src/components/HarnessAnalystWorkbench";

describe("HarnessAnalystWorkbench", () => {
  beforeEach(() => {
    createAnalysisLifecycleRecordMock.mockReset();
    runLifecycleAwareHarnessAnalysisMock.mockReset();
  });

  it("submits a shared harness run and renders the returned run summary", async () => {
    const user = userEvent.setup();
    runLifecycleAwareHarnessAnalysisMock.mockResolvedValue({
      run_id: "run_fixture_frontend_001",
      analysis_run_id: "run_fixture_frontend_001",
      analysis_type: "acquisition_memo",
      status: "completed",
      events_url: "/api/v1/harness/runs/run_fixture_frontend_001/events",
      report_id: "report_fixture_frontend_001",
      evidence_ids: ["ev_1", "ev_2"],
      verification_status: "passed_with_warnings",
      source_mode: "live",
      preliminary: true,
      claims: [
        {
          claim_id: "claim_1",
          claim_type: "comp_value_signal",
          claim_text: "Comparable sales indicate a supportable range.",
          confidence: 0.74,
          source_mode: "live",
        },
      ],
      evidence_items: [
        {
          evidence_id: "ev_1",
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
      events: [
        { event_id: "evt_1", type: "run.created", source: "harness", status: "completed" },
        { event_id: "evt_2", type: "run.completed", source: "harness", status: "completed" },
      ],
      artifacts: {
        acquisition_guidance: {
          recommended_action: "offer_range",
          basis: "residual_and_market_signal",
          land_signal_strength: "direct",
          market_signal_verification_status: "direct_verified",
          recommendation_confidence: "high",
          requires_market_signal_validation: false,
        },
        comp_support_summary: {
          status: "passed",
          reason: "direct land comps or county-reconciled support available",
          recommendation_confidence: "high",
          recommended_action: "offer_range",
          requires_market_signal_validation: false,
          land_signal_tier: "direct",
          public_listing_signal_tier: "none",
        },
        comp_search_strategy: {
          selected_months: 24,
          selected_reason: "direct_land_comp_signal",
        },
      },
      pipeline_stages: [],
    });

    render(<HarnessAnalystWorkbench />);

    await user.clear(screen.getByLabelText("Address"));
    await user.type(screen.getByLabelText("Address"), "171 NE 209th Ter, Miami, FL 33179");
    await user.click(screen.getByRole("button", { name: "Run harness" }));

    await waitFor(() => {
      expect(runLifecycleAwareHarnessAnalysisMock).toHaveBeenCalledWith(
        expect.objectContaining({
          address: "171 NE 209th Ter, Miami, FL 33179",
          analysisType: "acquisition_memo",
          sourceMode: "live",
        }),
      );
    });

    expect(await screen.findAllByText("run_fixture_frontend_001")).toHaveLength(2);
    expect(screen.getByText("Analysis run ID")).toBeInTheDocument();
    expect(screen.getByText("passed_with_warnings")).toBeInTheDocument();
    expect(screen.getByText("Comparable sales indicate a supportable range.")).toBeInTheDocument();
    expect(screen.getByText("19646 NE 14 CT • contextual • fresh")).toBeInTheDocument();
    expect(screen.getByText("Comp search strategy")).toBeInTheDocument();
    expect(screen.getByText("direct land comp signal")).toBeInTheDocument();
    expect(screen.getByText(/selected window:\s*24 months/i)).toBeInTheDocument();
    expect(screen.getByText("Market signal")).toBeInTheDocument();
    expect(screen.getByText("direct verified")).toBeInTheDocument();
    expect(screen.getAllByText("high confidence")).toHaveLength(2);
    expect(screen.getAllByText("Validation: Not required")).toHaveLength(2);
    expect(screen.getByText("Comp support")).toBeInTheDocument();
    expect(screen.getByText("Reason: direct land comps or county-reconciled support available")).toBeInTheDocument();
    expect(screen.getByText("Land tier: direct")).toBeInTheDocument();
    expect(screen.getByText("Public listing tier: none")).toBeInTheDocument();
  });

  it("creates a durable analysis record before running when lifecycle tracking is enabled", async () => {
    const user = userEvent.setup();
    createAnalysisLifecycleRecordMock.mockResolvedValue({
      id: "analysis_fixture_001",
      workspace_id: "ws_fixture",
      project_id: "prj_fixture",
      site_id: "site_fixture",
      name: "Shared harness analysis",
      skill_name: "acquisition_memo",
      status: "active",
      metadata_json: {},
    });
    runLifecycleAwareHarnessAnalysisMock.mockResolvedValue({
      run_id: "run_fixture_frontend_002",
      analysis_run_id: "run_fixture_frontend_002",
      workspace_id: "ws_fixture",
      project_id: "prj_fixture",
      site_id: "site_fixture",
      analysis_id: "analysis_fixture_001",
      analysis_type: "acquisition_memo",
      status: "completed",
      events_url: "/api/v1/harness/runs/run_fixture_frontend_002/events",
      report_id: "report_fixture_frontend_002",
      evidence_ids: [],
      verification_status: "passed_with_warnings",
      source_mode: "live",
      preliminary: true,
      claims: [],
      evidence_items: [],
      calculations: [],
      events: [],
      artifacts: {},
      pipeline_stages: [],
    });

    render(<HarnessAnalystWorkbench />);

    await user.click(screen.getByRole("button", { name: "Lifecycle off" }));
    await user.type(screen.getByLabelText("Workspace ID"), "ws_fixture");
    await user.type(screen.getByLabelText("Project ID"), "prj_fixture");
    await user.type(screen.getByLabelText("Site ID"), "site_fixture");
    await user.click(screen.getByRole("button", { name: "Run harness" }));

    await waitFor(() => {
      expect(createAnalysisLifecycleRecordMock).toHaveBeenCalledWith(
        expect.objectContaining({
          workspaceId: "ws_fixture",
          projectId: "prj_fixture",
          siteId: "site_fixture",
          skillName: "acquisition_memo",
        }),
      );
      expect(runLifecycleAwareHarnessAnalysisMock).toHaveBeenCalledWith(
        expect.objectContaining({
          workspaceId: "ws_fixture",
          projectId: "prj_fixture",
          siteId: "site_fixture",
          analysisId: "analysis_fixture_001",
        }),
      );
    });

    expect(screen.queryByText("Comp search strategy")).not.toBeInTheDocument();
  });
});
