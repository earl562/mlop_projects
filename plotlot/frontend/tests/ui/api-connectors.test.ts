import { afterEach, describe, expect, it, vi } from "vitest";

import { testEmailConnector } from "../../src/lib/api";

describe("connector API helpers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends email test actions as JSON requests", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init).toMatchObject({
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Session-ID": "session-123",
        },
        body: "{}",
      });
      return new Response(
        JSON.stringify({
          sent: true,
          message_id: "message-123",
          daily_sends_used: 1,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(testEmailConnector("session-123")).resolves.toEqual({
      sent: true,
      message_id: "message-123",
      daily_sends_used: 1,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
