import { expect, gotoHome, runLookupFlow, stubAnalyzeStream, test } from "./helpers";
import { CANONICAL_LEAD_SAMPLES } from "./canonical-lead-samples";

function resultFor(lead: (typeof CANONICAL_LEAD_SAMPLES)[number]) {
  return {
    address: lead.address,
    formatted_address: lead.address,
    municipality: lead.municipality,
    county: lead.countyLabel,
    lat: 26.1,
    lng: -80.2,
    zoning_district: "PUBLIC-SAMPLE",
    zoning_description: "Recorded public lead-list zoning fixture",
    allowed_uses: ["Residential"],
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
      governing_constraint: "Recorded public sample",
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
    summary: "Canonical public lead-list sample completed.",
    sources: [],
    confidence: "high",
    source_refs: [],
    confidence_warning: null,
    suggested_next_steps: [],
  };
}

test.describe("canonical stubbed lookup UAT", () => {
  for (const lead of CANONICAL_LEAD_SAMPLES) {
    test(`${lead.municipalityLane} completes with a terminal SSE result`, async ({ page }) => {
      await gotoHome(page);
      await stubAnalyzeStream(page, {
        statuses: [
          { step: "geocoding", message: "Resolving address...", complete: true },
        ],
        result:
          process.env.PLOTLOT_QUALITY_MUTATION === "missing-terminal-sse" &&
          lead.municipalityLane === "miami"
            ? undefined
            : resultFor(lead),
      });

      await runLookupFlow(page, lead.address);

      const report = page.getByTestId("report-root");
      await expect(report).toBeVisible();
      await expect(report.getByRole("heading", { name: lead.address, exact: true })).toBeVisible();
      await expect(report.getByText("Recorded public sample")).toBeVisible();
      await expect(
        report.getByText(`${lead.municipality}, ${lead.countyLabel} County`),
      ).toBeVisible();
    });
  }
});
