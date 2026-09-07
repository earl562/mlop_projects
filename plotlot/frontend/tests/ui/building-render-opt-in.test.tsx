import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BuildingRenderViewer from "../../src/components/BuildingRenderViewer";

const props = {
  lotWidthFt: 100,
  lotDepthFt: 100,
  setbackFrontFt: 20,
  setbackSideFt: 10,
  setbackRearFt: 20,
  maxHeightFt: 30,
  maxStories: 2,
  zoningDistrict: "TEST-ZONE",
  municipality: "Synthetic city",
} satisfies ComponentProps<typeof BuildingRenderViewer>;

const result = {
  views: [
    { view: "front", image_base64: "c3ludGhldGlj", prompt_used: "Synthetic fixture" },
    { view: "aerial", image_base64: "c3ludGhldGlj", prompt_used: "Synthetic fixture" },
  ],
  cached: false,
  generation_time_ms: 10,
};

afterEach(() => vi.restoreAllMocks());

describe("Optional building illustrations", () => {
  it("makes no image request when a report viewer mounts or its inputs change", () => {
    // Given a configured transport and a drawable envelope.
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(result));
    const viewer = render(<BuildingRenderViewer {...props} />);

    // When the property input changes without a generation action.
    viewer.rerender(<BuildingRenderViewer {...props} municipality="Another synthetic city" />);

    // Then merely reviewing a report costs no image calls.
    expect(request).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Generate AI views" })).toBeEnabled();
  });

  it("generates only on request and switches returned views without another request", async () => {
    // Given an idle viewer and a successful provider response.
    const user = userEvent.setup();
    const request = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json(result));
    render(<BuildingRenderViewer {...props} />);

    // When the analyst requests generation then selects an existing view.
    await user.click(screen.getByRole("button", { name: "Generate AI views" }));
    await screen.findByRole("img", { name: /front view/i });
    await user.click(screen.getByRole("button", { name: "Aerial" }));

    // Then one explicit request supplies both selectable views.
    expect(request).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("img", { name: /aerial view/i })).toBeVisible();
  });

  it("waits for an explicit retry after the provider rejects generation", async () => {
    // Given a provider that is unavailable on the first request.
    const user = userEvent.setup();
    const request = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json({ detail: "Image provider unavailable" }, { status: 503 }))
      .mockResolvedValueOnce(Response.json(result));
    render(<BuildingRenderViewer {...props} />);

    // When the analyst starts generation and sees its failure.
    await user.click(screen.getByRole("button", { name: "Generate AI views" }));

    // Then no retry occurs without another action.
    expect(await screen.findByRole("alert")).toHaveTextContent("Image provider unavailable");
    expect(request).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("img", { name: /front view/i })).toBeVisible();
    expect(request).toHaveBeenCalledTimes(2);
  });

  it("does not attach a late illustration to a changed property", async () => {
    // Given a requested illustration that is still in flight.
    const user = userEvent.setup();
    let resolveResponse: (response: Response) => void = () => {
      throw new Error("Expected the illustration request to start before resolving it");
    };
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(() => (
      new Promise<Response>((resolve) => { resolveResponse = resolve; })
    ));
    const viewer = render(<BuildingRenderViewer {...props} />);
    await user.click(screen.getByRole("button", { name: "Generate AI views" }));
    expect(screen.getByRole("status")).toBeVisible();

    // When a different property replaces it before the old response arrives.
    viewer.rerender(<BuildingRenderViewer {...props} lotWidthFt={120} />);
    await act(async () => resolveResponse(Response.json(result)));

    // Then the new envelope remains idle without old imagery or another request.
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate AI views" })).toBeEnabled();
    expect(request).toHaveBeenCalledTimes(1);
  });
});
