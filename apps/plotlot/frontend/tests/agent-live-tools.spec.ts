import { expect, gotoHome, switchToAgent, test } from "./helpers";

function buildToolSseBody({
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

test.describe("Agent live-tool seams (UI)", () => {
  test("shows tool activity for OpenData + Municode live tools", async ({ page }, testInfo) => {
    await gotoHome(page);
    await switchToAgent(page);
    const conversation = page.getByLabel("Analysis conversation");

    let callCount = 0;
    await page.route("**/api/v1/chat", async (route) => {
      callCount += 1;

      if (callCount === 1) {
        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          body: buildToolSseBody({
            sessionId: "tools-session",
            toolName: "discover_open_data_layers",
            toolMessage: "Discovering live Open Data layers...",
            fullContent:
              "I found a parcels layer and a zoning layer for the county. Here are the dataset URLs and the key fields you can query next.",
          }),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: buildToolSseBody({
          sessionId: "tools-session",
          toolName: "search_municode_live",
          toolMessage: "Searching live Municode headings...",
          fullContent:
            "Top Municode matches include a setbacks section and a definitions section. I will summarize the setback rule and cite the headings returned.",
        }),
      });
    });

    const agentInput = page.getByTestId("agent-input");
    const sendButton = page.getByTestId("send-button");

    await agentInput.fill(
      "Find open data parcel and zoning layers for Broward County near 25.9873, -80.2323",
    );
    await sendButton.click();
    await expect(conversation.getByText("Used discover_open_data_layers")).toBeVisible({
      timeout: 15_000,
    });
    await expect(conversation.getByTestId("inline-tool-discover_open_data_layers")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("Live agent activity")).toHaveCount(0);
    await expect(page.getByText("Agent follow-up")).toHaveCount(0);
    await page.screenshot({
      path: testInfo.outputPath("01-open-data-tool.png"),
      fullPage: true,
    });

    await expect(agentInput).toBeEnabled({ timeout: 15_000 });
    await agentInput.fill("Search Municode for Miramar, FL setbacks");
    await sendButton.click();
    await expect(conversation.getByText("Used search_municode_live")).toBeVisible({
      timeout: 15_000,
    });
    await expect(conversation.getByTestId("inline-tool-search_municode_live")).toBeVisible({
      timeout: 15_000,
    });
    await page.screenshot({
      path: testInfo.outputPath("02-municode-tool.png"),
      fullPage: true,
    });
  });
});
