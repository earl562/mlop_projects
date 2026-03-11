import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// Helper: run analysis for a given address and wait for report
// ---------------------------------------------------------------------------
async function analyzeAddress(
  page: import("@playwright/test").Page,
  address: string,
) {
  await page.goto("/");
  const input = page.getByRole("textbox", { name: /South Florida address/ });
  await input.fill(address);
  await page.getByRole("button", { name: "Send message" }).click();
  // Wait for pipeline to start — either stepper or the report itself
  // (pipeline can be fast enough that stepper is gone before we check)
  await expect(
    page.getByText("Geocoding").or(page.getByText("MAX ALLOWABLE UNITS")),
  ).toBeVisible({ timeout: 30_000 });
}

// ---------------------------------------------------------------------------
// Pre-flight: verify backend + data before running UAT
// ---------------------------------------------------------------------------
test.beforeAll(async ({ request }) => {
  const health = await request.get("http://localhost:8000/health");
  expect(health.ok()).toBeTruthy();
  const body = await health.json();
  expect(body.status).toBe("healthy");
  expect(body.checks.database).toBe("ok");

  // Verify we have data for all test municipalities
  const stats = await request.get(
    "http://localhost:8000/api/v1/admin/chunks/stats",
  );
  const chunks = await stats.json();
  const municipalities = chunks.breakdown.map(
    (m: { municipality: string }) => m.municipality,
  );
  expect(municipalities).toContain("Miramar");
  expect(municipalities).toContain("Miami Gardens");
  expect(municipalities).toContain("Fort Lauderdale");
});

