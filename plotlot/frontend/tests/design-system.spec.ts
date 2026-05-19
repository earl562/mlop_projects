import { test, expect } from "@playwright/test";

test.describe("PlotLot design system", () => {
  test("root route presents the restored public homepage", async ({ page }, testInfo) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    await expect(page.getByTestId("public-homepage")).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: "PlotLot turns parcel uncertainty into buildable answers.",
      }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "Start a lookup" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open workspace" }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Capabilities" })).toHaveCount(0);
    await expect(page.getByText("A public front door that still leads into real analysis.")).toBeVisible();
    await expect(page.getByTestId("sidebar-nav-site-finder")).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath("ds-01-public-homepage.png"), fullPage: true });
  });

  test("primary CTA enters the explicit workspace route", async ({ page }) => {
    await page.goto("/");
    const cta = page.getByRole("link", { name: "Start a lookup" });
    await expect(cta).toHaveAttribute("href", "/workspace?mode=lookup");
    await page.goto("/workspace?mode=lookup");

    await expect(page).toHaveURL(/\/workspace\?mode=lookup$/);
    await expect(page.getByTestId("lookup-input")).toBeVisible();
    await expect(page.getByTestId("sidebar-nav-site-finder")).toBeVisible();
  });
});
