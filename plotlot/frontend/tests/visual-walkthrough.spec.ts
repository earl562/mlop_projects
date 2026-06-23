import { test, expect, gotoHome, requireHealthyBackend, runLookupFlow, waitForReport } from "./helpers";

const VISUAL_VIEWPORTS = [
  { name: "mobile", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1280, height: 720 },
] as const;

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
    for (const viewport of VISUAL_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await gotoHome(page);
      const unpkgReactScripts = page.locator('script[src*="unpkg.com/react-"]');
      await expect(await unpkgReactScripts.count()).toBeLessThanOrEqual(2);
      await page.screenshot({
        path: testInfo.outputPath(`01-welcome-${viewport.name}.png`),
        fullPage: true,
        animations: "disabled",
      });
    }

    await page.setViewportSize({ width: 1280, height: 720 });
    await gotoHome(page);
    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");
    await page
      .locator('[data-testid="pipeline-stepper"], [data-testid="report-root"]')
      .first()
      .waitFor({ state: "visible", timeout: 15_000 });
    await page.screenshot({
      path: testInfo.outputPath("02-pipeline.png"),
      fullPage: true,
      animations: "disabled",
    });

    await waitForReport(page);
    await expect(page.getByTestId("pipeline-stepper")).toHaveCount(0);
    for (const viewport of VISUAL_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page
        .getByTestId("report-root")
        .evaluate((element) => element.scrollIntoView({ block: "start" }));
      await page.screenshot({
        path: testInfo.outputPath(`03-report-top-${viewport.name}.png`),
        animations: "disabled",
      });
      await page.screenshot({
        path: testInfo.outputPath(`04-report-full-${viewport.name}.png`),
        fullPage: true,
        animations: "disabled",
      });
    }
  });
});
