import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const previewDocumentMock = vi.fn();
const generateDocumentMock = vi.fn();

vi.mock("../../src/lib/api", () => ({
  previewDocument: (...args: unknown[]) => previewDocumentMock(...args),
  generateDocument: (...args: unknown[]) => generateDocumentMock(...args),
}));

import DocumentGenerator from "../../src/components/DocumentGenerator";
import type { ZoningReportData } from "../../src/lib/api";

const report = {
  address: "1233 Hueneme St, San Diego, CA 92110",
  density_analysis: { max_units: 7, governing_constraint: "min_lot_area" },
} as unknown as ZoningReportData;

describe("DocumentGenerator — entitlement / rezoning contingency", () => {
  beforeEach(() => {
    previewDocumentMock.mockReset();
    generateDocumentMock.mockReset();
    previewDocumentMock.mockResolvedValue({
      document_type: "psa",
      deal_type: "land_deal",
      clause_count: 1,
      clauses: [],
    });
  });

  it("hides the toggle for a non-contract document (deal summary)", () => {
    render(<DocumentGenerator report={report} />);
    // default document type is deal_summary → no entitlement switch
    expect(screen.queryByRole("switch", { name: /entitlement/i })).toBeNull();
  });

  it("hides the toggle for a PSA that is not a land deal", async () => {
    const user = userEvent.setup();
    render(<DocumentGenerator report={report} />);
    // Set the non-land deal type first so the section never mounts (avoids
    // depending on AnimatePresence exit timing in jsdom).
    await user.selectOptions(screen.getByLabelText("Deal Type"), "subject_to");
    await user.selectOptions(screen.getByLabelText("Document Type"), "psa");
    expect(screen.queryByRole("switch", { name: /entitlement/i })).toBeNull();
  });

  it("sends the contingency context when toggled on for a land-deal PSA", async () => {
    const user = userEvent.setup();
    render(<DocumentGenerator report={report} />);
    await user.selectOptions(screen.getByLabelText("Document Type"), "psa");

    const sw = screen.getByRole("switch", { name: /entitlement/i });
    expect(sw.getAttribute("aria-checked")).toBe("false");
    await user.click(sw);
    expect(sw.getAttribute("aria-checked")).toBe("true");

    await user.click(screen.getByRole("button", { name: /^preview$/i }));

    await waitFor(() => expect(previewDocumentMock).toHaveBeenCalledTimes(1));
    const arg = previewDocumentMock.mock.calls[0][0] as {
      document_type: string;
      context: Record<string, unknown>;
    };
    expect(arg.document_type).toBe("psa");
    expect(arg.context.entitlement_contingency).toBe(true);
    expect(arg.context.upzoning_vehicle).toBe("Special Use Permit");
    expect(arg.context.entitlement_close_days).toBe(365);
    expect(arg.context.entitlement_extension_days).toBe(180);
  });

  it("omits the contingency when the toggle is left off", async () => {
    const user = userEvent.setup();
    render(<DocumentGenerator report={report} />);
    await user.selectOptions(screen.getByLabelText("Document Type"), "psa");
    await user.click(screen.getByRole("button", { name: /^preview$/i }));

    await waitFor(() => expect(previewDocumentMock).toHaveBeenCalledTimes(1));
    const arg = previewDocumentMock.mock.calls[0][0] as { context: Record<string, unknown> };
    expect(arg.context.entitlement_contingency).toBeUndefined();
  });
});
