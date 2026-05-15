import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("../../src/lib/api", () => ({
  streamChat: vi.fn(),
}));

import AnalyzePage from "../../src/app/analyze/page";

describe("Analyze console shell", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  it("renders explicit status, plan, evidence, and next-action cards", async () => {
    render(<AnalyzePage />);

    expect(await screen.findByText("Land-use intelligence console.")).toBeInTheDocument();
    expect(screen.getByTestId("analyze-status-card")).toBeInTheDocument();
    expect(screen.getByTestId("analyze-plan-card")).toBeInTheDocument();
    expect(screen.getByTestId("analyze-evidence-card")).toBeInTheDocument();
    expect(screen.getByTestId("analyze-actions-card")).toBeInTheDocument();
    expect(screen.getByTestId("analyze-task-timeline-card")).toBeInTheDocument();
    expect(screen.getByText("Run state")).toBeInTheDocument();
    expect(screen.getByText("Consultant loop")).toBeInTheDocument();
    expect(screen.getByText("Task timeline")).toBeInTheDocument();
    expect(screen.getByText("Awaiting sources")).toBeInTheDocument();
    expect(screen.getByText("What to pressure-test next")).toBeInTheDocument();
  });
});
