import { test, expect, gotoHome, requireHealthyBackend, runLookupFlow, waitForReport } from "./helpers";

let dbPreflight = {
  healthy: true,
  reason: "",
};

test.describe("Canonical visual walkthrough lane", () => {
  test.beforeAll(async () => {
    dbPreflight = await requireHealthyBackend();
  });

  test.beforeEach(() => {
    test.skip(!dbPreflight.healthy, dbPreflight.reason);
  });

  test("captures planned walkthrough artifacts", async ({ page }, testInfo) => {
    await gotoHome(page);
    await page.screenshot({ path: testInfo.outputPath("01-welcome.png"), fullPage: true });

    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");
    await expect(page.getByTestId("pipeline-stepper")).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("02-pipeline.png"), fullPage: true });

    await waitForReport(page);
    await page.screenshot({ path: testInfo.outputPath("03-report-top.png") });
    await page.screenshot({ path: testInfo.outputPath("04-report-full.png"), fullPage: true });
  });
});
