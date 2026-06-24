import {
  test,
  expect,
  gotoHome,
  requireHealthyBackend,
  runLookupFlow,
  switchToAgent,
  switchToLookup,
  waitForReport,
} from "./helpers";

let dbPreflight = {
  healthy: true,
  reason: "",
};

test.describe("Canonical cross-mode lane", () => {
  test.beforeAll(async () => {
    dbPreflight = await requireHealthyBackend();
  });

  test.beforeEach(() => {
    test.skip(!dbPreflight.healthy, dbPreflight.reason);
  });

  test("lookup flow stays clean when switching modes", async ({ page }) => {
    await gotoHome(page);
    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");
    await waitForReport(page);

    await switchToAgent(page);
    await expect(page.getByTestId("deal-type-selector")).toHaveCount(0);
    await expect(page.getByTestId("pipeline-approval-card")).toHaveCount(0);

    await switchToLookup(page);
    await expect(page.getByTestId("deal-type-selector")).toHaveCount(0);
    await expect(page.getByTestId("pipeline-approval-card")).toHaveCount(0);
    await expect(page.getByTestId("lookup-input")).toBeVisible();
  });

  test("report context survives mode switches until reset", async ({ page }) => {
    await gotoHome(page);
    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");
    await waitForReport(page);

    await switchToAgent(page);
    await expect(page.getByTestId("report-root")).toBeVisible();

    await switchToLookup(page);
    await expect(page.getByTestId("report-root")).toBeVisible();

    await page.getByTestId("new-analysis-button").click();
    await expect(page.getByTestId("report-root")).toHaveCount(0);
  });
});
