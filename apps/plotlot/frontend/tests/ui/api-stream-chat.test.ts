import { afterEach, describe, expect, it, vi } from "vitest";

import {
  streamChat,
  type AgentTaskEvent,
  type BrowserActionEvent,
  type ReasoningEvent,
  type ThinkingEvent,
  type ToolUseEvent,
} from "../../src/lib/api";

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

  it("processes a final SSE event even without a trailing blank line", async () => {
    const sseBody = [
      `event: token\ndata: ${JSON.stringify({ content: "Hello" })}\n\n`,
      `event: done\ndata: ${JSON.stringify({ full_content: "Hello" })}`,
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

    const tokens: string[] = [];
    const done: string[] = [];

    await streamChat(
      "hello",
      [],
      null,
      (token) => tokens.push(token),
      (fullContent) => done.push(fullContent),
      () => {
        throw new Error("error should not be emitted");
      },
    );

    expect(tokens).toEqual(["Hello"]);
    expect(done).toEqual(["Hello"]);
  });

  it("reports a chat connection failure without throwing into the app shell", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    const errors: string[] = [];

    await expect(
      streamChat(
        "hello",
        [],
        null,
        () => {},
        () => {},
        (error) => errors.push(error),
      ),
    ).resolves.toBeUndefined();

    expect(errors).toEqual(["Connection failed. Is the backend running?"]);
  });

  it("surfaces structured task, browser, and reasoning events for visible agent work", async () => {
    const taskStart = {
      task_id: "task-1",
      task_type: "browser",
      name: "Open zoning portal",
      detail: "Navigating to the county zoning website.",
    };
    const browserAction = {
      action: "navigate",
      url: "https://example.gov/zoning",
      extracted_text: "County zoning portal",
    };
    const reasoning = {
      phase: "plan",
      summary: "Use live browser research because the local ordinance cache may be stale.",
      confidence: 0.82,
      alternatives: ["Use cached Municode chunks"],
    };
    const taskComplete = {
      task_id: "task-1",
      title: "Open zoning portal",
      detail: "Loaded the source page.",
      duration_ms: 1200,
    };
    const sseBody = [
      `event: task_start\ndata: ${JSON.stringify(taskStart)}\n\n`,
      `event: browser_action\ndata: ${JSON.stringify(browserAction)}\n\n`,
      `event: reasoning\ndata: ${JSON.stringify(reasoning)}\n\n`,
      `event: task_complete\ndata: ${JSON.stringify(taskComplete)}\n\n`,
      `event: done\ndata: ${JSON.stringify({ full_content: "Browser research complete." })}\n\n`,
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

    const tasks: AgentTaskEvent[] = [];
    const browserActions: BrowserActionEvent[] = [];
    const reasonings: ReasoningEvent[] = [];
    const done: string[] = [];

    await streamChat(
      "research zoning portal",
      [],
      null,
      () => {},
      (fullContent) => done.push(fullContent),
      () => {
        throw new Error("error should not be emitted");
      },
      null,
      undefined,
      undefined,
      undefined,
      undefined,
      (event) => tasks.push(event),
      (event) => browserActions.push(event),
      (event) => reasonings.push(event),
    );

    expect(tasks).toEqual([
      { ...taskStart, type: "task_start" },
      { ...taskComplete, type: "task_complete" },
    ]);
    expect(browserActions).toEqual([{ ...browserAction, type: "browser_action" }]);
    expect(reasonings).toEqual([reasoning]);
    expect(done).toEqual(["Browser research complete."]);
  });
});
