import { expect, gotoHome, switchToAgent, test } from "./helpers";

test.describe("Stop generating", () => {
  test("can abort a streaming agent response without showing an error", async ({ page }) => {
    await page.addInitScript(() => {
      const originalFetch = window.fetch.bind(window);
      window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (!url.includes("/api/v1/chat")) {
          return originalFetch(input as never, init);
        }

        const encoder = new TextEncoder();
        const signal = init?.signal;

        const sseEvents: string[] = [
          `event: session\ndata: ${JSON.stringify({ session_id: "stop-session" })}\n\n`,
          `event: tool_use\ndata: ${JSON.stringify({ tool: "discover_open_data_layers", args: {}, message: "Discovering..." })}\n\n`,
          `event: token\ndata: ${JSON.stringify({ content: "Streaming" })}\n\n`,
          `event: token\ndata: ${JSON.stringify({ content: " " })}\n\n`,
          `event: token\ndata: ${JSON.stringify({ content: "content" })}\n\n`,
          `event: token\ndata: ${JSON.stringify({ content: " " })}\n\n`,
          `event: token\ndata: ${JSON.stringify({ content: "that" })}\n\n`,
          `event: token\ndata: ${JSON.stringify({ content: " " })}\n\n`,
          `event: token\ndata: ${JSON.stringify({ content: "should" })}\n\n`,
          `event: token\ndata: ${JSON.stringify({ content: " " })}\n\n`,
          `event: token\ndata: ${JSON.stringify({ content: "be" })}\n\n`,
          `event: token\ndata: ${JSON.stringify({ content: " " })}\n\n`,
          `event: token\ndata: ${JSON.stringify({ content: "interruptible." })}\n\n`,
          `event: done\ndata: ${JSON.stringify({ full_content: "Streaming content that should be interruptible." })}\n\n`,
        ];

        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            let idx = 0;
            const pump = () => {
              if (signal?.aborted) {
                controller.error(new DOMException("Aborted", "AbortError"));
                return;
              }
              if (idx >= sseEvents.length) {
                controller.close();
                return;
              }
              controller.enqueue(encoder.encode(sseEvents[idx]));
              idx += 1;
              setTimeout(pump, 120);
            };
            pump();

            signal?.addEventListener("abort", () => {
              controller.error(new DOMException("Aborted", "AbortError"));
            });
          },
        });

        return new Response(stream, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      };
    });

    await gotoHome(page);
    await switchToAgent(page);

    await page.getByTestId("agent-input").fill("Start streaming");
    await page.getByTestId("send-button").click();

    await expect(page.getByText("Streaming")).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: "Stop generating" }).click();

    await expect(page.getByTestId("send-button")).toHaveAttribute("aria-label", "Send message");
    await expect(page.getByText("Error:")).toHaveCount(0);
    await expect(page.getByText("Connection interrupted")).toHaveCount(0);
  });
});