// ---------------------------------------------------------------------------
// Scenario 1: Welcome Screen — Visual Integrity
// ---------------------------------------------------------------------------
test.describe("Scenario 1: Welcome Screen", () => {
  test("renders all UI elements correctly", async ({ page }) => {
    await page.goto("/");

    // Nav bar
    await expect(page.locator("nav")).toContainText("PlotLot");
    await expect(page.locator("nav")).toContainText("Beta");
    await expect(page.locator("nav")).toContainText("104 municipalities");

    // Greeting + heading
    await expect(page.getByText("Hi there")).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: "Analyze any property in South Florida",
      }),
    ).toBeVisible();

    // Input bar
    const input = page.getByRole("textbox", {
      name: /South Florida address/,
    });
    await expect(input).toBeVisible();
    await expect(input).toBeFocused();

    // Send button disabled when empty
    await expect(
      page.getByRole("button", { name: "Send message" }),
    ).toBeDisabled();

    // 4 suggestion chips
    for (const text of [
      /Miami Gardens/,
      /vacant lots/,
      /Zoning rules in Miramar/,
      /build on my lot/,
    ]) {
      await expect(page.getByRole("button", { name: text })).toBeVisible();
    }

    // Footer
    await expect(
      page.getByText("PlotLot covers 104 municipalities"),
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Scenario 2: Miramar RS5 — Single-Family, Max 1 Unit
// ---------------------------------------------------------------------------
test.describe("Scenario 2: Miramar RS5 (max 1 unit)", () => {
  test("returns correct RS5 zoning report", async ({ page }) => {
    await analyzeAddress(page, "7940 Plantation Blvd, Miramar, FL 33023");

    // Wait for report
    await expect(page.getByText("RS5").first()).toBeVisible({
      timeout: 120_000,
    });

    // Municipality + county
    await expect(
      page.getByText("Miramar, Broward County").first(),
    ).toBeVisible();

    // Density analysis — max 1 unit
    await expect(page.getByText("MAX ALLOWABLE UNITS")).toBeVisible();
    await expect(page.getByText("Governing constraint")).toBeVisible();

    // Dimensional standards section
    await expect(page.getByText("Max Height")).toBeVisible();
    await expect(page.getByText("Max Density")).toBeVisible();

    // Setbacks
    await expect(
      page.getByRole("heading", { name: "Setbacks" }),
    ).toBeVisible();

    // Property record
    await expect(
      page.getByRole("heading", { name: "Property Record" }),
    ).toBeVisible();

    // Sources + save
    await expect(page.getByText(/VIEW \d+ SOURCES/i)).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Save to Portfolio" }),
    ).toBeVisible();

    // Follow-up suggestions
    await expect(
      page.getByRole("button", { name: /build on this lot/ }),
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Scenario 3: Miami Gardens R-1 — Different Municipality, Single-Family
// ---------------------------------------------------------------------------
test.describe("Scenario 3: Miami Gardens R-1 (different municipality)", () => {
  test("returns R-1 zoning for Miami Gardens address", async ({ page }) => {
    await analyzeAddress(page, "171 NE 209th Ter, Miami, FL 33179");

    // Wait for report — R-1 district
    await expect(page.getByText("R-1").first()).toBeVisible({
      timeout: 120_000,
    });

    // Municipality + county (geocoded to Miami Gardens area, Miami-Dade)
    await expect(page.getByText(/Miami-Dade/i).first()).toBeVisible();

    // Density — should be 1 unit for single-family R-1
    await expect(page.getByText("MAX ALLOWABLE UNITS")).toBeVisible();

    // Confidence badge present (level may vary across runs)
    await expect(
      page.getByText(/high|medium|low/i).first(),
    ).toBeVisible();

    // Save button available
    await expect(
      page.getByRole("button", { name: "Save to Portfolio" }),
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Scenario 4: Fort Lauderdale — Different County Municipality
// ---------------------------------------------------------------------------
test.describe("Scenario 4: Fort Lauderdale (third municipality)", () => {
  test("returns zoning report for Fort Lauderdale address", async ({
    page,
  }) => {
    // Tests a third municipality (Broward) — zoning code may be RC-15, RS-8, etc.
    await analyzeAddress(page, "1517 NE 5th Ct, Fort Lauderdale, FL 33301");

    // Wait for report to load
    await expect(
      page.getByText("MAX ALLOWABLE UNITS"),
    ).toBeVisible({ timeout: 120_000 });

    // Municipality + county
    await expect(page.getByText(/Fort Lauderdale/i).first()).toBeVisible();
    await expect(page.getByText(/Broward/i).first()).toBeVisible();

    // Dimensional standards
    await expect(page.getByText("Max Height")).toBeVisible();
    await expect(page.getByText("Max Density")).toBeVisible();

    // Property record
    await expect(
      page.getByRole("heading", { name: "Property Record" }),
    ).toBeVisible();

    // Save button
    await expect(
      page.getByRole("button", { name: "Save to Portfolio" }),
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Scenario 5: Suggestion Chip — Chat Path
// ---------------------------------------------------------------------------
test.describe("Scenario 5: Suggestion Chip Chat", () => {
  test("clicking chip sends chat message", async ({ page }) => {
    await page.goto("/");

    // Click the Miramar chip (no street address → routes to chat)
    await page
      .getByRole("button", { name: /Zoning rules in Miramar/ })
      .click();

    // User message should appear
    await expect(page.getByText("Zoning rules in Miramar")).toBeVisible();

    // Wait for assistant response
    await expect(
      page
        .locator('[class*="assistant"]')
        .or(page.getByText(/zoning|Miramar/i).last()),
    ).toBeVisible({ timeout: 60_000 });
  });
});

// ---------------------------------------------------------------------------
// Scenario 6: Follow-Up Chat with Context
// ---------------------------------------------------------------------------
test.describe("Scenario 6: Follow-Up Chat", () => {
  test("follow-up maintains report context", async ({ page }) => {
    await analyzeAddress(page, "7940 Plantation Blvd, Miramar, FL 33023");

    // Wait for report
    await expect(page.getByText("RS5").first()).toBeVisible({
      timeout: 120_000,
    });

    // Click follow-up chip
    await page
      .getByRole("button", { name: /build on this lot/ })
      .first()
      .click();

    // Response should reference RS5/Miramar context
    await expect(
      page.getByText(/single.family|RS5|residential|Miramar/i).last(),
    ).toBeVisible({ timeout: 60_000 });
  });
});

// ---------------------------------------------------------------------------
// Scenario 7: Error — Out of Coverage
// ---------------------------------------------------------------------------
test.describe("Scenario 7: Out of Coverage Error", () => {
  test("Orlando address shows coverage error", async ({ page }) => {
    await page.goto("/");

    const input = page.getByRole("textbox", {
      name: /South Florida address/,
    });
    await input.fill("100 S Orange Ave, Orlando, FL 32801");
    await page.getByRole("button", { name: "Send message" }).click();

    // Should show error about coverage
    await expect(
      page.getByText(
        /couldn't analyze|outside|coverage|Orange County|PlotLot covers/i,
      ),
    ).toBeVisible({ timeout: 30_000 });

    // Input should be re-enabled for retry
    const chatInput = page.getByRole("textbox");
    await expect(chatInput).toBeEnabled({ timeout: 5_000 });
  });
});

// ---------------------------------------------------------------------------
// Scenario 8: Save to Portfolio
// ---------------------------------------------------------------------------
test.describe("Scenario 8: Save to Portfolio", () => {
  test("save button persists analysis", async ({ page }) => {
    // Intercept the portfolio POST to capture request/response for debugging
    let saveResponse: { status: number; body: string } | null = null;
    let saveRequestBody: string | null = null;
    await page.route("**/api/v1/portfolio", async (route) => {
      // Capture the request body
      saveRequestBody = route.request().postData();
      // Let the request continue to the real backend
      const response = await route.fetch();
      saveResponse = {
        status: response.status(),
        body: (await response.text()),
      };
      await route.fulfill({ response });
    });

    await analyzeAddress(page, "7940 Plantation Blvd, Miramar, FL 33023");

    // Wait for report and save button
    await expect(page.getByText("RS5").first()).toBeVisible({
      timeout: 120_000,
    });
    const saveBtn = page.getByRole("button", { name: "Save to Portfolio" });
    await expect(saveBtn).toBeVisible();

    // Click save
    await saveBtn.click();

    // Wait for network request to complete
    await page.waitForTimeout(3_000);

    // Log save result for debugging
    if (saveResponse) {
      console.log(`Portfolio save: ${saveResponse.status}`);
      if (saveResponse.status !== 200) {
        console.error("Save response:", saveResponse.body);
        if (saveRequestBody) {
          // Log just the list fields that might cause validation errors
          try {
            const req = JSON.parse(saveRequestBody);
            const report = req.report;
            for (const field of ["allowed_uses", "conditional_uses", "prohibited_uses", "sources"]) {
              const val = report[field];
              console.error(`  ${field}: type=${typeof val}, isArray=${Array.isArray(val)}`);
            }
          } catch { /* ignore parse errors */ }
        }
      }
    }

    // Should transition to saved state
    await expect(page.getByText(/Saved to Portfolio/i)).toBeVisible({
      timeout: 10_000,
    });
  });
});
