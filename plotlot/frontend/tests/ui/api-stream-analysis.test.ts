import { afterEach, describe, expect, it, vi } from "vitest";

import { streamAnalysis, type AnalysisError } from "../../src/lib/api";

describe("streamAnalysis", () => {
  afterEach(() => {
    vi.useRealTimers();
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

  it("falls back to sync analysis after repeated stream connection failures", async () => {
    vi.useFakeTimers();

    const report = {
      address: "7940 Plantation Blvd, Miramar, FL 33023",
      formatted_address: "7940 Plantation Blvd, Miramar, FL 33023",
      municipality: "Miramar",
      county: "Broward",
      lat: 26.0,
      lng: -80.0,
      zoning_district: "RM-25",
      zoning_description: "Multifamily",
      allowed_uses: [],
      conditional_uses: [],
      prohibited_uses: [],
      setbacks: { front: "", side: "", rear: "" },
      max_height: "",
      max_density: "",
      floor_area_ratio: "",
      lot_coverage: "",
      min_lot_size: "",
      parking_requirements: "",
      property_record: null,
      numeric_params: null,
      density_analysis: null,
      comp_analysis: null,
      pro_forma: null,
      summary: "Recovered via sync fallback",
      sources: [],
      confidence: "medium",
    };

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.endsWith("/api/v1/analyze/stream")) {
        throw new TypeError("fetch failed");
      }

      if (url.endsWith("/health")) {
        return new Response(
          JSON.stringify({
            status: "healthy",
            capabilities: { db_backed_analysis_ready: true },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.endsWith("/api/v1/analyze")) {
        return new Response(JSON.stringify(report), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      throw new Error(`Unexpected fetch URL: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    let receivedResult: typeof report | null = null;
    let receivedError: AnalysisError | null = null;

    const pending = streamAnalysis(
      { address: report.address },
      () => {},
      (result) => {
        receivedResult = result as unknown as typeof report;
      },
      (error) => {
        receivedError = error;
      },
    );

    await vi.advanceTimersByTimeAsync(2_000);
    await pending;

    expect(receivedResult).toEqual(report);
    expect(receivedError).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("reports one recoverable error when a status-only stream closes", async () => {
    const sseBody = [
      `event: status\ndata: ${JSON.stringify({ step: "geocoding", message: "Resolving address..." })}\n\n`,
    ].join("");

    const fetchMock = vi.fn().mockResolvedValue(
      new Response(sseBody, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    const statuses: string[] = [];
    const errors: AnalysisError[] = [];

    await streamAnalysis(
      { address: "7940 Plantation Blvd, Miramar, FL 33023" },
      (status) => {
        statuses.push(status.step);
      },
      () => {
        throw new Error("result should not be emitted");
      },
      (error) => {
        errors.push(error);
      },
    );

    expect(statuses).toEqual(["geocoding"]);
    expect(errors).toEqual([{
      detail: "The analysis stream ended before a final result was returned.",
      errorType: "pipeline_error",
    }]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
