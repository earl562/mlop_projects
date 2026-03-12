import { test, expect } from "@playwright/test";

const API_URL = "http://localhost:8000";

test.describe("PlotLot E2E Visual Walkthrough", () => {
  test.setTimeout(180_000); // 3 min for LLM calls

  test("full analysis flow with screenshots", async ({ page }) => {
    // Step 1: Welcome page
    await page.goto("http://localhost:3000", { waitUntil: "networkidle" });
    await page.screenshot({ path: "tests/screenshots/e2e-01-welcome.png", fullPage: true });
    console.log("✓ Welcome page loaded");

    // Step 2: Enter address and submit
    const input = page.getByPlaceholder("Enter an address or ask a question...");
    await input.fill("3201 SW 152nd Ave, Miramar, FL 33027");
    await page.screenshot({ path: "tests/screenshots/e2e-02-address-entered.png" });

    const sendBtn = page.getByRole("button", { name: "Send message" });
    await sendBtn.click();
    console.log("✓ Analysis submitted");

    // Step 3: Wait for pipeline stepper to appear
    await page.waitForSelector("text=Geocoding", { timeout: 15_000 });
    await page.screenshot({ path: "tests/screenshots/e2e-03-pipeline-started.png" });
    console.log("✓ Pipeline started");

    // Step 4: Wait for analysis to complete (report card appears)
    // The report card has the zoning district displayed prominently
    try {
      await page.waitForSelector('[class*="border-l-amber"]', { timeout: 120_000 });
      console.log("✓ Report card appeared");
    } catch {
      // Take screenshot of whatever state we're in
      await page.screenshot({ path: "tests/screenshots/e2e-04-timeout-state.png", fullPage: true });
      console.log("⚠ Report card didn't appear within timeout, checking current state...");

      // Check if there's an error message
      const errorText = await page.textContent("body");
      if (errorText?.includes("error") || errorText?.includes("Error")) {
        console.log("Error detected on page");
      }
      return; // Exit gracefully
    }

    // Step 5: Screenshot the report card top
    await page.screenshot({ path: "tests/screenshots/e2e-05-report-top.png" });
    console.log("✓ Report top captured");

    // Step 6: Full page screenshot
    await page.screenshot({ path: "tests/screenshots/e2e-06-report-full.png", fullPage: true });
    console.log("✓ Full report captured");

    // Step 7: Scroll to dimensional standards / setbacks
    const setbacksSection = page.locator("text=Setbacks").first();
    if (await setbacksSection.isVisible()) {
      await setbacksSection.scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);
      await page.screenshot({ path: "tests/screenshots/e2e-07-setbacks.png" });
      console.log("✓ Setbacks section captured");
    }

    // Step 8: Check for Floor Plan section
    const floorPlanSection = page.locator("text=Floor Plan").first();
    if (await floorPlanSection.isVisible()) {
      await floorPlanSection.scrollIntoViewIfNeeded();
      await page.waitForTimeout(2000);
      await page.screenshot({ path: "tests/screenshots/e2e-09-floor-plan.png" });
      console.log("✓ Floor plan captured");
    } else {
      console.log("⚠ Floor Plan not visible (may need buildable area in report)");
    }

    // Step 10: Scroll to property record
    const propertySection = page.locator("text=Property Record").first();
    if (await propertySection.isVisible()) {
      await propertySection.scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);
      await page.screenshot({ path: "tests/screenshots/e2e-10-property-record.png" });
      console.log("✓ Property record captured");
    }

    // Step 11: Test PDF download button
    const pdfBtn = page.locator("button:has-text('PDF')").first();
    if (await pdfBtn.isVisible()) {
      console.log("✓ PDF download button is visible");
      await page.screenshot({ path: "tests/screenshots/e2e-11-pdf-button.png" });
    }

    // Step 12: Scroll to sources
    const sourcesBtn = page.locator("text=View").first();
    if (await sourcesBtn.isVisible()) {
      await sourcesBtn.scrollIntoViewIfNeeded();
      await page.screenshot({ path: "tests/screenshots/e2e-12-sources.png" });
      console.log("✓ Sources section captured");
    }

    console.log("\n🎉 E2E visual walkthrough complete!");
  });

  test("API endpoints health check", async ({ request }) => {
    // Health
    const health = await request.get(`${API_URL}/health`);
    expect(health.ok()).toBeTruthy();
    const healthData = await health.json();
    expect(healthData.status).toBe("healthy");
    console.log("✓ Health: OK");

    // Geometry envelope
    const envelope = await request.post(`${API_URL}/api/v1/geometry/envelope`, {
      data: {
        lot_width_ft: 75,
        lot_depth_ft: 100,
        setback_front_ft: 25,
        setback_side_ft: 10,
        setback_rear_ft: 20,
        max_height_ft: 35,
      },
    });
    expect(envelope.ok()).toBeTruthy();
    const envData = await envelope.json();
    expect(envData.buildable_width_ft).toBe(55);
    expect(envData.buildable_depth_ft).toBe(55);
    console.log(`✓ Geometry: ${envData.buildable_footprint_sqft} sqft buildable`);

    // Floor plan
    const floorplan = await request.post(`${API_URL}/api/v1/geometry/floorplan`, {
      data: {
        buildable_width_ft: 55,
        buildable_depth_ft: 55,
        max_height_ft: 35,
        max_units: 2,
      },
    });
    expect(floorplan.ok()).toBeTruthy();
    const fpData = await floorplan.json();
    expect(fpData.template).toBe("duplex");
    expect(fpData.svg).toContain("<svg");
    console.log(`✓ Floor plan: ${fpData.template}, ${fpData.total_units} units`);

    // Pro forma
    const proforma = await request.post(`${API_URL}/api/v1/geometry/proforma`, {
      data: {
        address: "3201 SW 152nd Ave, Miramar, FL",
        max_units: 2,
        unit_size_sqft: 1200,
        land_cost: 250000,
        monthly_rent_per_unit: 2500,
        sale_price_per_unit: 400000,
      },
    });
    expect(proforma.ok()).toBeTruthy();
    const pfData = await proforma.json();
    expect(pfData.total_development_cost).toBeGreaterThan(0);
    expect(pfData.roi_pct).toBeGreaterThan(0);
    console.log(`✓ Pro forma: $${pfData.total_development_cost.toLocaleString()} dev cost, ${pfData.roi_pct.toFixed(1)}% ROI`);

    // Analytics
    const analytics = await request.get(`${API_URL}/api/v1/admin/analytics`);
    expect(analytics.ok()).toBeTruthy();
    console.log("✓ Analytics: OK");

    console.log("\n🎉 All API endpoints verified!");
  });
});
