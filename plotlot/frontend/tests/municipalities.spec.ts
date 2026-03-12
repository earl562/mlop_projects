import { test, expect } from "@playwright/test";

/**
 * Municipality Coverage Tests — verify every ingested municipality
 * returns a valid zoning report through the full pipeline.
 *
 * Each test: enter address → wait for report → verify key sections.
 * Uses the backend /admin/chunks/stats to discover which municipalities
 * have data, then runs one test per municipality.
 */

// ---------------------------------------------------------------------------
// Test addresses — one real address per municipality
// ---------------------------------------------------------------------------
const MUNICIPALITY_ADDRESSES: Record<string, { address: string; county: string }> = {
  // Miami-Dade County
  "Aventura":               { address: "3250 NE 188th St, Aventura, FL 33180", county: "Miami-Dade" },
  "Bal Harbour":            { address: "43 Bal Bay Dr, Bal Harbour, FL 33154", county: "Miami-Dade" },
  "Bay Harbor Islands":     { address: "9221 E Bay Harbor Dr, Bay Harbor Islands, FL 33154", county: "Miami-Dade" },
  "Biscayne Park":          { address: "750 NE 120th St, Biscayne Park, FL 33161", county: "Miami-Dade" },
  "Coral Gables":           { address: "434 Aragon Ave, Coral Gables, FL 33134", county: "Miami-Dade" },
  "Cutler Bay":             { address: "9920 SW 214th St, Cutler Bay, FL 33189", county: "Miami-Dade" },
  "Doral":                  { address: "5253 NW 94th Doral Pl, Doral, FL 33178", county: "Miami-Dade" },
  "El Portal":              { address: "400 NE 87th St, El Portal, FL 33138", county: "Miami-Dade" },
  "Florida City":           { address: "867 SW 7th Plz, Florida City, FL 33034", county: "Miami-Dade" },
  "Golden Beach":           { address: "240 Golden Beach Dr, Golden Beach, FL 33160", county: "Miami-Dade" },
  "Hialeah":                { address: "590 W 35th Pl, Hialeah, FL 33012", county: "Miami-Dade" },
  "Hialeah Gardens":        { address: "10440 NW 131st St, Hialeah Gardens, FL 33018", county: "Miami-Dade" },
  "Homestead":              { address: "236 SW 6th Ave, Homestead, FL 33030", county: "Miami-Dade" },
  "Indian Creek Village":   { address: "26 Indian Creek Island Rd, Indian Creek Village, FL 33154", county: "Miami-Dade" },
  "Key Biscayne":           { address: "440 S Mashta Dr, Key Biscayne, FL 33149", county: "Miami-Dade" },
  "Medley":                 { address: "6811 NW 104th Ct, Medley, FL 33178", county: "Miami-Dade" },
  "Miami":                  { address: "701 S Miami Ave, Miami, FL 33130", county: "Miami-Dade" },
  "Miami Beach":            { address: "311 Meridian Ave, Miami Beach, FL 33139", county: "Miami-Dade" },
  "Miami Gardens":          { address: "171 NE 209th Ter, Miami, FL 33179", county: "Miami-Dade" },
  "Miami Lakes":            { address: "6437 Lemon Tree Ln, Miami Lakes, FL 33014", county: "Miami-Dade" },
  "Miami Springs":          { address: "201 Westward Dr, Miami Springs, FL 33166", county: "Miami-Dade" },
  "North Miami Beach":      { address: "1698 NE 182nd St, North Miami Beach, FL 33162", county: "Miami-Dade" },
  "Opa-Locka":              { address: "1130 York St, Opa-Locka, FL 33054", county: "Miami-Dade" },
  "Palmetto Bay":           { address: "15405 SW 73rd Ct, Palmetto Bay, FL 33157", county: "Miami-Dade" },
  "Pinecrest":              { address: "11001 SW 74th Ave, Pinecrest, FL 33156", county: "Miami-Dade" },
  "South Miami":            { address: "5990 SW 86th St, South Miami, FL 33143", county: "Miami-Dade" },
  "Sunny Isles Beach":      { address: "330 Sunny Isles Blvd, Sunny Isles Beach, FL 33160", county: "Miami-Dade" },
  "Surfside":               { address: "9441 Byron Ave, Surfside, FL 33154", county: "Miami-Dade" },
  "Sweetwater":             { address: "11441 SW 2nd St, Sweetwater, FL 33174", county: "Miami-Dade" },
  "Virginia Gardens":       { address: "3810 NW 65th Ave, Virginia Gardens, FL 33166", county: "Miami-Dade" },
  "West Miami":             { address: "6227 SW 19th St, West Miami, FL 33155", county: "Miami-Dade" },
  "Unincorporated Miami-Dade": { address: "12208 SW 220th St, Miami, FL 33170", county: "Miami-Dade" },

  // Broward County
  "Coconut Creek":          { address: "4361 NW 39th Ave, Coconut Creek, FL 33073", county: "Broward" },
  "Cooper City":            { address: "9201 SW 51st Pl, Cooper City, FL 33328", county: "Broward" },
  "Coral Springs":          { address: "10833 NW 6th St, Coral Springs, FL 33071", county: "Broward" },
  "Dania Beach":            { address: "216 SE 9th St, Dania Beach, FL 33004", county: "Broward" },
  "Deerfield Beach":        { address: "409 NW 2nd Way, Deerfield Beach, FL 33441", county: "Broward" },
  "Fort Lauderdale":        { address: "1517 NE 5th Ct, Fort Lauderdale, FL 33301", county: "Broward" },
  "Lauderdale Lakes":       { address: "4740 NW 24th Ct, Lauderdale Lakes, FL 33313", county: "Broward" },
  "Lauderhill":             { address: "4841 NW 12th Ct, Lauderhill, FL 33313", county: "Broward" },
  "Margate":                { address: "6289 Duval Dr, Margate, FL 33063", county: "Broward" },
  "Miramar":                { address: "7940 Plantation Blvd, Miramar, FL 33023", county: "Broward" },
  "North Lauderdale":       { address: "8251 SW 3rd Ct, North Lauderdale, FL 33068", county: "Broward" },
  "Oakland Park":           { address: "800 NE 43rd St, Oakland Park, FL 33334", county: "Broward" },
  "Parkland":               { address: "10800 Windward St, Parkland, FL 33076", county: "Broward" },
  "Plantation":             { address: "4341 SW 2nd Ct, Plantation, FL 33317", county: "Broward" },
  "Sea Ranch Lakes":        { address: "7 Winnebago Rd, Sea Ranch Lakes, FL 33308", county: "Broward" },
  "Southwest Ranches":      { address: "5450 SW 148th Ave, Southwest Ranches, FL 33330", county: "Broward" },
  "Sunrise":                { address: "9350 NW 43rd Manor, Sunrise, FL 33351", county: "Broward" },
  "Tamarac":                { address: "7913 NW 71st Ave, Tamarac, FL 33321", county: "Broward" },
  "West Park":              { address: "5231 SW 18th St, West Park, FL 33023", county: "Broward" },
  "Wilton Manors":          { address: "2416 NE 19th Ter, Wilton Manors, FL 33305", county: "Broward" },
  "Davie":                  { address: "6300 SW 41st Ct, Davie, FL 33314", county: "Broward" },
  "Hillsboro Beach":        { address: "1083 Hillsboro Mile, Hillsboro Beach, FL 33062", county: "Broward" },
  "Lauderdale-By-The-Sea":  { address: "4558 Bougainvilla Dr, Lauderdale-By-The-Sea, FL 33308", county: "Broward" },
  "Pembroke Park":          { address: "5000 SW 37th St, Pembroke Park, FL 33023", county: "Broward" },

  // Palm Beach County
  "Atlantis":               { address: "105 Palm Cir, Atlantis, FL 33462", county: "Palm Beach" },
  "Belle Glade":            { address: "932 NE 22nd St, Belle Glade, FL 33430", county: "Palm Beach" },
  "Boca Raton":             { address: "200 E Palmetto Park Rd, Boca Raton, FL 33432", county: "Palm Beach" },
  "Cloud Lake":             { address: "204 Lang Rd, Cloud Lake, FL 33406", county: "Palm Beach" },
  "Delray Beach":           { address: "275 NE 16th St, Delray Beach, FL 33444", county: "Palm Beach" },
  "Glen Ridge":             { address: "1330 Glen Rd, Glen Ridge, FL 33406", county: "Palm Beach" },
  "Greenacres":             { address: "5600 S 36th St, Greenacres, FL 33463", county: "Palm Beach" },
  "Gulf Stream":            { address: "3433 Gulfstream Rd, Gulf Stream, FL 33483", county: "Palm Beach" },
  "Haverhill":              { address: "1081 New Parkview Pl, Haverhill, FL 33417", county: "Palm Beach" },
  "Highland Beach":         { address: "2455 S Ocean Blvd, Highland Beach, FL 33487", county: "Palm Beach" },
  "Hypoluxo":               { address: "108 Lucina Dr, Hypoluxo, FL 33462", county: "Palm Beach" },
  "Juno Beach":             { address: "431 Sunset Way, Juno Beach, FL 33408", county: "Palm Beach" },
  "Jupiter":                { address: "330 Center St, Jupiter, FL 33458", county: "Palm Beach" },
  "Jupiter Inlet Colony":   { address: "87 Lighthouse Dr, Jupiter Inlet Colony, FL 33469", county: "Palm Beach" },
  "Lake Clarke Shores":     { address: "7306 Clarke Rd, Lake Clarke Shores, FL 33406", county: "Palm Beach" },
  "Lake Park":              { address: "515 8th St, Lake Park, FL 33403", county: "Palm Beach" },
  "Lantana":                { address: "505 SE Atlantic Dr, Lantana, FL 33462", county: "Palm Beach" },
  "Loxahatchee Groves":     { address: "17987 32nd Ln N, Loxahatchee, FL 33470", county: "Palm Beach" },
  "Mangonia Park":          { address: "1704 Boardman Ave, Mangonia Park, FL 33407", county: "Palm Beach" },
  "North Palm Beach":       { address: "904 Lighthouse Dr, North Palm Beach, FL 33408", county: "Palm Beach" },
  "Ocean Ridge":            { address: "18 Hersey Dr, Ocean Ridge, FL 33435", county: "Palm Beach" },
  "Pahokee":                { address: "754 Fern St, Pahokee, FL 33476", county: "Palm Beach" },
  "Palm Beach":             { address: "272 Sandpiper Dr, Palm Beach, FL 33480", county: "Palm Beach" },
  "Palm Beach Gardens":     { address: "4305 Birdwood St, Palm Beach Gardens, FL 33410", county: "Palm Beach" },
  "Palm Beach Shores":      { address: "236 Inlet Way, Palm Beach Shores, FL 33404", county: "Palm Beach" },
  "Palm Springs":           { address: "3050 Emilio Ln, Palm Springs, FL 33406", county: "Palm Beach" },
  "Riviera Beach":          { address: "546 W 2nd St, Riviera Beach, FL 33404", county: "Palm Beach" },
  "Royal Palm Beach":       { address: "141 Eider Ct, Royal Palm Beach, FL 33411", county: "Palm Beach" },
  "South Bay":              { address: "330 SW 1st Ave, South Bay, FL 33493", county: "Palm Beach" },
  "South Palm Beach":       { address: "3610 S Ocean Blvd, South Palm Beach, FL 33480", county: "Palm Beach" },
  "Tequesta":               { address: "37 Russell St, Tequesta, FL 33469", county: "Palm Beach" },
  "Wellington":             { address: "1282 Whimbrel Rd, Wellington, FL 33414", county: "Palm Beach" },
  "Westlake":               { address: "13560 Spruce Pine Dr, Westlake, FL 33470", county: "Palm Beach" },
  "West Palm Beach":        { address: "2962 Oklahoma St, West Palm Beach, FL 33406", county: "Palm Beach" },
};

