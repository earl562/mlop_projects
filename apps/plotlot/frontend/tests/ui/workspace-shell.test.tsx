/* eslint-disable @next/next/no-img-element */
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("framer-motion", async () => {
  const React = await import("react");
  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    motion: new Proxy(
      {},
      {
        get: (_target, tag: string) => {
          return ({ children, ...props }: Record<string, unknown>) =>
            React.createElement(tag, props, children as React.ReactNode);
        },
      },
    ),
  };
});

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("next/image", () => ({
  default: ({ alt, ...props }: React.ImgHTMLAttributes<HTMLImageElement>) => <img alt={alt} {...props} />,
}));

vi.mock("../../src/lib/motion", () => ({
  staggerContainer: {},
  staggerItem: {},
  fadeUp: {},
  springGentle: {},
}));

vi.mock("../../src/lib/api", () => ({
  streamAnalysis: vi.fn(),
  streamChat: vi.fn(),
  saveAnalysis: vi.fn(),
}));

vi.mock("../../src/lib/sessions", () => ({
  createSession: vi.fn(() => ({ id: "session-1" })),
  getSession: vi.fn(() => null),
  updateSession: vi.fn(),
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
    inputRef?: React.Ref<HTMLInputElement>;
    disabled?: boolean;
  }) {
    return (
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        data-testid="lookup-input"
      />
    );
  },
}));

vi.mock("../../src/components/DocumentCanvas", () => ({
  default: function MockDocumentCanvas() {
    return <div data-testid="mock-document-canvas" />;
  },
}));

vi.mock("../../src/components/ThinkingIndicator", () => ({
  default: function MockThinkingIndicator() {
    return <div data-testid="mock-thinking-indicator" />;
  },
}));

vi.mock("../../src/components/ErrorBoundary", () => ({
  default: function MockErrorBoundary({ children }: { children: React.ReactNode }) {
    return <>{children}</>;
  },
}));

vi.mock("../../src/components/DealTypeSelector", () => ({
  default: function MockDealTypeSelector() {
    return <div data-testid="deal-type-selector" />;
  },
}));

vi.mock("../../src/components/PipelineApproval", () => ({
  PIPELINE_STEPS: [
    { key: "search", label: "Zoning Search", description: "Search ordinance database", required: true },
    { key: "analysis", label: "AI Analysis", description: "Extract standards", required: true },
    { key: "calculation", label: "Density Calculation", description: "Compute max units", required: false },
    { key: "comps", label: "Comparable Sales", description: "Find land sales", required: false },
    { key: "proforma", label: "Pro Forma", description: "Residual valuation", required: false },
  ],
  default: function MockPipelineApproval() {
    return <div data-testid="pipeline-approval-card" />;
  },
}));

vi.mock("../../src/components/AnalysisStream", () => ({
  default: function MockAnalysisStream() {
    return <div data-testid="pipeline-stepper" />;
  },
}));

vi.mock("../../src/components/TabbedReport", () => ({
  default: function MockTabbedReport() {
    return <div data-testid="report-root">Report</div>;
  },
}));

vi.mock("../../src/components/ZoningReport", () => ({
  default: function MockZoningReport() {
    return <div data-testid="report-root">Report</div>;
  },
}));

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  localStorage.clear();
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

import WorkspacePage from "../../src/app/workspace/page";
import { streamAnalysis } from "../../src/lib/api";

describe("Workspace shell", () => {
  it("shows the current address-first lookup welcome shell on first entry", () => {
    render(<WorkspacePage />);

    expect(screen.getByText("Analyze any property in the US")).toBeInTheDocument();
    expect(screen.getByTestId("lookup-input")).toHaveAttribute(
      "placeholder",
      "Enter a property address...",
    );
    expect(screen.getByRole("button", { name: "Lookup" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Agent" })).toBeInTheDocument();
    expect(screen.getByTestId("send-button")).toBeDisabled();
    expect(screen.queryByText("Analyze a Site")).not.toBeInTheDocument();
    expect(screen.queryByText("Open Data Layers")).not.toBeInTheDocument();
    expect(screen.queryByText("Municode Live")).not.toBeInTheDocument();
    expect(screen.queryByText("Generate LOI")).not.toBeInTheDocument();
    expect(screen.queryByText("Search Comps")).not.toBeInTheDocument();
    expect(screen.queryByText("Run Pro Forma")).not.toBeInTheDocument();
    expect(screen.queryByText("Source Land Leads")).not.toBeInTheDocument();
    expect(
      screen.getByText("PlotLot analyzes zoning, density, comps & pro forma for any US property"),
    ).toBeInTheDocument();

    expect(screen.queryByTestId("workspace-status-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("workspace-plan-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("workspace-evidence-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("workspace-report-card")).not.toBeInTheDocument();
  });

  it("starts lookup analysis directly after an address without deal-type cards", async () => {
    vi.mocked(streamAnalysis).mockResolvedValue(undefined);
    render(<WorkspacePage />);

    const address = "171 NE 209th Ter Miami FL";
    fireEvent.change(screen.getByTestId("lookup-input"), {
      target: { value: address },
    });
    fireEvent.click(screen.getByTestId("send-button"));

    await waitFor(() => {
      expect(streamAnalysis).toHaveBeenCalledWith(
        expect.objectContaining({
          address,
          dealType: "land_deal",
        }),
        expect.any(Function),
        expect.any(Function),
        expect.any(Function),
        expect.any(Function),
        expect.any(Function),
      );
    });

    expect(screen.queryByText("What type of deal are you evaluating?")).not.toBeInTheDocument();
    expect(screen.queryByTestId("deal-type-selector")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pipeline-approval-card")).not.toBeInTheDocument();
  });
});
