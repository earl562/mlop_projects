import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import LookupReleaseGatePanel from "../../src/components/LookupReleaseGatePanel";
import {
  batchEvalPayload,
  blockedPayload,
  noHistoryPayload,
  passedPayload,
} from "./lookup-release-gate-panel.fixtures";

describe("LookupReleaseGatePanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("blocks release when no lookup-correctness eval history exists", async () => {
    // Given: the release-gate endpoint has no completed batch eval run.
    const fetchMock = vi.fn(async () => jsonResponse(noHistoryPayload()));
    vi.stubGlobal("fetch", fetchMock);

    // When: the workbench release-gate panel loads.
    render(<LookupReleaseGatePanel />);

    // Then: missing history is shown as an explicit blocker.
    expect(await screen.findByTestId("lookup-release-gate-empty")).toHaveTextContent(
      "No completed lookup-correctness eval run is available.",
    );
    expect(screen.getByTestId("lookup-release-gate-decision")).toHaveTextContent("Blocked");
    expect(screen.getByText("missing_eval_history")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/lookup-snapshots/evals/batch/release-gate?suite=lookup_correctness"),
      { cache: "no-store" },
    );
  });

  it("surfaces regression blockers, gate failures, and improvement-log entries", async () => {
    // Given: the latest lookup-correctness eval regressed against baseline.
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(blockedPayload())));

    // When: the panel renders the latest release-gate response.
    render(<LookupReleaseGatePanel />);

    // Then: release blockers and improvement evidence stay visible.
    expect(await screen.findByText("latest_eval_failed")).toBeInTheDocument();
    expect(screen.getByTestId("lookup-release-gate-decision")).toHaveTextContent("Blocked");
    expect(screen.getByText("pass_rate")).toBeInTheDocument();
    expect(screen.getByText(/current 50% \/ baseline 100%/)).toBeInTheDocument();
    expect(screen.getByText("eval_metric:pass_rate")).toBeInTheDocument();
    expect(screen.getByText("baseline_regression_requires_review")).toBeInTheDocument();
  });

  it("shows a clear gate when the latest lookup-correctness eval passed", async () => {
    // Given: the latest lookup-correctness eval is passing.
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(passedPayload())));

    // When: the panel loads the release-gate response.
    render(<LookupReleaseGatePanel />);

    // Then: the panel shows the pass decision and core eval metrics.
    expect(await screen.findByText("Latest eval passed: eval-pass.")).toBeInTheDocument();
    expect(screen.getByTestId("lookup-release-gate-decision")).toHaveTextContent("Passed");
    expect(screen.getAllByText("100%").length).toBeGreaterThan(1);
    expect(screen.queryByTestId("lookup-release-gate-blockers")).not.toBeInTheDocument();
  });

  it("refreshes the release-gate response on demand", async () => {
    // Given: the first response is blocked and the next response passes.
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(noHistoryPayload()))
      .mockResolvedValueOnce(jsonResponse(passedPayload()));
    vi.stubGlobal("fetch", fetchMock);

    // When: the user refreshes the release-gate panel.
    render(<LookupReleaseGatePanel />);
    expect(await screen.findByText("missing_eval_history")).toBeInTheDocument();
    await user.click(screen.getByTestId("lookup-release-gate-refresh"));

    // Then: the latest passed decision replaces the blocker.
    expect(await screen.findByText("Latest eval passed: eval-pass.")).toBeInTheDocument();
    expect(screen.getByTestId("lookup-release-gate-decision")).toHaveTextContent("Passed");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("runs a golden eval for the active lookup snapshot and refreshes the gate", async () => {
    // Given: the panel is tied to a recorded lookup snapshot with a matching golden case.
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(noHistoryPayload()))
      .mockResolvedValueOnce(jsonResponse(batchEvalPayload()))
      .mockResolvedValueOnce(jsonResponse(passedPayload()));
    vi.stubGlobal("fetch", fetchMock);

    // When: the user records a golden eval from the panel.
    render(
      <LookupReleaseGatePanel
        address="171 NE 209th Ter, Miami, FL 33179"
        snapshotId="ls_fixture"
      />,
    );
    expect(await screen.findByText("missing_eval_history")).toBeInTheDocument();
    await user.click(screen.getByTestId("lookup-release-gate-run"));

    // Then: the batch endpoint receives the snapshot-address pair and the gate refreshes.
    expect(await screen.findByTestId("lookup-release-gate-run-success")).toHaveTextContent(
      "Recorded 1 golden case eval.",
    );
    expect(await screen.findByText("Latest eval passed: eval-pass.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      expect.stringContaining("/api/v1/lookup-snapshots/evals/batch/golden"),
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          suite: "lookup_correctness",
          snapshots: [
            {
              snapshot_id: "ls_fixture",
              address: "171 NE 209th Ter, Miami, FL 33179",
            },
          ],
          use_latest_baseline: true,
        }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("surfaces a golden eval refusal without clearing the latest gate state", async () => {
    // Given: the backend refuses to synthesize a missing golden case.
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(noHistoryPayload()))
      .mockResolvedValueOnce(
        jsonResponse(
          { detail: "Lookup golden case not found: 1 Missing Golden Case Way" },
          422,
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    // When: the user tries to run the eval for an unmatched address.
    render(
      <LookupReleaseGatePanel
        address="1 Missing Golden Case Way"
        snapshotId="ls_missing_fixture"
      />,
    );
    expect(await screen.findByText("missing_eval_history")).toBeInTheDocument();
    await user.click(screen.getByTestId("lookup-release-gate-run"));

    // Then: the refusal is shown and no fake passing gate is fetched.
    expect(await screen.findByTestId("lookup-release-gate-run-error")).toHaveTextContent(
      "Lookup golden case not found: 1 Missing Golden Case Way",
    );
    expect(screen.getByTestId("lookup-release-gate-decision")).toHaveTextContent("Blocked");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

function jsonResponse(payload: object, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
