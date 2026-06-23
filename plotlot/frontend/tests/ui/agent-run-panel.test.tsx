import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentRunPanel from "../../src/components/AgentRunPanel";
import {
  evalPayload,
  jsonResponse,
  reportWithSnapshot,
  reportWithoutSnapshot,
} from "./agent-run-panel.fixtures";
import { tracePayload } from "./agent-run-trace.fixtures";

describe("AgentRunPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("refuses to start an agent run without a recorded lookup snapshot", () => {
    render(<AgentRunPanel report={reportWithoutSnapshot()} />);

    expect(screen.getByTestId("agent-run-panel")).toBeInTheDocument();
    expect(screen.getByText("No lookup snapshot")).toBeInTheDocument();
    expect(screen.queryByTestId("agent-run-snapshot-fields")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Run harness eval/i })).toBeDisabled();
  });

  it("starts an agent run, evaluates it, and renders the release gate summary", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/agent-runs")) {
        expect(init?.headers).toMatchObject({ "Content-Type": "application/json" });
        return jsonResponse({
          run_id: "run_frontend_agent",
          lookup_snapshot_id: "lookup_frontend",
          workspace_id: "frontend_workspace",
          status: "requires_review",
          evidence_ids: ["evidence-parcel", "evidence-zoning"],
          warnings: [],
          ready_for_synthesis: false,
        });
      }
      if (url.endsWith("/api/v1/agent-runs/run_frontend_agent/evals?workspace_id=frontend_workspace")) {
        expect(init).toMatchObject({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
        return jsonResponse(evalPayload());
      }
      if (
        url.endsWith(
          "/api/v1/agent-runs/run_frontend_agent/improvement-summary?workspace_id=frontend_workspace",
        )
      ) {
        return jsonResponse({
          current: evalPayload(),
          previous: null,
          baseline_status: "missing",
          improvement_status: "no_baseline",
          release_blocked: false,
          deltas: {},
          improved_metric_keys: [],
          regressed_metric_keys: [],
        });
      }
      if (url.endsWith("/api/v1/agent-runs/run_frontend_agent/trace?workspace_id=frontend_workspace")) {
        return jsonResponse(tracePayload());
      }
      throw new Error(`Unexpected URL ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AgentRunPanel report={reportWithSnapshot()} />);

    expect(screen.getByTestId("agent-run-snapshot-fields")).toBeInTheDocument();
    expect(screen.getByText("APN")).toBeInTheDocument();
    expect(screen.getAllByText("evidence-parcel").length).toBeGreaterThan(0);
    expect(screen.getByText("stale")).toBeInTheDocument();
    expect(screen.getByText("Official parcel appraiser")).toBeInTheDocument();
    expect(screen.getByText("max_units=2")).toBeInTheDocument();
    expect(screen.getByText("human review")).toBeInTheDocument();
    expect(screen.getByText("Confirm adopted parking table.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Run harness eval/i }));

    expect(await screen.findByText("Release gate clear")).toBeInTheDocument();
    expect(screen.getByText("Replay trace")).toBeInTheDocument();
    expect(screen.getByText("Replay ready")).toBeInTheDocument();
    expect(screen.getByText("report_frontend_agent")).toBeInTheDocument();
    expect(screen.getByText("2 packets")).toBeInTheDocument();
    expect(screen.getByText("2 retrievals")).toBeInTheDocument();
    expect(screen.getByText("Source retrievals")).toBeInTheDocument();
    expect(screen.getAllByText("Recorded zoning map packet")).toHaveLength(2);
    expect(screen.getByText("City of Miramar")).toBeInTheDocument();
    expect(screen.getByText("raw://zoning/evidence-zoning")).toBeInTheDocument();
    expect(screen.getAllByText("official_zoning_map")).toHaveLength(2);
    expect(screen.getByText("zoning-map-v2")).toBeInTheDocument();
    expect(screen.getAllByText("schema_stable")).toHaveLength(2);
    expect(screen.getByText("Report claims")).toBeInTheDocument();
    expect(screen.getByText("Evidence Scope")).toBeInTheDocument();
    expect(screen.getByText("Deterministic Calculations")).toBeInTheDocument();
    expect(
      screen.getByText("Deterministic calculation output from underwriting_analyst: max_units=2."),
    ).toBeInTheDocument();
    expect(screen.getByText("Opportunity hypotheses")).toBeInTheDocument();
    expect(screen.getByText("opportunity.by_right_capacity")).toBeInTheDocument();
    expect(
      screen.getByText("Test by-right development capacity using recorded zoning evidence."),
    ).toBeInTheDocument();
    expect(screen.getByText("hypothesis")).toBeInTheDocument();
    expect(
      screen.getByText("Developer value may exist if the by-right unit yield exceeds the current use."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Confirm market rents, costs, financing terms, and any missing dimensional standards before underwriting value.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Artifact assumptions")).toBeInTheDocument();
    expect(screen.getByText("requires_human_review")).toBeInTheDocument();
    expect(screen.getByText("agent_run.open_question")).toBeInTheDocument();
    expect(
      screen.getByText("standards.setbacks.front is unknown; retrieve authoritative evidence before use."),
    ).toBeInTheDocument();
    expect(screen.getByText("Evidence")).toBeInTheDocument();
    expect(screen.getByText("Opportunity")).toBeInTheDocument();
    expect(screen.getAllByText("Assumptions")).toHaveLength(2);
    expect(screen.getAllByText("100%")).toHaveLength(5);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("surfaces blocked release gates with regressed metric keys", async () => {
    const user = userEvent.setup();
    const blockedEval = {
      ...evalPayload(),
      status: "failed",
      metrics: {
        ...evalPayload().metrics,
        artifact_citation_coverage: 0.5,
        unsupported_claim_rate: 0.25,
      },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/api/v1/agent-runs")) {
        expect(init?.headers).toMatchObject({ "Content-Type": "application/json" });
        return jsonResponse({
          run_id: "run_frontend_agent",
          lookup_snapshot_id: "lookup_frontend",
          workspace_id: "frontend_workspace",
          status: "requires_review",
          evidence_ids: ["evidence-parcel", "evidence-zoning"],
          warnings: [],
          ready_for_synthesis: false,
        });
      }
      if (url.endsWith("/api/v1/agent-runs/run_frontend_agent/evals?workspace_id=frontend_workspace")) {
        expect(init).toMatchObject({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
        return jsonResponse(blockedEval);
      }
      if (
        url.endsWith(
          "/api/v1/agent-runs/run_frontend_agent/improvement-summary?workspace_id=frontend_workspace",
        )
      ) {
        return jsonResponse({
          current: blockedEval,
          previous: evalPayload(),
          baseline_status: "available",
          improvement_status: "regressed",
          release_blocked: true,
          deltas: {
            artifact_citation_coverage: -0.5,
            unsupported_claim_rate: 0.25,
          },
          improved_metric_keys: [],
          regressed_metric_keys: ["artifact_citation_coverage", "unsupported_claim_rate"],
        });
      }
      if (url.endsWith("/api/v1/agent-runs/run_frontend_agent/trace?workspace_id=frontend_workspace")) {
        return jsonResponse({
          ...tracePayload(),
          latest_eval: {
            ...tracePayload().latest_eval,
            status: "failed",
          },
          improvement: {
            baseline_status: "available",
            improvement_status: "regressed",
            release_blocked: true,
            improved_metric_keys: [],
            regressed_metric_keys: ["artifact_citation_coverage", "unsupported_claim_rate"],
            improvement_log: [
              {
                source: "agent_run_eval",
                researched_input: "run_frontend_agent",
                changed_rule: "eval_metric:artifact_citation_coverage",
                metric: "artifact_citation_coverage",
                direction: "regressed",
                reason: "baseline_delta",
                affected_golden_cases: ["gold_frontend_agent"],
                before_score: 1,
                after_score: 0.5,
                delta: -0.5,
                gate_blocking: true,
                unresolved_risk: "agent_run_regression_requires_review",
              },
            ],
          },
        });
      }
      throw new Error(`Unexpected URL ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AgentRunPanel report={reportWithSnapshot()} />);

    await user.click(screen.getByRole("button", { name: /Run harness eval/i }));

    expect(await screen.findByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText("Release blocked")).toBeInTheDocument();
    expect(screen.getByText("Regressed")).toBeInTheDocument();
    expect(screen.getByText("artifact_citation_coverage")).toBeInTheDocument();
    expect(screen.getByText("unsupported_claim_rate")).toBeInTheDocument();
  });
});
