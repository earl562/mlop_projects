import { afterEach, describe, expect, it, vi } from "vitest";

import { streamChat, type ThinkingEvent, type ToolUseEvent } from "../../src/lib/api";

describe("streamChat", () => {
  afterEach(() => {
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
});
