import {
  test,
  expect,
  gotoLanding,
  gotoHome,
  switchToAgent,
  runLookupFlow,
  stubAnalyzeStream,
} from "./helpers";

test.describe("Canonical no-db smoke", () => {
  test("public homepage is restored at root without workspace chrome", async ({ page }) => {
    await gotoLanding(page);

    await expect(
      page.getByRole("heading", {
        name: "See What Fits.",
      }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "Analyze a Lot" }).first()).toBeVisible();
    await expect(page.getByTestId("lookup-input")).toHaveCount(0);
    await expect(page.getByTestId("sidebar-nav-site-finder")).toHaveCount(0);
  });

  test("analyze route renders the PI console without workspace chrome", async ({ page }) => {
    await page.goto("/analyze", { waitUntil: "domcontentloaded" });

    await expect(page.getByRole("heading", { name: "Land-use intelligence console." })).toBeVisible();
    await expect(page.getByTestId("analyze-computer-card")).toBeVisible();
    await expect(page.getByTestId("analyze-status-card")).toBeVisible();
    await expect(page.getByTestId("analyze-plan-card")).toBeVisible();
    await expect(page.getByTestId("analyze-evidence-card")).toBeVisible();
    await expect(page.getByTestId("analyze-actions-card")).toBeVisible();
    await expect(page.getByTestId("sidebar-nav-site-finder")).toHaveCount(0);
  });

  test("workspace lookup welcome exposes canonical selectors", async ({ page }) => {
    await gotoHome(page);

    await expect(page.getByTestId("lookup-input")).toBeVisible();
    await expect(page.getByTestId("send-button")).toBeDisabled();
    await expect(page.getByRole("button", { name: "Lookup" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Agent" })).toBeVisible();
  });

  test("agent welcome exposes canonical selectors without autocomplete", async ({ page }) => {
    await gotoHome(page);
    await switchToAgent(page);

    await expect(page.getByTestId("agent-input")).toBeVisible();
    await page.getByTestId("agent-input").fill("1234 NW");
    await page.waitForTimeout(400);
    await expect(page.getByTestId("lookup-suggestions")).toHaveCount(0);
  });

  test("lookup gate handles a terminal backend response without a database", async ({ page }) => {
    await gotoHome(page);
    await stubAnalyzeStream(page, {
      statuses: [
        { step: "geocoding", message: "Resolving address...", complete: false },
      ],
      error: {
        detail: "Recorded no-database response",
        error_type: "backend_unavailable",
      },
    });

    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");

    await expect(page.getByTestId("report-error")).toBeVisible();
    await expect(page.getByText(/analysis backend is temporarily offline/i)).toBeVisible();
    await expect(page.getByTestId("report-retry-button")).toBeVisible();
  });
});
