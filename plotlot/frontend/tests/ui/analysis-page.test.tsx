import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../src/components/HarnessRunDetail", () => ({
  default: ({
    runId,
    projectId,
    siteId,
  }: {
    runId: string;
    projectId: string;
    siteId: string;
  }) => (
    <div data-testid="harness-run-detail">
      {runId}:{projectId}:{siteId}
    </div>
  ),
}));

import AnalysisPage from "../../src/app/(workspace)/projects/[projectId]/sites/[siteId]/analyses/[analysisId]/page";

describe("AnalysisPage", () => {
  it("keeps non-harness analysis ids on the workspace analysis shell", async () => {
    const page = await AnalysisPage({
      params: Promise.resolve({
        projectId: "project_1",
        siteId: "site_1",
        analysisId: "analysis_1",
      }),
    });

    render(page);

    expect(screen.getByText("Analysis workspace")).toBeInTheDocument();
    expect(screen.getByText(/workspace analysis record/i)).toBeInTheDocument();
    expect(screen.queryByTestId("harness-run-detail")).not.toBeInTheDocument();
  });

  it("routes harness run ids into persisted harness detail", async () => {
    const page = await AnalysisPage({
      params: Promise.resolve({
        projectId: "project_1",
        siteId: "site_1",
        analysisId: "run_fixture_detail_001",
      }),
    });

    render(page);

    expect(screen.getByTestId("harness-run-detail")).toHaveTextContent(
      "run_fixture_detail_001:project_1:site_1",
    );
  });
});
