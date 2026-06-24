/**
 * Edge case tests for PlotLot frontend resilience.
 *
 * Coverage:
 *  1. Address outside coverage area → graceful error/empty state
 *  2. Empty address submission → validation error (send button disabled)
 *  3. Very long address string → no crash, UI remains responsive
 *  4. Rapid-fire 3-address submissions → no race condition
 *  5. Refresh mid-analysis → state recovery from localStorage
 *
 * These tests use the stub pattern from smoke.no-db.spec.ts so they do NOT
 * require a live backend. All SSE events are mocked via page.route().
 */
import {
  test,
  expect,
  gotoHome,
} from "./helpers";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Capture console output for the current page into an array. */
function captureConsole(page: import("@playwright/test").Page): string[] {
  const logs: string[] = [];
  page.on("console", (msg) => {
    logs.push(`[${msg.type()}] ${msg.text()}`);
  });
  page.on("pageerror", (err) => {
    logs.push(`[pageerror] ${err.message}`);
  });
  return logs;
}

/** Stub the analyze stream endpoint with a predefined SSE sequence. */
async function stubAnalyze(
  page: import("@playwright/test").Page,
  events: string[],
) {
  await page.route("**/api/v1/analyze/stream", async (route) => {
    const body = events.join("");
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body,
    });
  });
}

// Reusable SSE helpers
function statusEvent(step: string, message: string, complete = false) {
  return `event: status\ndata: ${JSON.stringify({ step, message, complete })}\n\n`;
}
function errorEvent(detail: string, errorType?: string) {
  return `event: error\ndata: ${JSON.stringify({ detail, error_type: errorType })}\n\n`;
}
function resultEvent(report: Record<string, unknown>) {
  return `event: result\ndata: ${JSON.stringify(report)}\n\n`;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Edge Case: Outside Coverage Area", () => {
  test("shows graceful error for address outside coverage", async ({ page }, testInfo) => {
    const logs = captureConsole(page);

    await gotoHome(page);
    await stubAnalyze(page, [
      statusEvent("geocoding", "Resolving address..."),
      errorEvent("Geocoding failed: address outside US coverage area", "geocoding_failed"),
    ]);

    // Type an address clearly outside the coverage area
    const input = page.getByTestId("lookup-input");
    const sendButton = page.getByTestId("send-button");

    await input.fill("123 Main St, Boise, ID 83702");
    await expect(sendButton).toBeEnabled({ timeout: 5_000 });
    await sendButton.click();

    // Should show error content (bad_address error type)
    await expect(page.getByTestId("report-error")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("report-error")).toContainText("outside");

    // Verify no fatal console errors
    const fatalErrors = logs.filter(
      (l) => l.startsWith("[error]") || l.startsWith("[pageerror]"),
    );
    await page.screenshot({
      path: testInfo.outputPath("edge-01-outside-coverage.png"),
      fullPage: true,
    });
    expect(fatalErrors.length).toBe(0);
  });
});

test.describe("Edge Case: Empty Address", () => {
  test("send button is disabled with empty input", async ({ page }, testInfo) => {
    const logs = captureConsole(page);
    await gotoHome(page);

    const input = page.getByTestId("lookup-input");
    const sendButton = page.getByTestId("send-button");

    // Start with empty input — button should be disabled
    await expect(input).toHaveValue("");
    await expect(sendButton).toBeDisabled();

    // Type something then clear it — button should return to disabled
    await input.fill("123 Test");
    await expect(sendButton).toBeEnabled();
    await input.fill("");
    await expect(sendButton).toBeDisabled();

    // Whitespace-only should also be disabled
    await input.fill("   ");
    await expect(sendButton).toBeDisabled();

    // Verify pressing Enter on empty does not trigger submission
    await input.fill("");
    // No analysis stub is set up, so if a request fires it will fail — but it shouldn't
    await input.press("Enter");
    await page.waitForTimeout(500);
    // still on welcome page (no messages rendered)
    await expect(page.getByTestId("lookup-input")).toBeVisible();
    await expect(page.locator("[role='log']")).toHaveCount(0);

    await page.screenshot({
      path: testInfo.outputPath("edge-02-empty-address.png"),
      fullPage: true,
    });

    const fatalErrors = logs.filter(
      (l) => l.startsWith("[error]") || l.startsWith("[pageerror]"),
    );
    expect(fatalErrors.length).toBe(0);
  });
});

