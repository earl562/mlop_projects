import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import DealTypeSelector from "../../src/components/DealTypeSelector";
import PipelineApproval from "../../src/components/PipelineApproval";
import AnalysisStream from "../../src/components/AnalysisStream";

describe("PlotLot testing standard UI contract", () => {
  it("exposes canonical deal type test ids", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();

    render(<DealTypeSelector onSelect={onSelect} />);

    expect(screen.getByTestId("deal-type-selector")).toBeInTheDocument();
    await user.click(screen.getByTestId("deal-type-land"));
    expect(onSelect).toHaveBeenCalledWith("land_deal");

    expect(screen.getByTestId("deal-type-wholesale")).toBeInTheDocument();
    expect(screen.getByTestId("deal-type-creative-finance")).toBeInTheDocument();
    expect(screen.getByTestId("deal-type-hybrid")).toBeInTheDocument();
  });

  it("computes optional pipeline skips behind the canonical approval controls", async () => {
    const user = userEvent.setup();
    const onApprove = vi.fn();

    render(
      <PipelineApproval
        address="7940 Plantation Blvd, Miramar, FL 33023"
        dealType="land_deal"
        onApprove={onApprove}
        onCancel={() => {}}
      />,
    );

    expect(screen.getByTestId("pipeline-approval-card")).toBeInTheDocument();
    await user.click(screen.getByLabelText(/Density Calculation/i));
    await user.click(screen.getByTestId("pipeline-run-button"));

    expect(onApprove).toHaveBeenCalledWith(["calculation"]);
  });

  it("marks the current pipeline step with canonical machine hooks", () => {
    render(
      <AnalysisStream
        steps={[
          { step: "geocoding", message: "Resolving address...", complete: false },
          {
            step: "property",
            message: "Loaded property record",
            complete: true,
            resolved_address: "7940 Plantation Blvd, Miramar, FL 33023",
          },
        ]}
        error={null}
      />,
    );

    expect(screen.getByTestId("pipeline-stepper")).toBeInTheDocument();
    expect(screen.getByTestId("pipeline-step-geocoding")).toBeInTheDocument();
    expect(screen.getByTestId("pipeline-step-property")).toBeInTheDocument();
    expect(screen.getByTestId("pipeline-step-current")).toHaveTextContent(
      "Geocoding",
    );
  });
});
