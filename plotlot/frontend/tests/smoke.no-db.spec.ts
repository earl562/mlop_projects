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

  test("lookup stream completes without db-backed assertions", async ({ page }) => {
    await gotoHome(page);
    await stubAnalyzeStream(page, {
      statuses: [
        { step: "geocoding", message: "Address resolved", complete: true },
      ],
      result: {
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
        density_analysis: null,
        comp_analysis: null,
        pro_forma: null,
        site_risk: null,
        summary: "Completed no-database smoke analysis.",
        sources: [],
        confidence: "high",
        source_refs: [],
        confidence_warning: null,
        suggested_next_steps: [],
      },
    });

    await runLookupFlow(page, "7940 Plantation Blvd, Miramar, FL 33023");

    await expect(page.getByTestId("report-root")).toBeVisible();
    await expect(page.getByText("Miramar, Broward County")).toBeVisible();
    await expect(page.getByTestId("report-error")).toHaveCount(0);
  });
});
