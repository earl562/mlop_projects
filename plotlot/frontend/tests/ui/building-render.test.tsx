import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BuildingRenderViewer from "../../src/components/BuildingRenderViewer";

const renderBuildingMock = vi.fn();

vi.mock("../../src/lib/api", () => ({
  renderBuilding: (...args: unknown[]) => renderBuildingMock(...args),
}));

const props = {
  lotWidthFt: 70,
  lotDepthFt: 100,
  setbackFrontFt: 20,
  setbackSideFt: 5,
  setbackRearFt: 20,
  maxHeightFt: 35,
  maxStories: 2,
  propertyType: "single_family",
  maxUnits: 1,
  zoningDistrict: "RS5",
  municipality: "Miramar",
};

describe("BuildingRenderViewer", () => {
  beforeEach(() => {
    renderBuildingMock.mockReset();
  });

  it("does not call the optional AI renderer until the user requests it", async () => {
    const user = userEvent.setup();
    renderBuildingMock.mockResolvedValue({
      views: [],
      cached: false,
      generation_time_ms: 1,
    });

    render(<BuildingRenderViewer {...props} />);

    expect(renderBuildingMock).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /generate ai views/i }));

    expect(renderBuildingMock).toHaveBeenCalledTimes(1);
  });

  it("shows renderer failures as an optional degraded state", async () => {
    const user = userEvent.setup();
    renderBuildingMock.mockRejectedValue(new Error("AI rendering is not configured"));

    render(<BuildingRenderViewer {...props} />);
    await user.click(screen.getByRole("button", { name: /generate ai views/i }));

    expect(await screen.findByText("AI rendering is not configured")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
