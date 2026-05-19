import {
  test,
  expect,
  gotoHome,
  switchToAgent,
  runLookupFlow,
  stubAnalyzeStream,
  stubAgentChatErrorSse,
} from "./helpers";

test.describe("Canonical mutation lane", () => {
  test("lookup timeout shows retry affordance", async ({ page }) => {
    await gotoHome(page);
    await stubAnalyzeStream(page, {
      statuses: [
        { step: "geocoding", message: "Resolving address...", complete: false },
      ],
      error: {
        detail: "Request timed out after 120s",
        error_type: "timeout",
      },
    });

    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");

    await expect(page.getByTestId("report-error")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("report-retry-button")).toBeVisible();
  });

  test("lookup bad address shows actionable recovery", async ({ page }) => {
    await gotoHome(page);

    const input = page.getByTestId("lookup-input");
    await input.click();
    await input.pressSequentially("hello world", { delay: 8 });
    await expect(input).toHaveValue("hello world");
    await expect(page.getByTestId("send-button")).toBeEnabled();
    await page.getByTestId("send-button").click();

    await expect(
      page.getByText("Please enter a street address to run a lookup analysis"),
    ).toBeVisible();
    await expect(page.getByTestId("deal-type-selector")).toHaveCount(0);
  });

  test("lookup backend unavailable shows actionable degraded message", async ({ page }) => {
    await gotoHome(page);
    await stubAnalyzeStream(page, {
      statuses: [
        { step: "geocoding", message: "Resolving address...", complete: false },
      ],
      error: {
        detail:
          "Analysis is temporarily unavailable because the data backend is offline. Please try again shortly.",
        error_type: "backend_unavailable",
      },
    });

    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");

    await expect(page.getByTestId("report-error")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/analysis backend is temporarily offline/i)).toBeVisible();
    await expect(page.getByText(/please try again shortly/i)).toBeVisible();
    await expect(page.getByTestId("report-retry-button")).toBeVisible();
    await expect(page.getByText(/i couldn't analyze that address/i)).toHaveCount(0);
    await expect(page.getByText(/connection refused/i)).toHaveCount(0);
  });

  test("lookup backend unavailable retry reissues the analysis request", async ({ page }) => {
    await gotoHome(page);

    let analyzeCalls = 0;
    await page.route("**/api/v1/analyze/stream", async (route) => {
      analyzeCalls += 1;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          `event: status\ndata: ${JSON.stringify({ step: "geocoding", message: "Resolving address...", complete: false })}\n\n`,
          `event: error\ndata: ${JSON.stringify({ detail: "Analysis is temporarily unavailable because the data backend is offline. Please try again shortly.", error_type: "backend_unavailable" })}\n\n`,
        ].join(""),
      });
    });

    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");
    await expect(page.getByTestId("report-retry-button")).toBeVisible({ timeout: 15_000 });

    await page.getByTestId("report-retry-button").click();
    await expect
      .poll(() => analyzeCalls, { timeout: 15_000 })
      .toBe(2);
    await expect(page.getByTestId("report-retry-button")).toBeVisible();
  });

  test("agent chat error stays deterministic", async ({ page }) => {
    await gotoHome(page);
    await switchToAgent(page);

    await stubAgentChatErrorSse(page, "LLM returned empty response");

    await page.getByTestId("agent-input").fill("What is the max height for RM-25?");
    await page.getByTestId("send-button").click();

    await expect(page.getByTestId("report-error")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("LLM returned empty response")).toBeVisible();
  });

  test("agent chat missing credentials shows actionable recovery", async ({ page }) => {
    await gotoHome(page);
    await switchToAgent(page);

    await stubAgentChatErrorSse(
      page,
      "Chat is temporarily unavailable because no LLM credentials are configured. Set OPENAI_API_KEY or OPENAI_ACCESS_TOKEN to enable agent responses.",
    );

    await page.getByTestId("agent-input").fill("What is the max height for RM-25?");
    await page.getByTestId("send-button").click();

    await expect(page.getByTestId("report-error")).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText(/no LLM credentials are configured/i),
    ).toBeVisible();
    await expect(page.getByText(/OPENAI_API_KEY/i)).toBeVisible();
  });
});
