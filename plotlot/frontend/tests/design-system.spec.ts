import { test, expect } from "./fixtures";

async function revealScrollDrivenSections(page: import("@playwright/test").Page) {
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0; y < height; y += 600) {
    await page.evaluate((offset) => window.scrollTo(0, offset), y);
    await page.waitForTimeout(40);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
}

test.describe("PlotLot design system", () => {
  test.beforeEach(async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
  });

  test("root route presents the restored public homepage", async ({ page }, testInfo) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await expect(page.getByTestId("public-homepage")).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: "See What Fits.",
      }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "Analyze a Lot" }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Everything needed to evaluate a lot." })).toBeVisible();
    await expect(page.getByText("Trusted by developers, architects, and municipal teams")).toBeVisible();
    await expect(page.getByTestId("sidebar-nav-site-finder")).toHaveCount(0);
    await revealScrollDrivenSections(page);
    await page.screenshot({
      path: testInfo.outputPath("ds-01-public-homepage.png"),
      fullPage: true,
      caret: "initial",
    });
  });

  test("primary CTA enters the explicit workspace route", async ({ page }, testInfo) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    const cta = page.getByRole("link", { name: "Analyze a Lot" }).first();
    await expect(cta).toHaveAttribute("href", "/workspace");
    await cta.click();

    await expect(page).toHaveURL(/\/workspace(?:\?mode=lookup)?$/);
    await expect(page.getByTestId("lookup-input")).toBeVisible();
    await expect(page.getByTestId("sidebar-nav-site-finder")).toBeVisible();
    await expect
      .poll(() =>
        page.getByTestId("lookup-input").evaluate((element) => {
          const form = element.closest("form");
          return form ? Number.parseFloat(getComputedStyle(form).opacity) : 0;
        }),
      )
      .toBe(1);
    await page.screenshot({
      path: testInfo.outputPath("ds-02-workspace.png"),
      fullPage: true,
      caret: "initial",
    });
  });
});