// ---------------------------------------------------------------------------
// Pre-flight: query backend for ingested municipalities
// ---------------------------------------------------------------------------
let ingestedMunicipalities: Set<string> = new Set();

test.beforeAll(async ({ request }) => {
  const health = await request.get("http://localhost:8000/health");
  expect(health.ok()).toBeTruthy();

  const stats = await request.get("http://localhost:8000/api/v1/admin/chunks/stats");
  const chunks = await stats.json();
  ingestedMunicipalities = new Set(
    chunks.breakdown.map((m: { municipality: string }) => m.municipality),
  );
  console.log(
    `\nIngested municipalities (${ingestedMunicipalities.size}): ${[...ingestedMunicipalities].sort().join(", ")}\n`,
  );
});

// ---------------------------------------------------------------------------
// Helper: run analysis and wait for report
// ---------------------------------------------------------------------------
async function analyzeAndWaitForReport(
  page: import("@playwright/test").Page,
  address: string,
) {
  await page.goto("/");
  const input = page.getByRole("textbox", { name: /South Florida address/ });
  await input.fill(address);
  await page.getByRole("button", { name: "Send message" }).click();

  // Wait for pipeline to start — stepper, report, or error
  await expect(
    page
      .getByText("Geocoding")
      .or(page.getByText("MAX ALLOWABLE UNITS"))
      .or(page.getByText("Fetching property record"))
      .or(page.getByText(/Connection error/i)),
  ).toBeVisible({ timeout: 45_000 });

  // Fail fast if connection error
  const connError = page.getByText(/Connection error/i);
  if (await connError.isVisible().catch(() => false)) {
    throw new Error("Backend connection error — is the server overloaded?");
  }

  // Wait for report to complete — look for any of the key report sections
  await expect(
    page.getByText("MAX ALLOWABLE UNITS"),
  ).toBeVisible({ timeout: 120_000 });
}

