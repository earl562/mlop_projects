import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const FAL_PROXY_TARGET = "https://fal.run/fal-ai/veo3";

async function importFalProxyRoute() {
  vi.resetModules();
  return await import("../../src/app/api/fal/proxy/route");
}

describe("FAL proxy API route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("rejects non-json proxy requests before upstream unsupported content-type leaks", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "Unsupported content type" }), {
          status: 415,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { POST } = await importFalProxyRoute();

    const response = await POST(
      new NextRequest("http://localhost/api/fal/proxy", {
        method: "POST",
        headers: {
          "Content-Type": "text/plain",
          "x-fal-target-url": FAL_PROXY_TARGET,
        },
        body: "not json",
      }),
    );
    const body = await response.json();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(response.status).toBe(415);
    expect(body).toMatchObject({
      error: expect.stringContaining("application/json"),
    });
    expect(body).not.toMatchObject({ detail: "Unsupported content type" });
  });

  it("passes json proxy requests through to the upstream route", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ video: { url: "https://videos.example/flyover.mp4" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { POST } = await importFalProxyRoute();

    const response = await POST(
      new NextRequest("http://localhost/api/fal/proxy", {
        method: "POST",
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "x-fal-target-url": FAL_PROXY_TARGET,
        },
        body: JSON.stringify({ input: { prompt: "aerial flyover" } }),
      }),
    );
    const body = await response.json();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(response.status).toBe(200);
    expect(body).toMatchObject({
      video: { url: "https://videos.example/flyover.mp4" },
    });
  });
});
