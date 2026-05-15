import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AnalysisError } from "../../src/lib/api";

const streamAnalysisMock = vi.fn();
const saveAnalysisMock = vi.fn();

vi.mock("../../src/lib/api", () => ({
  streamAnalysis: (...args: unknown[]) => streamAnalysisMock(...args),
  saveAnalysis: (...args: unknown[]) => saveAnalysisMock(...args),
}));

vi.mock("../../src/components/AddressAutocomplete", () => ({
  default: function MockAddressAutocomplete({
    value,
    onChange,
    placeholder,
    inputRef,
    disabled,
  }: {
    value: string;
    onChange: (value: string) => void;
    placeholder: string;
    inputRef: React.Ref<HTMLInputElement>;
    disabled?: boolean;
  }) {
    return (
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
      />
    );
  },
}));

vi.mock("../../src/components/ModeToggle", () => ({
  default: function MockModeToggle() {
    return <div data-testid="mock-mode-toggle" />;
  },
}));

vi.mock("../../src/components/AnalysisStream", () => ({
  default: function MockAnalysisStream() {
    return <div data-testid="mock-analysis-stream" />;
  },
}));

vi.mock("../../src/components/ZoningReport", () => ({
  default: function MockZoningReport() {
    return <div data-testid="mock-zoning-report" />;
  },
}));

import QuickLookup from "../../src/components/QuickLookup";

describe("QuickLookup degraded retry UX", () => {
  beforeEach(() => {
    streamAnalysisMock.mockReset();
    saveAnalysisMock.mockReset();
  });

  it("shows retry for backend-unavailable errors and reruns analysis", async () => {
    const user = userEvent.setup();
    let errorCallback: ((error: AnalysisError) => void) | undefined;

    streamAnalysisMock.mockImplementation(
      async (
        options: { address: string },
        _onStatus: unknown,
        _onResult: unknown,
        onError: (error: AnalysisError) => void,
      ) => {
        errorCallback = onError;
        onError({
          detail:
            "Analysis is temporarily unavailable because the data backend is offline. Please try again shortly.",
          errorType: "backend_unavailable",
        });
      },
    );

    render(<QuickLookup />);

    await user.type(
      screen.getByPlaceholderText("Enter a property address..."),
      "7940 Plantation Blvd, Miramar, FL 33023",
    );
    await user.click(screen.getByRole("button", { name: "Analyze" }));

    await screen.findByText(/data backend is offline/i);
    const retryButton = screen.getByRole("button", { name: "Retry" });
    expect(retryButton).toBeInTheDocument();
    expect(streamAnalysisMock).toHaveBeenCalledTimes(1);

    await user.click(retryButton);

    await waitFor(() => {
      expect(streamAnalysisMock).toHaveBeenCalledTimes(2);
    });
    expect(errorCallback).toBeDefined();
  });
});
