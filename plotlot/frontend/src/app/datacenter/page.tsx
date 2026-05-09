import type { Metadata } from "next";
import { DataCenterStream } from "@/components/DataCenterStream";

export const metadata: Metadata = {
  title: "Data Center Site Selection — PlotLot",
  description:
    "Evaluate industrial sites for data center development across power grid, fiber connectivity, flood zone, seismic risk, and zoning.",
};

export default function DataCenterPage() {
  return <DataCenterStream />;
}
