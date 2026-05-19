import { expect, gotoHome, switchToAgent, test } from "./helpers";

function buildSseBody(fullContent: string) {
  const tokens = fullContent.split(/(\s+)/).filter(Boolean);
  return [
    `event: session\ndata: ${JSON.stringify({ session_id: "edit-session" })}\n\n`,
    `event: tool_use\ndata: ${JSON.stringify({ tool: "report_context", args: {}, message: "Using report context" })}\n\n`,
    ...tokens.map((token) => `event: token\ndata: ${JSON.stringify({ content: token })}\n\n`),
    `event: tool_result\ndata: ${JSON.stringify({ tool: "report_context" })}\n\n`,
    `event: done\ndata: ${JSON.stringify({ full_content: fullContent })}\n\n`,
  ].join("");
}

test.describe("Edit prompt", () => {
  test("lets the user edit a prompt and re-run the turn", async ({ page }) => {
    let callCount = 0;
    await page.route("**/api/v1/chat", async (route) => {
      callCount += 1;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: buildSseBody(callCount === 1 ? "First response" : "Second response after edit"),
      });
    });

    await gotoHome(page);
    await switchToAgent(page);

    await page.getByTestId("agent-input").fill("Original prompt");
    await page.getByTestId("send-button").click();
    await expect(page.getByText("First response")).toBeVisible({ timeout: 15_000 });

    await page.getByTestId("user-edit").last().click();
    await expect(page.getByTestId("user-edit-input")).toBeVisible();
    await page.getByTestId("user-edit-input").fill("Updated prompt");
    await page.getByTestId("user-edit-save").click();

    await expect(page.getByText("Second response after edit")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("First response")).toHaveCount(0);
  });
});

