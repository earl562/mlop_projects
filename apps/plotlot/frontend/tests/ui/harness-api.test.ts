import { afterEach, describe, expect, it, vi } from "vitest";

import { invokeMcpTool, listMcpTools, runHarness } from "../../src/lib/api";

describe("harness api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("posts harness runs to the runtime endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "success",
          summary: "done",
          data: { report: { zoning_district: "RU-1" } },
          evidence_ids: ["ev_source_0"],
          open_questions: [],
          next_actions: ["review_evidence"],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await runHarness({
      intent: "zoning_lookup",
      prompt: "123 Main St",
      payload: { address: "123 Main St" },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/harness/run",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          intent: "zoning_lookup",
          prompt: "123 Main St",
          payload: { address: "123 Main St" },
        }),
      }),
    );
    expect(result.evidence_ids).toEqual(["ev_source_0"]);
  });

  it("loads MCP tool contracts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            tools: [
              {
                name: "plotlot.discover_open_data_layers",
                description: "Discover parcel and zoning layers.",
                risk_class: "read_only",
                input_schema: { required: ["county", "lat", "lng"] },
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    const result = await listMcpTools();

    expect(result.tools[0]?.name).toBe("plotlot.discover_open_data_layers");
    expect(result.tools[0]?.risk_class).toBe("read_only");
  });

  it("invokes MCP tools through the web client", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "success",
          tool: "plotlot.discover_open_data_layers",
          result: { county: "Broward" },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await invokeMcpTool("plotlot.discover_open_data_layers", {
      county: "Broward",
      lat: 26.1,
      lng: -80.1,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/mcp/invoke",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          name: "plotlot.discover_open_data_layers",
          input: { county: "Broward", lat: 26.1, lng: -80.1 },
        }),
      }),
    );
    expect(result.result.county).toBe("Broward");
  });
});
