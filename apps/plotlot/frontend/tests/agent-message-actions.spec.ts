import { expect, gotoHome, switchToAgent, test } from "./helpers";

function buildSseBody({
  fullContent,
  toolName,
  toolMessage,
  sessionId,
}: {
  fullContent: string;
  toolName: string;
  toolMessage: string;
  sessionId: string;
}) {
  const tokens = fullContent.split(/(\s+)/).filter(Boolean);
  return [
    `event: session\ndata: ${JSON.stringify({ session_id: sessionId })}\n\n`,
    `event: tool_use\ndata: ${JSON.stringify({ tool: toolName, args: {}, message: toolMessage })}\n\n`,
    ...tokens.map((token) => `event: token\ndata: ${JSON.stringify({ content: token })}\n\n`),
    `event: tool_result\ndata: ${JSON.stringify({ tool: toolName })}\n\n`,
    `event: done\ndata: ${JSON.stringify({ full_content: fullContent })}\n\n`,
  ].join("");
}

test.describe("Assistant message actions", () => {
  test("copies code blocks, copies message, and can retry a turn", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "clipboard", {
        value: {
          writeText: async (text: string) => {
            (window as unknown as { __copiedText?: string }).__copiedText = text;
          },
        },
      });
    });

    await gotoHome(page);
    await switchToAgent(page);

    const firstResponse = [
      "Here is a quick example:",
      "",
      "```js",
      "console.log('hi')",
      "```",
    ].join("\n");

    let callCount = 0;
    await page.route("**/api/v1/chat", async (route) => {
      callCount += 1;

      const body =
        callCount === 1
          ? buildSseBody({
              sessionId: "actions-session",
              toolName: "report_context",
              toolMessage: "Using report context",
              fullContent: firstResponse,
            })
          : buildSseBody({
              sessionId: "actions-session",
              toolName: "report_context",
              toolMessage: "Using report context",
              fullContent: "Retry worked — here is a regenerated response.",
            });

      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body,
      });
    });

    await page.getByTestId("agent-input").fill("Show me code");
    await page.getByTestId("send-button").click();

    await expect(page.getByText("Here is a quick example:")).toBeVisible({
      timeout: 15_000,
    });

    const copyCode = page.getByRole("button", { name: "Copy code" });
    await page.getByText("console.log('hi')").hover();
    await expect(copyCode).toBeVisible();
    await copyCode.click();
    await expect
      .poll(() =>
        page.evaluate(() => (window as unknown as { __copiedText?: string }).__copiedText ?? ""),
      )
      .toBe("console.log('hi')");

    await page.getByTestId("assistant-copy").click();
    await expect
      .poll(() =>
        page.evaluate(() => (window as unknown as { __copiedText?: string }).__copiedText ?? ""),
      )
      .toContain("```js");

    await page.getByTestId("assistant-retry").click();
    await expect(page.getByText("Retry worked — here is a regenerated response.")).toBeVisible({
      timeout: 15_000,
    });
  });
});

