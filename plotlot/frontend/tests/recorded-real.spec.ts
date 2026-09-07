import { expect, test } from "./fixtures";
import {
  addressSha256,
  BYRIGHT_PUBLIC_LEAD_SOURCE,
  CANONICAL_LEAD_SAMPLES,
} from "./canonical-lead-samples";

test("recorded public ByRight lead sample remains hash-bound and private-list free", async ({
  page,
}, testInfo) => {
  for (const lead of CANONICAL_LEAD_SAMPLES) {
    expect(addressSha256(lead.address)).toBe(lead.addressSha256);
  }

  await page.goto("/workspace");
  await expect(page.getByTestId("lookup-input")).toBeVisible();

  await testInfo.attach("recorded-public-source.json", {
    body: JSON.stringify(
      {
        source: BYRIGHT_PUBLIC_LEAD_SOURCE,
        selection: CANONICAL_LEAD_SAMPLES.map((lead) => ({
          addressSha256: lead.addressSha256,
          county: lead.county,
          municipalityLane: lead.municipalityLane,
        })),
        privacy: {
          classification: "public-parcel-record",
          privateUploadedListsExcluded: true,
        },
      },
      null,
      2,
    ),
    contentType: "application/json",
  });
});
