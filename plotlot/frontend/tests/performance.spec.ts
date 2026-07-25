import { expect, test } from "./fixtures";

test("workspace becomes interactive within the bounded release budget", async ({
  page,
}, testInfo) => {
  const startedAt = Date.now();
  await page.goto("/workspace", { waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("lookup-input")).toBeVisible();
  const readyMilliseconds = Date.now() - startedAt;
  const navigation = await page.evaluate(() => {
    const entry = performance.getEntriesByType("navigation")[0];
    if (!(entry instanceof PerformanceNavigationTiming)) {
      return null;
    }
    return {
      domContentLoaded: entry.domContentLoadedEventEnd,
      responseEnd: entry.responseEnd,
    };
  });

  expect(readyMilliseconds).toBeLessThan(15_000);
  expect(navigation).not.toBeNull();
  await testInfo.attach("performance-budget.json", {
    body: JSON.stringify({ navigation, readyMilliseconds }, null, 2),
    contentType: "application/json",
  });
});
