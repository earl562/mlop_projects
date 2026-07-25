import { test, expect } from "./fixtures";

test.describe("PlotLot design system", () => {
  test("root route presents the restored public homepage", async ({ page }, testInfo) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

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
    await page.screenshot({ path: testInfo.outputPath("ds-01-public-homepage.png"), fullPage: true });
  });

  test("primary CTA enters the explicit workspace route", async ({ page }) => {
    await page.goto("/");
    const cta = page.getByRole("link", { name: "Analyze a Lot" }).first();
    await expect(cta).toHaveAttribute("href", "/workspace");
    await page.goto("/workspace");

    await expect(page).toHaveURL(/\/workspace(?:\?mode=lookup)?$/);
    await expect(page.getByTestId("lookup-input")).toBeVisible();
    await expect(page.getByTestId("sidebar-nav-site-finder")).toBeVisible();
  });
});
