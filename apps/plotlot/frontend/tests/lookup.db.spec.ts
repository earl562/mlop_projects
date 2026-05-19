import {
  test,
  expect,
  gotoHome,
  requireHealthyBackend,
  runLookupFlow,
  waitForReport,
} from "./helpers";

let dbPreflight = {
  healthy: true,
  reason: "",
};

test.describe("Canonical db-backed lookup lane", () => {
  test.beforeAll(async () => {
    dbPreflight = await requireHealthyBackend();
  });

  test.beforeEach(() => {
    test.skip(!dbPreflight.healthy, dbPreflight.reason);
  });

  test("lookup renders canonical report sections", async ({ page }) => {
    await gotoHome(page);
    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");
    await waitForReport(page);

    await expect(page.getByTestId("report-root")).toBeVisible();
    await expect(page.getByTestId("report-property-tab")).toBeVisible();
    await expect(page.getByTestId("report-section-property")).toBeVisible();

    await page.getByTestId("report-zoning-tab").click();
    await expect(page.getByTestId("report-section-zoning")).toBeVisible();

    await page.getByTestId("report-analysis-tab").click();
    await expect(page.getByTestId("report-section-analysis")).toBeVisible();

    await page.getByTestId("report-deal-tab").click();
    await expect(page.getByTestId("report-section-deal")).toBeVisible();
  });

  test("new analysis resets to canonical welcome state", async ({ page }) => {
    await gotoHome(page);
    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");
    await waitForReport(page);

    await page.getByTestId("new-analysis-button").click();
    await expect(page.getByTestId("lookup-input")).toBeVisible();
    await expect(page.getByTestId("report-root")).toHaveCount(0);
  });
});
