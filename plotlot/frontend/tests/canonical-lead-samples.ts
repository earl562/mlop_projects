import { createHash } from "node:crypto";

type LaunchCounty = "miami-dade" | "broward" | "palm-beach";

export type CanonicalLeadSample = {
  readonly address: string;
  readonly addressSha256: string;
  readonly county: LaunchCounty;
  readonly countyLabel: string;
  readonly municipality: string;
  readonly municipalityLane: string;
};

export const BYRIGHT_PUBLIC_LEAD_SOURCE = {
  list: "south-florida-public-parcel-list",
  path: "packages/data/src/lead-list-records.ts",
  repository: "byright",
  sha256: "51c098cae91bb708acc0cf9bfd5ce3f65e3856fffdcbafe1bb967426264a3322",
} as const;

export const CANONICAL_LEAD_SAMPLES = [
  {
    address: "1320 NW 58 TER, Miami, FL 33142-0000",
    addressSha256: "c299bb6b2ce4ae2451ff62584437be44743ebdbc5d3134ba1252c0c4df7399d4",
    county: "miami-dade",
    countyLabel: "Miami-Dade",
    municipality: "Miami",
    municipalityLane: "miami",
  },
  {
    address: "11320 NW 58 PL, Unincorporated County, FL 33012-0000",
    addressSha256: "88dbeba565e4523bd97230bf61dae01bf558266ca076825dc337da5afb8838f9",
    county: "miami-dade",
    countyLabel: "Miami-Dade",
    municipality: "Unincorporated County",
    municipalityLane: "unincorporated-miami-dade",
  },
  {
    address: "1508 NE 18 ST, Fort Lauderdale, FL 33305",
    addressSha256: "71fdbcfe5af07df5b1a4054eb843be93b88e9f68fc82b83872cc687b614cbc6c",
    county: "broward",
    countyLabel: "Broward",
    municipality: "Fort Lauderdale",
    municipalityLane: "fort-lauderdale",
  },
  {
    address: "719 9TH ST, West Palm Beach, FL",
    addressSha256: "c8f6525608c240679c30a85c5dacf994af6c646875ebdac34a2901944040ee95",
    county: "palm-beach",
    countyLabel: "Palm Beach",
    municipality: "West Palm Beach",
    municipalityLane: "west-palm-beach",
  },
] as const satisfies readonly CanonicalLeadSample[];

export function addressSha256(address: string): string {
  return createHash("sha256").update(address).digest("hex");
}