// ---------------------------------------------------------------------------
// Generate one test per municipality
// ---------------------------------------------------------------------------
for (const [municipality, { address, county }] of Object.entries(MUNICIPALITY_ADDRESSES)) {
  test.describe(`${municipality} (${county})`, () => {
    test(`analyzes address and returns zoning report`, async ({ page }) => {
      // Skip if municipality has no ingested data
      test.skip(
        !ingestedMunicipalities.has(municipality),
        `No data ingested for ${municipality}`,
      );

      await analyzeAndWaitForReport(page, address);

      // -- Core report structure checks --

      // County identification
      await expect(page.getByText(new RegExp(county, "i")).first()).toBeVisible();

      // Dimensional standards present
      await expect(page.getByText("Max Height")).toBeVisible({ timeout: 5_000 });
      await expect(page.getByText("Max Density")).toBeVisible();

      // Setbacks section
      await expect(
        page.getByRole("heading", { name: "Setbacks" }),
      ).toBeVisible();

      // Property record section
      await expect(
        page.getByRole("heading", { name: "Property Record" }),
      ).toBeVisible();

      // Sources
      await expect(page.getByText(/VIEW \d+ SOURCES/i)).toBeVisible();

      // Save button
      await expect(
        page.getByRole("button", { name: "Save to Portfolio" }),
      ).toBeVisible();

      // Follow-up chips
      await expect(
        page.getByRole("button", { name: /build on this lot/i }),
      ).toBeVisible();
    });
  });
}
