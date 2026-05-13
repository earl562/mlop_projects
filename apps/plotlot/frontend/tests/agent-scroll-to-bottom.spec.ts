import { expect, gotoHome, switchToAgent, test } from "./helpers";

function buildSseBody(fullContent: string) {
  const tokens = fullContent.split(/(\s+)/).filter(Boolean);
  return [
    `event: session\ndata: ${JSON.stringify({ session_id: "scroll-session" })}\n\n`,
    ...tokens.map((token) => `event: token\ndata: ${JSON.stringify({ content: token })}\n\n`),
    `event: done\ndata: ${JSON.stringify({ full_content: fullContent })}\n\n`,
  ].join("");
}

test.describe("Scroll to bottom affordance", () => {
  test("shows jump-to-latest when scrolled up, and hides it after clicking", async ({ page }) => {
    const longContent = Array.from({ length: 140 }, (_, i) => `Line ${i + 1}`).join("\n");

    await page.route("**/api/v1/chat", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: buildSseBody(longContent),
      });
    });

    await gotoHome(page);
    await switchToAgent(page);

    await page.getByTestId("agent-input").fill("Create a long message");
    await page.getByTestId("send-button").click();

    await expect(page.getByText("Line 140")).toBeVisible({ timeout: 15_000 });

    const scroller = page.getByTestId("conversation-scroll");
    await scroller.evaluate((el) => {
      el.scrollTop = 0;
    });

    const jump = page.getByTestId("scroll-to-bottom");
    await expect(jump).toBeVisible({ timeout: 5_000 });

    await jump.click();

    await expect(jump).toBeHidden({ timeout: 5_000 });
    await expect(page.getByText("Line 140")).toBeVisible({ timeout: 5_000 });
  });
});

