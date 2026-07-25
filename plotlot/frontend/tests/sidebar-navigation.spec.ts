import { test, expect } from "@playwright/test";

test.describe("sidebar navigation", () => {
  test("sidebar items are clickable and switch between lookup and agent modes", async ({ page }) => {
    await page.goto("/workspace");

    await expect(page.getByTestId("lookup-input")).toBeVisible();

    const harnessWorkspace = page.getByTestId("sidebar-nav-harness-workspace");
    await harnessWorkspace.click();
    await expect(page.getByTestId("agent-input")).toBeVisible();
    await expect(harnessWorkspace).toHaveAttribute("aria-current", "page");

    const analyses = page.getByTestId("sidebar-nav-analyses");
    await analyses.click();
    await expect(page).toHaveURL(/\/analyses$/);
    await expect(
      page.getByRole("heading", { name: "Shared harness run" }),
    ).toBeVisible();
    await expect(analyses).toHaveAttribute("aria-current", "page");

    const siteFinder = page.getByTestId("sidebar-nav-site-finder");
    await siteFinder.click();
    await expect(page.getByTestId("lookup-input")).toBeVisible();
    await expect(page).toHaveURL(/\/workspace\?mode=lookup$/);
    await expect(siteFinder).toHaveAttribute("aria-current", "page");

    const connectors = page.getByTestId("sidebar-nav-connectors");
    await connectors.click();
    await expect(page).toHaveURL(/\/connectors$/);
    await expect(page.getByRole("heading", { name: "Connectors" })).toBeVisible();
    await expect(connectors).toHaveAttribute("aria-current", "page");
  });
});
