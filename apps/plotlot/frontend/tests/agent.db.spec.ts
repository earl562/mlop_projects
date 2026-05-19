import {
  test,
  expect,
  gotoHome,
  requireHealthyBackend,
  runLookupFlow,
  stubAgentChatSse,
  switchToAgent,
  waitForReport,
} from "./helpers";

let dbPreflight = {
  healthy: true,
  reason: "",
};

test.describe("Canonical db-backed agent lane", () => {
  test.beforeAll(async () => {
    dbPreflight = await requireHealthyBackend();
  });

  test.beforeEach(() => {
    test.skip(!dbPreflight.healthy, dbPreflight.reason);
  });

  test("report-backed follow-up uses deterministic chat stubs", async ({ page }) => {
    await gotoHome(page);
    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");
    await waitForReport(page);

    await switchToAgent(page);
    await stubAgentChatSse(page, {
      fullContent:
        "Miramar zoning context is loaded. Based on the report, you should review setbacks and density before underwriting.",
    });

    await page.getByTestId("agent-input").fill("What should I review next?");
    await page.getByTestId("send-button").click();

    await expect(page.getByText("Miramar zoning context is loaded")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText("Used report_context")).toBeVisible();
  });
});
