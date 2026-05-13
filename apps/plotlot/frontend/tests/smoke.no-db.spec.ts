import {
  test,
  expect,
  gotoHome,
  switchToAgent,
  runLookupFlow,
  stubAnalyzeStream,
} from "./helpers";

test.describe("Canonical no-db smoke", () => {
  test("lookup welcome exposes canonical selectors", async ({ page }) => {
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

  test("lookup gate and pipeline start work without db-backed assertions", async ({ page }) => {
    await gotoHome(page);
    await stubAnalyzeStream(page, {
      statuses: [
        { step: "geocoding", message: "Resolving address...", complete: false },
      ],
    });

    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");

    await expect(page.getByTestId("pipeline-stepper")).toBeVisible();
    await expect(page.getByTestId("pipeline-step-geocoding")).toBeVisible();
    await expect(page.getByTestId("pipeline-step-current")).toContainText(
      "Geocoding",
    );
  });
});
