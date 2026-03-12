import { test, expect } from "@playwright/test";

/**
 * Phase 6B UAT — De-Wordification, Floor Plans, Address Autocomplete
 *
 * These tests validate the Phase 6B changes:
 *  - Concise pipeline step descriptions (telegraphic, not verbose)
 *  - Short one-liner assistant message after analysis
 *  - No summary markdown block in report card
 *  - No Development Summary section
 *  - Compact Property Type badge replaces Financial Summary
 *  - Professional floor plans with new room types
 *  - Address autocomplete threshold lowered to 2 chars
 */

const TEST_ADDRESS = "4341 NW 183rd St, Miami Gardens, FL 33055";
const SCREENSHOT_DIR = "tests/screenshots";

test.describe("Phase 6B UAT", () => {
  // --------------------------------------------------------------------------
  // UAT-1: Welcome state renders
  // --------------------------------------------------------------------------
  test("UAT-1: Welcome state renders correctly", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });

    // Floating pill nav with "PlotLot" and "Beta"
    await expect(page.locator("nav").filter({ hasText: "PlotLot" })).toBeVisible();
    await expect(page.getByText("Beta")).toBeVisible();

    // Serif heading
    await expect(page.getByText("Analyze any property")).toBeVisible();

    // Input bar with placeholder
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await expect(input).toBeVisible();

    // Suggestion chips visible
    await expect(page.getByText("Analyze a property in Miami Gardens")).toBeVisible();
    await expect(page.getByText("Find vacant lots in Miami-Dade")).toBeVisible();

    // Send button disabled when empty
    const sendBtn = page.getByRole("button", { name: "Send message" });
    await expect(sendBtn).toBeDisabled();

    // Screenshot
    await page.screenshot({ path: `${SCREENSHOT_DIR}/uat-6b-01-welcome.png`, fullPage: true });
  });

  // --------------------------------------------------------------------------
  // UAT-2: Pipeline step descriptions are telegraphic
  // --------------------------------------------------------------------------
  test("UAT-2: Pipeline step descriptions are telegraphic", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/", { waitUntil: "networkidle" });

    // Collect all text that appears during pipeline via a mutation observer
    // This captures transient step labels even if the pipeline completes quickly (cached)
    await page.evaluate(() => {
      (window as unknown as Record<string, string[]>).__capturedText = [];
      const observer = new MutationObserver(() => {
        const texts = document.body.innerText;
        (window as unknown as Record<string, string[]>).__capturedText.push(texts);
      });
      observer.observe(document.body, { childList: true, subtree: true, characterData: true });
      (window as unknown as Record<string, MutationObserver>).__observer = observer;
    });

    // Submit address
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill(TEST_ADDRESS);
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for pipeline step counter to appear
    await expect(page.getByText(/Step \d+ of 6/)).toBeVisible({ timeout: 15_000 });

    // Screenshot the pipeline running
    await page.screenshot({ path: `${SCREENSHOT_DIR}/uat-6b-02-pipeline-running.png`, fullPage: true });

    // Wait for pipeline to complete (zoning district appears in report)
    await expect(
      page.locator(".font-display").filter({ hasText: /R-/ }),
    ).toBeVisible({ timeout: 120_000 });

    // Disconnect observer and collect captured text
    const allCapturedText = await page.evaluate(() => {
      (window as unknown as Record<string, MutationObserver>).__observer?.disconnect();
      return (window as unknown as Record<string, string[]>).__capturedText.join("\n");
    });

    // Verify that at some point during the pipeline, the short step labels appeared
    // These are the STEP_LABELS defined in AnalysisStream.tsx
    expect(allCapturedText).toContain("Step 1 of 6");

    // Verify verbose descriptions NEVER appeared in any captured snapshot
    const verboseDescriptions = [
      "Establishing connection to PlotLot server",
      "Looking up property information from county records",
      "Analyzing zoning ordinances and extracting dimensional",
    ];

    for (const verbose of verboseDescriptions) {
      expect(allCapturedText).not.toContain(verbose);
    }
  });

  // --------------------------------------------------------------------------
  // UAT-3: Analysis completes with concise assistant message
  // --------------------------------------------------------------------------
  test("UAT-3: Analysis completes with concise assistant message", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/", { waitUntil: "networkidle" });

    // Submit address
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill(TEST_ADDRESS);
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for report to load (zoning district R- visible)
    await expect(page.locator(".font-display").filter({ hasText: /R-/ })).toBeVisible({
      timeout: 120_000,
    });

    // Verify assistant message is the short one-liner
    await expect(page.getByText("full zoning analysis")).toBeVisible({ timeout: 10_000 });

    // Verify NO verbose summary with "governed by" text in assistant message
    // (old verbose messages contained phrasing like "governed by", "zoning district allows", etc.)
    const assistantMessages = page.locator('[class*="text-sm"]').filter({ hasText: /governed by/ });
    await expect(assistantMessages).toHaveCount(0);
  });

  // --------------------------------------------------------------------------
  // UAT-4: Report card has NO summary markdown block
  // --------------------------------------------------------------------------
  test("UAT-4: Report card has NO summary markdown block", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/", { waitUntil: "networkidle" });

    // Submit address
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill(TEST_ADDRESS);
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for report
    await expect(page.locator(".font-display").filter({ hasText: /R-/ })).toBeVisible({
      timeout: 120_000,
    });

    // Screenshot the report card top
    await page.screenshot({ path: `${SCREENSHOT_DIR}/uat-6b-03-report-card-top.png`, fullPage: true });

    // Zoning district IS displayed (e.g. "RS-1" or similar R-prefixed)
    const zoningDistrict = page.locator(".font-display").filter({ hasText: /R-/ });
    await expect(zoningDistrict).toBeVisible();

    // "DIMENSIONAL STANDARDS" section pill exists
    await expect(page.getByText("Dimensional Standards")).toBeVisible();

    // No large summary prose block — check that there is no paragraph containing
    // typical summary text like "Summary", "This property is governed", "Overview"
    const summaryProse = page.locator("h2, h3").filter({ hasText: /^Summary$/i });
    await expect(summaryProse).toHaveCount(0);
  });

  // --------------------------------------------------------------------------
  // UAT-5: Report card has NO Development Summary section
  // --------------------------------------------------------------------------
  test("UAT-5: Report card has NO Development Summary section", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/", { waitUntil: "networkidle" });

    // Submit address
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill(TEST_ADDRESS);
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for report
    await expect(page.locator(".font-display").filter({ hasText: /R-/ })).toBeVisible({
      timeout: 120_000,
    });

    // "Development Summary" text should NOT appear in the report
    await expect(page.getByText("Development Summary")).not.toBeVisible();

    // "MAX ALLOWABLE UNITS" (DensityBreakdown) DOES appear
    await expect(page.getByText("Max Allowable Units")).toBeVisible();
  });

  // --------------------------------------------------------------------------
  // UAT-6: Financial Summary replaced with compact Property Type
  // --------------------------------------------------------------------------
  test("UAT-6: Financial Summary replaced with compact Property Type", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/", { waitUntil: "networkidle" });

    // Submit address
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill(TEST_ADDRESS);
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for report
    await expect(page.locator(".font-display").filter({ hasText: /R-/ })).toBeVisible({
      timeout: 120_000,
    });

    // "Property Type" section pill exists
    await expect(page.getByText("Property Type")).toBeVisible();

    // Property type badge appears (one of the known property types)
    const propertyTypeBadge = page.locator("span").filter({
      hasText: /Single-Family|Land \/ Development|Multifamily|Commercial MF|Commercial/,
    });
    await expect(propertyTypeBadge.first()).toBeVisible();

    // NO verbose financial text like "Provide purchase price and ARV"
    await expect(page.getByText("Provide purchase price and ARV")).not.toBeVisible();
    await expect(page.getByText("Financial Summary")).not.toBeVisible();
  });

  // --------------------------------------------------------------------------
  // UAT-7: Floor plan section exists
  // --------------------------------------------------------------------------
  test("UAT-7: Floor plan section exists", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/", { waitUntil: "networkidle" });

    // Submit address
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill(TEST_ADDRESS);
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for report
    await expect(page.locator(".font-display").filter({ hasText: /R-/ })).toBeVisible({
      timeout: 120_000,
    });

    // "Floor Plan" section pill exists in the report
    const floorPlanPill = page.getByText("Floor Plan", { exact: true });
    await expect(floorPlanPill).toBeVisible();

    // Click to expand it (defaultOpen is false)
    await floorPlanPill.click();

    // Wait for SVG content to render
    await expect(page.locator("svg").filter({ has: page.locator("rect") }).last()).toBeVisible({
      timeout: 5_000,
    });

    // Screenshot the floor plan
    await page.screenshot({ path: `${SCREENSHOT_DIR}/uat-6b-04-floor-plan.png`, fullPage: true });
  });

  // --------------------------------------------------------------------------
  // UAT-8: DensityBreakdown shows buildable footprint
  // --------------------------------------------------------------------------
  test("UAT-8: DensityBreakdown shows buildable footprint", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/", { waitUntil: "networkidle" });

    // Submit address
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill(TEST_ADDRESS);
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for report
    await expect(page.locator(".font-display").filter({ hasText: /R-/ })).toBeVisible({
      timeout: 120_000,
    });

    // Verify "buildable footprint" text appears in DensityBreakdown area
    await expect(page.getByText(/buildable footprint/i)).toBeVisible();

    // Verify "GOVERNING" badge appears (exact match for the uppercase badge)
    await expect(page.getByText("GOVERNING", { exact: true })).toBeVisible();
  });

  // --------------------------------------------------------------------------
  // UAT-9: Follow-up suggestions appear after report
  // --------------------------------------------------------------------------
  test("UAT-9: Follow-up suggestions appear after report", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/", { waitUntil: "networkidle" });

    // Submit address
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill(TEST_ADDRESS);
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for report
    await expect(page.locator(".font-display").filter({ hasText: /R-/ })).toBeVisible({
      timeout: 120_000,
    });

    // Verify "What can I build on this lot?" chip visible
    await expect(page.getByText("What can I build on this lot?")).toBeVisible();

    // Verify follow-up input placeholder says "Ask about this property's zoning..."
    await expect(page.getByPlaceholder("Ask about this property's zoning...")).toBeVisible();
  });

  // --------------------------------------------------------------------------
  // UAT-10: New analysis resets properly
  // --------------------------------------------------------------------------
  test("UAT-10: New analysis resets properly", async ({ page }) => {
    test.setTimeout(180_000);
    await page.goto("/", { waitUntil: "networkidle" });

    // Submit address to enter conversation state
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill(TEST_ADDRESS);
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for at least the pipeline to start
    await expect(page.getByText(/Step \d+ of 6/)).toBeVisible({ timeout: 15_000 });

    // Wait a beat to ensure pipeline is in progress (avoids race condition)
    await page.waitForTimeout(500);

    // Click "New analysis" button
    await page.getByText("New analysis").click();

    // Verify welcome state returns with "Analyze any property" heading
    // Use a generous timeout to allow for React state reset and re-render
    await expect(page.getByText("Analyze any property")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByPlaceholder("Enter an address or ask a question...")).toBeVisible();

    // Welcome suggestion chips should be back (these are different from follow-up chips)
    await expect(page.getByText("Analyze a property in Miami Gardens")).toBeVisible({ timeout: 5_000 });
  });
});
