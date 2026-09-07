import { afterEach, describe, expect, it, vi } from "vitest";

import { streamChat, type ThinkingEvent, type ToolUseEvent } from "../../src/lib/api";

describe("streamChat", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("surfaces thinking events separately from tool activity", async () => {
    const sseBody = [
      `event: session\ndata: ${JSON.stringify({ session_id: "session-1" })}\n\n`,
      `event: thinking\ndata: ${JSON.stringify({ step: "intent", thoughts: ["Detected intent: search properties"] })}\n\n`,
      `event: tool_use\ndata: ${JSON.stringify({ tool: "search_properties", args: { county: "Miami-Dade" }, message: "Searching property records..." })}\n\n`,
      `event: done\ndata: ${JSON.stringify({ full_content: "Found matching properties." })}\n\n`,
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

    const sessions: string[] = [];
    const thinkingEvents: ThinkingEvent[] = [];
    const toolEvents: ToolUseEvent[] = [];
    const tokens: string[] = [];
    const done: string[] = [];

    await streamChat(
      "find vacant lots",
      [],
      null,
      (token) => tokens.push(token),
      (fullContent) => done.push(fullContent),
      () => {
        throw new Error("error should not be emitted");
      },
      null,
      (sessionId) => sessions.push(sessionId),
      (toolEvent) => toolEvents.push(toolEvent),
      () => {},
      (thinkingEvent) => thinkingEvents.push(thinkingEvent),
    );

    expect(sessions).toEqual(["session-1"]);
    expect(thinkingEvents).toEqual([
      { step: "intent", thoughts: ["Detected intent: search properties"] },
    ]);
    expect(toolEvents).toEqual([
      {
        tool: "search_properties",
        args: { county: "Miami-Dade" },
        message: "Searching property records...",
      },
    ]);
    expect(tokens).toEqual([]);
    expect(done).toEqual(["Found matching properties."]);
  });

  it.each([
    {
      name: "close without a terminal event",
      response: new Response(
        `event: session\ndata: ${JSON.stringify({ session_id: "session-1" })}\n\n`,
        { status: 200, headers: { "Content-Type": "text/event-stream" } },
      ),
      expected: "The response stream ended before completion. Please try again.",
    },
    {
      name: "malformed JSON",
      response: new Response("event: token\ndata: {not-json}\n\n", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }),
      expected: "The response stream sent invalid data. Please try again.",
    },
  ])("reports one recoverable error for $name", async ({ response, expected }) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    const errors: string[] = [];
    const done: string[] = [];

    await streamChat(
      "Explain this parcel",
      [],
      null,
      () => {},
      (content) => done.push(content),
      (error) => errors.push(error),
    );

    expect(errors).toEqual([expected]);
    expect(done).toEqual([]);
  });

  it("reports one recoverable error when the request is aborted", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("The operation was aborted", "AbortError")),
    );
    const errors: string[] = [];

    await streamChat(
      "Explain this parcel",
      [],
      null,
      () => {},
      () => {
        throw new Error("done should not be emitted");
      },
      (error) => errors.push(error),
    );

    expect(errors).toEqual(["The response was cancelled. Please try again."]);
  });

  it("reports one recoverable error after a 30 second idle timeout", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockImplementation(
      (_input: RequestInfo | URL, init?: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted", "AbortError"));
          });
        }),
    ));
    const errors: string[] = [];

    const pending = streamChat(
      "Explain this parcel",
      [],
      null,
      () => {},
      () => {
        throw new Error("done should not be emitted");
      },
      (error) => errors.push(error),
    );
    await vi.advanceTimersByTimeAsync(30_000);
    await pending;

    expect(errors).toEqual(["The response timed out. Please try again."]);
  });

  it("reports one HTTP failure and ignores duplicate terminal events", async () => {
    const httpErrors: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: "Backend unavailable" }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await streamChat(
      "Explain this parcel",
      [],
      null,
      () => {},
      () => {
        throw new Error("done should not be emitted");
      },
      (error) => httpErrors.push(error),
    );
    expect(httpErrors).toEqual(["Backend unavailable"]);

    const terminalBody = [
      `event: done\ndata: ${JSON.stringify({ full_content: "Complete" })}\n\n`,
      `event: error\ndata: ${JSON.stringify({ detail: "late error" })}\n\n`,
    ].join("");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(
        new Response(terminalBody, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      ),
    );
    const done: string[] = [];
    const lateErrors: string[] = [];

    await streamChat(
      "Explain this parcel",
      [],
      null,
      () => {},
      (content) => done.push(content),
      (error) => lateErrors.push(error),
    );

    expect(done).toEqual(["Complete"]);
    expect(lateErrors).toEqual([]);
  });
});
