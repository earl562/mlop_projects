import {
  test,
  expect,
  gotoHome,
  switchToAgent,
  runLookupFlow,
  stubAnalyzeStream,
} from "./helpers";

const STUB_REPORT = {
  address: "7940 Plantation Blvd, Miramar, FL 33023",
  formatted_address: "7940 Plantation Blvd, Miramar, FL 33023",
  municipality: "Miramar",
  county: "Broward",
  lat: 25.98,
  lng: -80.26,
  zoning_district: "RS-5",
  zoning_description: "Residential Single Family",
  allowed_uses: ["Single-family dwelling"],
  conditional_uses: [],
  prohibited_uses: [],
  setbacks: { front: "25 ft", side: "7.5 ft", rear: "25 ft" },
  max_height: "35 ft",
  max_density: "5 units per acre",
  floor_area_ratio: "",
  lot_coverage: "40%",
  min_lot_size: "7,500 sq ft",
  parking_requirements: "2 spaces per dwelling unit",
  property_record: {
    folio: "514128010010",
    address: "7940 PLANTATION BLVD",
    municipality: "Miramar",
    county: "Broward",
    owner: "",
    zoning_code: "RS-5",
    zoning_description: "Residential Single Family",
    land_use_code: "",
    land_use_description: "",
    lot_size_sqft: 7500,
    lot_dimensions: "75 x 100",
    bedrooms: 0,
    bathrooms: 0,
    half_baths: 0,
    floors: 0,
    living_units: 0,
    building_area_sqft: 0,
    living_area_sqft: 0,
    year_built: 0,
    assessed_value: 0,
    market_value: 0,
    last_sale_price: 0,
    last_sale_date: "",
    lat: 25.98,
    lng: -80.26,
    parcel_geometry: null,
    zoning_layer_url: "",
  },
  numeric_params: null,
  density_analysis: {
    max_units: 1,
    governing_constraint: "density",
    constraints: [
      {
        name: "density",
        max_units: 1,
        raw_value: 0.86,
        formula: "7500 sqft * 5 units/acre / 43560 = 0.86",
        is_governing: true,
      },
    ],
    lot_size_sqft: 7500,
    buildable_area_sqft: null,
    lot_width_ft: 75,
    lot_depth_ft: 100,
    max_gla_sqft: null,
    confidence: "high",
    notes: [],
  },
  comp_analysis: null,
  pro_forma: null,
  summary: "Stubbed no-db report for reset coverage.",
  sources: ["Miramar zoning ordinance"],
  confidence: "high",
  source_refs: [],
  confidence_warning: "",
  suggested_next_steps: [],
  active_dossier: {
    resolved_address: "7940 Plantation Blvd, Miramar, FL 33023",
    parcel_id: "514128010010",
    municipality: "Miramar",
    county: "Broward",
    state: "FL",
    zoning_district: "RS-5",
    zoning_description: "Residential Single Family",
    lot_facts: {
      lot_size_sqft: 7500,
      lot_dimensions: "75 x 100",
      lot_width_ft: 75,
      lot_depth_ft: 100,
    },
    dimensional_standards: {
      setbacks: { front: "25 ft", side: "7.5 ft", rear: "25 ft" },
      max_height: "35 ft",
      max_density: "5 units per acre",
      floor_area_ratio: "",
      lot_coverage: "40%",
      min_lot_size: "7,500 sq ft",
      parking_requirements: "2 spaces per dwelling unit",
    },
    max_units: 1,
    governing_constraint: "density",
    evidence_refs: [
      {
        kind: "source",
        label: "Miramar zoning ordinance",
        source: "Miramar zoning ordinance",
        preview: "",
        confidence: "high",
      },
    ],
    confidence: "high",
    freshness_timestamp: "2026-05-13T00:00:00+00:00",
  },
};

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

  test("workspace typed address text uses normal numeric glyphs", async ({ page }) => {
    await gotoHome(page);

    const lookupInput = page.getByTestId("lookup-input");
    await lookupInput.fill("171 NE 209th Ter");
    await expect(lookupInput).toHaveValue("171 NE 209th Ter");

    const lookupFontFeatures = await lookupInput.evaluate(
      (node) => getComputedStyle(node).fontFeatureSettings,
    );
    const lookupFontVariant = await lookupInput.evaluate(
      (node) => getComputedStyle(node).fontVariantNumeric,
    );

    expect(lookupFontFeatures).not.toContain("numr");
    expect(lookupFontVariant).toBe("normal");

    await switchToAgent(page);
    const agentInput = page.getByTestId("agent-input");
    await agentInput.fill("Can 171 NE 209th Ter support 4 units?");
    await expect(agentInput).toHaveValue("Can 171 NE 209th Ter support 4 units?");

    const agentFontFeatures = await agentInput.evaluate(
      (node) => getComputedStyle(node).fontFeatureSettings,
    );
    const agentFontVariant = await agentInput.evaluate(
      (node) => getComputedStyle(node).fontVariantNumeric,
    );

    expect(agentFontFeatures).not.toContain("numr");
    expect(agentFontVariant).toBe("normal");
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

  test("active report context clears on new analysis", async ({ page }) => {
    await gotoHome(page);
    await stubAnalyzeStream(page, {
      statuses: [
        { step: "geocoding", message: "Resolving address...", complete: true },
      ],
      result: STUB_REPORT,
    });

    const input = page.getByTestId("lookup-input");
    await input.fill(STUB_REPORT.address);
    await expect(page.getByTestId("send-button")).toBeEnabled();
    await page.getByTestId("send-button").click();
    await expect(page.getByRole("heading", { name: STUB_REPORT.formatted_address })).toBeVisible();
    await expect(page.getByText("RS-5").first()).toBeVisible();

    await page.getByTestId("new-analysis-button").click();
    await expect(page.getByRole("heading", { name: STUB_REPORT.formatted_address })).toHaveCount(0);
    await expect(page.getByTestId("lookup-input")).toBeVisible();
  });
});