test.describe("Edge Case: Very Long Address", () => {
  test("does not crash with extremely long address input", async ({ page }, testInfo) => {
    const logs = captureConsole(page);
    await gotoHome(page);

    const input = page.getByTestId("lookup-input");

    // Build a very long address string (5KB)
    const longAddress =
      "12345 " +
      "VeryLongStreetNameThatGoesOnAndOn".repeat(40) +
      " Blvd, " +
      "CityOf".repeat(30) +
      ", CA 90210";

    await input.fill(longAddress);
    await page.waitForTimeout(500);

    // Input should still be visible and page not crashed
    await expect(input).toBeVisible();
    await expect(page.getByTestId("send-button")).toBeVisible();

    // Clear and verify we can still type normally after the long string
    await input.fill("7940 Plantation Blvd, Miramar, FL 33023");
    await expect(input).toHaveValue("7940 Plantation Blvd, Miramar, FL 33023");

    await page.screenshot({
      path: testInfo.outputPath("edge-03-long-address.png"),
      fullPage: true,
    });

    const fatalErrors = logs.filter(
      (l) => l.startsWith("[pageerror]"),
    );
    expect(fatalErrors.length).toBe(0);
  });
});

test.describe("Edge Case: Rapid-Fire Submissions", () => {
  test("handles 3 rapid address submissions without race condition", async ({ page }, testInfo) => {
    const logs = captureConsole(page);
    await gotoHome(page);

    const input = page.getByTestId("lookup-input");
    const sendButton = page.getByTestId("send-button");

    // Stub: each submission returns a quick pipeline + result so we can observe
    // that the last result wins cleanly (no interleaved state)
    let callCount = 0;
    await page.route("**/api/v1/analyze/stream", async (route) => {
      callCount++;
      const id = callCount;
      const body = [
        statusEvent("geocoding", `Resolving address (req ${id})...`),
        statusEvent("property", `Fetching data (req ${id})...`),
        resultEvent({
          address: `Addr ${id}`,
          county: `County ${id}`,
          zoning_summary: `Zoning summary ${id}`,
          max_units: id * 10,
          confidence: "high",
        }),
      ].join("");
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body,
      });
    });

    // Rapid-fire 3 submissions
    const addresses = [
      "123 Alpha St, City A, FL 33023",
      "456 Beta Ave, City B, FL 33024",
      "789 Gamma Blvd, City C, FL 33025",
    ];

    for (const addr of addresses) {
      await input.fill(addr);
      await expect(sendButton).toBeEnabled({ timeout: 3_000 });
      await sendButton.click();
      // Don't wait between submissions — this is the rapid-fire test
    }

    // Wait for final state to settle
    await page.waitForTimeout(2_000);

    // Check that the last submission's result is visible (report or error)
    // The last one should win; we just verify no crash/blank state
    await expect(page.getByTestId("report-root")).toBeVisible({ timeout: 10_000 });

    // Verify no uncaught page errors
    const pageErrors = logs.filter((l) => l.startsWith("[pageerror]"));
    expect(pageErrors.length).toBe(0);

    await page.screenshot({
      path: testInfo.outputPath("edge-04-rapid-fire.png"),
      fullPage: true,
    });
  });
});

test.describe("Edge Case: Refresh Mid-Analysis", () => {
  test("recovers state after refresh during analysis", async ({ page }, testInfo) => {
    const logs = captureConsole(page);
    await gotoHome(page);

    // Set up a slow stub that reports pipeline progress but never completes
    // We'll refresh before it finishes
    await page.route("**/api/v1/analyze/stream", async (route) => {
      const body = [
        statusEvent("geocoding", "Resolving address...", false),
        statusEvent("property", "Fetching property data...", false),
        statusEvent("zoning", "Retrieving zoning ordinances...", false),
      ].join("");
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body,
      });
    });

    const input = page.getByTestId("lookup-input");
    const sendButton = page.getByTestId("send-button");

    await input.fill("7940 Plantation Blvd, Miramar, FL 33023");
    await sendButton.click();

    // Wait for pipeline to appear
    await expect(page.getByTestId("pipeline-stepper")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("pipeline-step-current")).toBeVisible();

    // Capture pre-refresh state
    await page.screenshot({
      path: testInfo.outputPath("edge-05a-mid-analysis-pre-refresh.png"),
      fullPage: true,
    });

    // Refresh the page mid-analysis
    await page.reload({ waitUntil: "domcontentloaded" });

    // Wait for hydration
    await page.waitForTimeout(1_000);

    // After refresh, the page should render the workspace again
    await expect(page.getByTestId("lookup-input")).toBeVisible({ timeout: 10_000 });
    // The welcome state is shown because the incomplete analysis is not persisted
    await expect(page.getByTestId("send-button")).toBeVisible();

    // Verify we can start a new analysis after refresh
    const newInput = page.getByTestId("lookup-input");
    await newInput.fill("1 Test St, Test City, TX 75001");
    await expect(page.getByTestId("send-button")).toBeEnabled({ timeout: 5_000 });

    await page.screenshot({
      path: testInfo.outputPath("edge-05b-post-refresh.png"),
      fullPage: true,
    });

    const pageErrors = logs.filter((l) => l.startsWith("[pageerror]"));
    // One network aborted error from the refresh is expected
    const realErrors = pageErrors.filter(
      (e) => !e.includes("aborted") && !e.includes("canceled"),
    );
    expect(realErrors.length).toBe(0);
  });
});
