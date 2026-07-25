import { test, expect } from "./fixtures";

test.describe("workspace route scaffolds", () => {
  test("analyze route renders the dedicated agent console", async ({ page }) => {
    await page.goto("/analyze");
    await expect(page.getByRole("heading", { name: "Land-use intelligence console." })).toBeVisible();
    await expect(page.getByTestId("analyze-task-timeline-card")).toBeVisible();
    await expect(page.getByTestId("agent-input")).toBeVisible();
  });

  test("workspace shell renders on explicit workspace route", async ({ page }) => {
    await page.goto("/workspace");
    await expect(page.getByTestId("lookup-input")).toBeVisible();
    await expect(page.getByTestId("sidebar-nav-site-finder")).toBeVisible();
  });

  test("projects routes render", async ({ page }) => {
    await page.goto("/projects");
    await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();

    await page.goto("/projects/project_1");
    await expect(page.getByRole("heading", { name: "Project" })).toBeVisible();

    await page.goto("/projects/project_1/sites/site_1");
    await expect(page.getByRole("heading", { name: "Site" })).toBeVisible();

    await page.goto("/projects/project_1/sites/site_1/analyses/analysis_1");
    await expect(page.getByRole("heading", { name: "Analysis" })).toBeVisible();
  });
});
