import { test, expect } from "./fixtures";

test.describe("sidebar navigation", () => {
  test("sidebar items are clickable and switch between lookup and agent modes", async ({ page }) => {
    if (process.env.PLOTLOT_QUALITY_MUTATION === "analyses-label") {
      await page.addInitScript(() => {
        window.addEventListener("DOMContentLoaded", () => {
          const mutate = () => {
            const label = document.querySelector(
              '[data-testid="sidebar-nav-analyses"] span:last-child',
            );
            if (label && label.textContent !== "Analysis archive") {
              label.textContent = "Analysis archive";
            }
          };
          mutate();
          new MutationObserver(mutate).observe(document.body, {
            childList: true,
            subtree: true,
          });
        });
      });
    }

    await page.goto("/workspace");

    await expect(page.getByTestId("lookup-input")).toBeVisible();

    const harnessWorkspace = page.getByTestId("sidebar-nav-harness-workspace");
    await harnessWorkspace.click();
    await expect(page.getByTestId("agent-input")).toBeVisible();
    await expect(harnessWorkspace).toHaveAttribute("aria-current", "page");

    const analyses = page.getByTestId("sidebar-nav-analyses");
    await expect(analyses).toContainText("Analyses");
    await analyses.click();
    await expect(page).toHaveURL(/\/analyses$/);
    await expect(page.getByRole("heading", { name: "Analyses" })).toBeVisible();
    await expect(analyses).toHaveAttribute("aria-current", "page");

    const siteFinder = page.getByTestId("sidebar-nav-site-finder");
    await siteFinder.click();
    await expect(page.getByTestId("lookup-input")).toBeVisible();
    await expect(page).toHaveURL(/\/workspace\?mode=lookup$/);
    await expect(siteFinder).toHaveAttribute("aria-current", "page");

    const connectors = page.getByTestId("sidebar-nav-connectors");
    await connectors.click();
    await expect(page.getByTestId("connectors-page")).toBeVisible({ timeout: 30_000 });
    await expect(page).toHaveURL(/\/connectors$/, { timeout: 30_000 });
    await expect(connectors).toHaveAttribute("aria-current", "page");
  });
});
