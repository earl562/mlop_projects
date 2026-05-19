import { afterEach, describe, expect, it, vi } from "vitest";

import { streamAnalysis, type AnalysisError } from "../../src/lib/api";

describe("streamAnalysis", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("propagates backend error_type from SSE events", async () => {
    const sseBody = [
      `event: status\ndata: ${JSON.stringify({ step: "geocoding", message: "Resolving address..." })}\n\n`,
      `event: error\ndata: ${JSON.stringify({ detail: "Backend offline", error_type: "backend_unavailable" })}\n\n`,
    ].join("");

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(sseBody, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      ),
    );

    const statuses: string[] = [];
    let receivedError: AnalysisError | null = null;

    await streamAnalysis(
      { address: "7940 Plantation Blvd, Miramar, FL 33023" },
      (status) => {
        statuses.push(status.step);
      },
      () => {
        throw new Error("result should not be emitted");
      },
      (error) => {
        receivedError = error;
      },
    );

    expect(statuses).toEqual(["geocoding"]);
    expect(receivedError).toEqual({
      detail: "Backend offline",
      errorType: "backend_unavailable",
    });
  });
});
