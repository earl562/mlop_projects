import { expect, stubAgentChatSse, test } from "./helpers";

test.describe("Analyze console", () => {
  test("streams chat in the modern product shell and restores input focus", async ({ page }) => {
    await stubAgentChatSse(page, {
      fullContent:
        "Based on the zoning context, review setbacks, density, parking, and ordinance evidence before underwriting.",
      toolName: "search_zoning_ordinance",
      toolMessage: "Searching ordinance context...",
    });

    await page.goto("/analyze", { waitUntil: "domcontentloaded" });

    await expect(page.getByText("Land-use intelligence console.")).toBeVisible();
    await expect(page.getByText("AI ZONING ANALYSIS")).toHaveCount(0);
    await expect(page.getByTestId("analyze-computer-card")).toBeVisible();
    await expect(page.getByText("PlotLot Computer")).toBeVisible();
    await expect(page.getByTestId("analyze-status-card")).toBeVisible();
    await expect(page.getByTestId("analyze-plan-card")).toBeVisible();
    await expect(page.getByTestId("analyze-evidence-card")).toBeVisible();
    await expect(page.getByTestId("analyze-actions-card")).toBeVisible();

    await page.getByTestId("agent-input").fill("What should I review next?");
    await page.getByTestId("send-button").click();

    await expect(page.getByText("review setbacks")).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByTestId("analyze-computer-card").getByText("Searching ordinance context", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.getByText("Used search_zoning_ordinance")).toBeVisible();
    await expect(page.getByTestId("agent-input")).toBeFocused();
  });
});
