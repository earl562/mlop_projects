import { test, expect } from "@playwright/test";

test("capture full analysis flow screenshots", async ({ page }) => {
  test.setTimeout(180_000);

  // 1: Welcome
  await page.goto("http://localhost:3000");
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: "tests/screenshots/e2e-01-welcome.png", fullPage: true });

  // 2: Enter address
  await page.getByPlaceholder("Enter an address or ask a question...").fill("2400 NW 167th St, Miami Gardens, FL 33054");
  await page.screenshot({ path: "tests/screenshots/e2e-02-input.png" });

  // 3: Submit
  await page.getByRole("button", { name: "Send message" }).click();
  await page.waitForSelector("text=Geocoding", { timeout: 15_000 });
  await page.screenshot({ path: "tests/screenshots/e2e-03-pipeline.png" });

  // 4: Wait for report card
  await page.waitForSelector('[class*="border-l-amber"]', { timeout: 120_000 });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: "tests/screenshots/e2e-04-report-top.png" });

  // 5: Full page
  await page.screenshot({ path: "tests/screenshots/e2e-05-report-full.png", fullPage: true });

  // 6: Scroll to setbacks
  const setbacks = page.locator("text=Setbacks").first();
  if (await setbacks.isVisible()) {
    await setbacks.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    await page.screenshot({ path: "tests/screenshots/e2e-06-setbacks.png" });
  }

  // 7: 3D Envelope
  const envelope = page.locator("text=3D Buildable Envelope").first();
  if (await envelope.isVisible()) {
    await envelope.scrollIntoViewIfNeeded();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: "tests/screenshots/e2e-07-3d-envelope.png" });
  }

  // 8: Floor Plan
  const fp = page.locator("text=Floor Plan").first();
  if (await fp.isVisible()) {
    await fp.scrollIntoViewIfNeeded();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: "tests/screenshots/e2e-08-floor-plan.png" });
  }

  // 9: Property card
  const prop = page.locator("text=Property Record").first();
  if (await prop.isVisible()) {
    await prop.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    await page.screenshot({ path: "tests/screenshots/e2e-09-property.png" });
  }

  // 10: Sources
  const srcBtn = page.locator("button:has-text('View')").first();
  if (await srcBtn.isVisible()) {
    await srcBtn.scrollIntoViewIfNeeded();
    await srcBtn.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: "tests/screenshots/e2e-10-sources.png" });
  }
});
