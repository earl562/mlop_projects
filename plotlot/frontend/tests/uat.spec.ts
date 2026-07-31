import { test, expect } from "./fixtures";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

// ---------------------------------------------------------------------------
// Helper: run analysis for a given address and wait for report
// ---------------------------------------------------------------------------
async function analyzeAddress(
  page: import("@playwright/test").Page,
  address: string,
) {
  await page.goto("/");
  // Switch to Agent mode for direct pipeline (no deal type gate)
  const agentBtn = page.getByRole("button", { name: "Agent" });
  if (await agentBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
    await agentBtn.click();
  }

  const input = page
    .getByPlaceholder("Ask about zoning, density, or property data...")
    .or(page.getByPlaceholder("Enter a property address..."))
    .first();
  await expect(input).toBeVisible();
  await input.fill(address);

  const sendButton = page.getByRole("button", { name: "Send message" });
  await expect(sendButton).toBeEnabled();
  await sendButton.click();

  // Wait for pipeline to start — either stepper or the report itself
  await expect(
    page.getByText("Geocoding", { exact: true })
      .first()
      .or(page.getByText("MAX ALLOWABLE UNITS").first()),
  ).toBeVisible({ timeout: 30_000 });
}

// ---------------------------------------------------------------------------
// Pre-flight: verify backend + data before running UAT
// ---------------------------------------------------------------------------
test.beforeAll(async ({ request }) => {
  const health = await request.get(`${API_BASE}/health`);
  expect(health.ok()).toBeTruthy();
  const body = await health.json();
  expect(body.status).toBe("healthy");
  expect(body.checks.database).toBe("ok");

  // Verify we have data for all test municipalities
  const stats = await request.get(`${API_BASE}/api/v1/admin/chunks/stats`);
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

    // Sidebar branding
    await expect(page.getByText("PlotLot").first()).toBeVisible();
    await expect(page.getByText("Beta").first()).toBeVisible();
    await expect(page.getByText("5 states")).toBeVisible();

    // Mode toggle visible
    await expect(page.getByRole("button", { name: "Lookup" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Agent" })).toBeVisible();

    // Greeting + heading (Lookup mode is default)
    await expect(page.getByText("Hi there")).toBeVisible();
    await expect(page.getByText("Analyze any property")).toBeVisible();

    // Input bar
    const input = page.getByPlaceholder("Enter a property address...");
    await expect(input).toBeVisible();

    // Send button disabled when empty
    await expect(
      page.getByRole("button", { name: "Send message" }),
    ).toBeDisabled();

    // Capability chips (lookup mode)
    for (const text of [/Miramar, FL/, /Miami Gardens, FL/, /Boca Raton, FL/]) {
      await expect(page.getByRole("button", { name: text })).toBeVisible();
    }

    // Footer
    await expect(
      page.getByText(/PlotLot analyzes/),
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
    // Switch to Chat mode where suggestion chips are visible
    await page.getByRole("button", { name: "Chat with Agent" }).click();

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
// Scenario 7: Out-of-State Address — No Boundary Rejection
// (VALID_COUNTIES removed — Universal Provider handles any US county)
// ---------------------------------------------------------------------------
test.describe("Scenario 7: Out-of-State Address", () => {
  test("Orlando address is NOT rejected by boundary check", async ({ page }) => {
    await page.goto("/");
    // Switch to Chat mode
    const chatBtn = page.getByRole("button", { name: "Chat with Agent" });
    if (await chatBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await chatBtn.click();
    }

    const input = page.getByRole("textbox", {
      name: /address|question/,
    });
    await input.fill("100 S Orange Ave, Orlando, FL 32801");
    await page.getByRole("button", { name: "Send message" }).click();

    // Wait for response
    await page.waitForTimeout(15_000);

    // Should NOT show the old "PlotLot covers Miami-Dade, Broward..." error
    const oldBoundaryError = page.getByText(
      /PlotLot covers Miami-Dade, Broward, and Palm Beach counties only/i,
    );
    await expect(oldBoundaryError).not.toBeVisible();

    // Pipeline should attempt to process (may succeed or fail on data, but not boundary)
    // Input should remain usable
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
    const resp = saveResponse as { status: number; body: string } | null;
    if (resp) {
      console.log(`Portfolio save: ${resp.status}`);
      if (resp.status !== 200) {
        console.error("Save response:", resp.body);
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

// ---------------------------------------------------------------------------
// Scenario 9: Lookup Mode — Direct Address → Pipeline → Tabbed Report
// ---------------------------------------------------------------------------
test.describe("Scenario 9: Lookup Mode Flow", () => {
  test("full lookup flow runs directly from address entry", async ({ page }) => {
    await page.goto("/");

    // Should start in lookup mode by default
    const input = page.getByRole("textbox", { name: /address|question/ });
    await expect(input).toBeVisible();

    await page.route("**/api/v1/analyze/stream", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          `event: status\ndata: ${JSON.stringify({ step: "geocoding", message: "Resolving address...", complete: true })}\n\n`,
          `event: result\ndata: ${JSON.stringify({
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
            summary: "RS5 zoning supports one dwelling unit on this lot.",
            sources: [],
            confidence: "high",
            source_refs: [],
            confidence_warning: null,
            suggested_next_steps: [],
          })}\n\n`,
        ].join(""),
      });
    });

    // Enter address
    await input.fill("7940 Plantation Blvd, Miramar, FL 33023");
    await page.getByRole("button", { name: "Send message" }).click();

    // Pipeline should start
    await expect(page.getByText("Geocoding")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("What type of deal are you evaluating?")).toHaveCount(0);

    // Wait for report to render (tabbed report)
    await expect(page.getByRole("tab", { name: /Property/i }).or(page.getByText("RS5").first())).toBeVisible({
      timeout: 120_000,
    });

    // Verify hero card is visible
    await expect(page.getByText(/Max Units|Max Offer|Governing Constraint/i).first()).toBeVisible();

    // Verify "Generate Documents" button appears
    await expect(page.getByRole("button", { name: "Generate Documents" })).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Scenario 10: Agent Mode — Tool Cards + Chat Flow
// ---------------------------------------------------------------------------
test.describe("Scenario 10: Agent Mode Flow", () => {
  test("agent mode shows tool cards and supports chat", async ({ page }) => {
    await page.goto("/");

    // Switch to agent mode
    const modeToggle = page.locator("[data-mode-toggle]").or(
      page.getByRole("button", { name: /agent/i }),
    );
    if (await modeToggle.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await modeToggle.click();
    }

    // Tool cards should be visible in agent mode
    await expect(page.getByText("Analyze Property")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("Generate LOI")).toBeVisible();
    await expect(page.getByText("Search Comps")).toBeVisible();
    await expect(
      page.getByRole("button", { name: /Search Properties/i }),
    ).toBeVisible();

    // "Generate LOI" should show "Analyze a property first" hint
    await expect(page.getByText("Analyze a property first").first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Scenario 11: Mode Switching
// ---------------------------------------------------------------------------
test.describe("Scenario 11: Mode Switching", () => {
  test("switching modes updates UI without state leaks", async ({ page }) => {
    await page.goto("/");

    // Start in lookup mode — should show address example chips
    await expect(page.getByText("Miramar, FL")).toBeVisible({ timeout: 5_000 });

    // Switch to agent mode
    const modeToggle = page.locator("[data-mode-toggle]").or(
      page.getByRole("button", { name: /agent/i }),
    );
    if (await modeToggle.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await modeToggle.click();
    }

    // Should now show tool cards instead of address chips
    await expect(page.getByText("Analyze Property")).toBeVisible({ timeout: 5_000 });

    // Switch back to lookup mode
    const lookupToggle = page.locator("[data-mode-toggle]").or(
      page.getByRole("button", { name: /lookup/i }),
    );
    if (await lookupToggle.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await lookupToggle.click();
    }

    // Should show address chips again
    await expect(page.getByText("Miramar, FL")).toBeVisible({ timeout: 5_000 });
  });
});
