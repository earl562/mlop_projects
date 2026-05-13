import { expect, gotoHome, stubAgentChatSse, switchToAgent, test } from "./helpers";

test.describe("Agent chat seamless UX", () => {
  test("keeps focus ready and shows completed tool context after streaming", async ({ page }) => {
    await gotoHome(page);
    await switchToAgent(page);
    const conversation = page.getByLabel("Analysis conversation");
    await stubAgentChatSse(page, {
      fullContent:
        "Based on the zoning context, review setbacks, density, and parking before underwriting.",
      toolName: "search_zoning_ordinance",
      toolMessage: "Searching ordinance context...",
    });

    await page.getByTestId("agent-input").fill("What should I review next?");
    await page.getByTestId("send-button").click();

    await expect(page.getByText("review setbacks")).toBeVisible({ timeout: 15_000 });
    await expect(conversation.getByText("Used search_zoning_ordinance")).toBeVisible();
    await expect(page.getByTestId("agent-input")).toBeFocused();
  });
});
