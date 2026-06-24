import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AgentRunSnapshotEvidenceDetails from "../../src/components/AgentRunSnapshotEvidenceDetails";
import AgentRunTraceSummary from "../../src/components/AgentRunTraceSummary";
import { parseAgentRunTrace } from "../../src/lib/agentRunTraceParser";
import { tracePayload } from "./agent-run-trace.fixtures";

describe("agent run evidence links", () => {
  it("renders unsafe trace source URLs as inert text", () => {
    const payload = tracePayload();
    const packet = payload.evidence_packets[0];
    const retrieval = payload.source_retrievals[0];
    if (!packet || !retrieval) {
      throw new Error("trace fixture must include source records");
    }
    packet.source_url = "javascript:alert(1)";
    retrieval.source_url = "data:text/html,<script>alert(1)</script>";

    render(<AgentRunTraceSummary trace={parseAgentRunTrace(payload)} />);

    expect(screen.getAllByText("Recorded parcel appraiser packet").length).toBeGreaterThan(0);
    expect(unsafeRenderedHrefs()).toEqual([]);
  });

  it("renders unsafe lookup snapshot source URLs as inert text", () => {
    render(
      <AgentRunSnapshotEvidenceDetails
        calculations={[]}
        sources={[
          {
            evidence_id: "evidence-unsafe",
            source_url: "javascript:alert(1)",
            source_title: "Unsafe source",
            effective_date: "2026-01-01",
          },
        ]}
      />,
    );

    expect(screen.getByText("Unsafe source")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /unsafe source/i })).not.toBeInTheDocument();
    expect(unsafeRenderedHrefs()).toEqual([]);
  });
});

function unsafeRenderedHrefs(): readonly string[] {
  return Array.from(document.querySelectorAll("a"))
    .map((link) => link.getAttribute("href") ?? "")
    .filter((href) => href.startsWith("javascript:") || href.startsWith("data:"));
}
