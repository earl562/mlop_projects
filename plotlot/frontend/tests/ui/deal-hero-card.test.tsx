import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DealHeroCard from "../../src/components/DealHeroCard";
import type { ZoningReportData } from "../../src/lib/api";
import { reportWithoutSnapshot } from "./agent-run-panel.fixtures";

function landReport(overrides: Partial<ZoningReportData> = {}): ZoningReportData {
  return {
    ...reportWithoutSnapshot(),
    numeric_params: {
      max_density_units_per_acre: null,
      min_lot_area_per_unit_sqft: null,
      far: null,
      max_lot_coverage_pct: null,
      max_height_ft: null,
      max_stories: null,
      setback_front_ft: null,
      setback_side_ft: null,
      setback_rear_ft: null,
      min_unit_size_sqft: null,
      min_lot_width_ft: null,
      parking_spaces_per_unit: null,
      property_type: "land",
      parking_per_1000_gla_sqft: null,
      max_gla_sqft: null,
      min_tenant_size_sqft: null,
      loading_spaces: null,
    },
    density_analysis: {
      max_units: 3,
      governing_constraint: "lot_area",
      constraints: [],
      lot_size_sqft: 15_000,
      buildable_area_sqft: null,
      lot_width_ft: null,
      lot_depth_ft: null,
      max_gla_sqft: null,
      confidence: "medium",
      notes: [],
    },
    comp_analysis: {
      comparables: [],
      median_price_per_acre: 0,
      estimated_land_value: 0,
      adv_per_unit: 250_000,
      confidence: 0.8,
    },
    ...overrides,
  };
}

function metricBox(label: string): HTMLElement {
  const box = screen.getByText(label).parentElement;
  if (box instanceof HTMLElement) return box;
  throw new Error(`${label} metric is missing`);
}

describe("DealHeroCard land deal metrics", () => {
  it("shows pro-forma gaps instead of deriving residual value in the frontend", () => {
    render(<DealHeroCard report={landReport()} dealType="land_deal" />);

    expect(screen.getByText("Max Lots/Units")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("ARV per Lot/Unit")).toBeInTheDocument();
    expect(screen.getByText("$250,000")).toBeInTheDocument();
    expect(screen.getAllByText("Needs pro forma")).toHaveLength(2);
    expect(screen.queryByText(/ARV.*75%/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/\$175\/sf/i)).not.toBeInTheDocument();
  });

  it("uses backend pro-forma values when available", () => {
    render(
      <DealHeroCard
        report={landReport({
          pro_forma: {
            gross_development_value: 750_000,
            hard_costs: 600_000,
            soft_costs: 120_000,
            builder_margin: 80_000,
            max_land_price: 120_000,
            cost_per_door: 300_000,
            construction_cost_psf: 200,
            avg_unit_size_sqft: 1_000,
            adv_per_unit: 250_000,
            max_units: 3,
            soft_cost_pct: 20,
            builder_margin_pct: 10,
            notes: [],
          },
        })}
        dealType="land_deal"
      />,
    );

    expect(within(metricBox("Est. Build Cost")).getByText("$600,000")).toBeInTheDocument();
    expect(within(metricBox("Est. Build Cost")).getByText("$200/sf x 1000sf from pro forma")).toBeInTheDocument();
    expect(within(metricBox("Residual Land Value")).getByText("$120,000")).toBeInTheDocument();
    expect(within(metricBox("Residual Land Value")).getByText("from backend pro forma")).toBeInTheDocument();
    expect(within(metricBox("Cost / Door")).getByText("$300,000")).toBeInTheDocument();
  });
});
