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
    await page.route("**/api/v1/autocomplete**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ suggestions: [] }),
      }),
    );

    const input = page.getByTestId("lookup-input");
    const sendButton = page.getByTestId("send-button");
    await input.click();
    await input.pressSequentially("hello world", { delay: 20 });
    await expect(input).toHaveValue("hello world");
    await expect(sendButton).toBeEnabled();
    await sendButton.click();

    await expect(
      page.getByText("Please enter a street address to run a lookup analysis"),
    ).toBeVisible();
    await expect(page.getByTestId("deal-type-selector")).toHaveCount(0);
    await expect(page.getByTestId("pipeline-approval-card")).toHaveCount(0);
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

  test("lookup recovers with sync fallback after stream connection failure", async ({
    page,
  }, testInfo) => {
    testInfo.annotations.push(
      { type: "allow-critical-request-failure", description: "The stream transport is intentionally aborted to exercise sync recovery." },
      { type: "allow-console-error", description: "Chromium logs the intentionally aborted stream request." },
    );
    await gotoHome(page);

    await page.route("**/health", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "healthy",
          capabilities: { db_backed_analysis_ready: true },
        }),
      });
    });

    await page.route("**/api/v1/analyze/stream", async (route) => {
      await route.abort("failed");
    });

    await page.route("**/api/v1/analyze", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          address: "7940 Plantation Blvd, Miramar, FL 33023",
          formatted_address: "7940 Plantation Blvd, Miramar, FL 33023",
          municipality: "Miramar",
          county: "Broward",
          lat: 26.025,
          lng: -80.251,
          zoning_district: "RS5",
          zoning_description: "Single Family Residential",
          allowed_uses: ["Single-family residential"],
          conditional_uses: [],
          prohibited_uses: [],
          setbacks: { front: "25 ft", side: "7.5 ft", rear: "20 ft" },
          max_height: "35 ft",
          max_density: "8 du/ac",
          floor_area_ratio: "0.5",
          lot_coverage: "40%",
          min_lot_size: "5,000 sqft",
          parking_requirements: "2 spaces per dwelling unit",
          property_record: null,
          numeric_params: null,
          density_analysis: {
            max_units: 1,
            governing_constraint: "Lot area per unit",
            constraints: [],
            lot_size_sqft: 5000,
            buildable_area_sqft: null,
            lot_width_ft: null,
            lot_depth_ft: null,
            max_gla_sqft: null,
            confidence: "high",
            notes: [],
          },
          comp_analysis: null,
          pro_forma: null,
          summary: "Recovered via sync fallback after stream connection failure.",
          sources: [],
          confidence: "high",
          source_refs: [],
          confidence_warning: null,
          suggested_next_steps: [],
        }),
      });
    });

    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");

    await expect(page.getByTestId("report-root")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Miramar, Broward County")).toBeVisible();
    await expect(page.getByText(/i couldn't analyze that address/i)).toHaveCount(0);
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
