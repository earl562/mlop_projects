# Mecklenburg property lookup checkpoint

Verified September 7, 2026. This is a current-property lookup repair, not a
production release or a claim that Mecklenburg closed-sale comps are ready.

## Defect and correction

The previously configured Charlotte GIS service returned HTTP 200 with an
ArcGIS `404` error envelope: the service no longer existed. Its parser also used
fields absent from the current county schema and guessed square-meter versus
square-foot units from the size of the number. The registered provider returned
no record for the county government center at 600 E 4th St.

The county's [OpenMapping catalog](https://maps.mecklenburgcountync.gov/opendata/data.json)
identifies these current public sources:

- [Tax parcels with CAMA data](https://meckgis.mecklenburgcountync.gov/server/rest/services/TaxParcel_camadata/FeatureServer/0).
- [Tax parcel ownership and jurisdiction](https://meckgis.mecklenburgcountync.gov/server/rest/services/TaxParcel_Camaownershipvalues/FeatureServer/0).
- [Parcel zoning](https://meckgis.mecklenburgcountync.gov/server/rest/services/ParcelsZoningZipcode/FeatureServer/0).

Lookup now requires a unique matching address, matching GIS and tax parcel IDs,
and matching ownership-record address with an explicit municipality. Zoning is
joined by parcel ID; missing, conflicting or incomplete zoning is withheld.
Source errors, malformed fields, truncated inventories and ambiguous subject
matches cannot silently become the first returned property.

Explicit `legalacres` converts to square feet with assessor provenance; otherwise
`gisacres` converts with geometry provenance. Ambiguous `totalac` and legacy
`SHAPE_Area` fields do not supply inferred units. This distinction follows the
county's [CAMA field metadata](https://maps.mecklenburgcountync.gov/opendata/metadata/Tax_Parcels_with_CAMA_Data.html).
Each query requests at most 21 rows to detect the 20-candidate local limit;
the whole lookup has a 20-second budget with 15-second HTTP timeouts.

## Verification

Base commit: `fdd8ca0b619189cedadddb5fc8ceea956278f679`.
Isolated implementation/test tree: `fec28b5dbfc554dc18288b3b32583dbf463853b0`.
The tree contains the provider and three direct test files only; unrelated local
changes were excluded. This note is additional documentation, not part of that
tested source tree.

- Initial current-source regressions: 18 failed against the old provider, then
  passed after repair. Fourteen legacy tests remain, with fixtures corrected to
  the observed schema and repeated client mocks replaced by HTTP-level tests.
- Fourteen additional checks cover malformed inputs, query bounds and escaping,
  aggregate deadline cancellation, caller cancellation and client cleanup.
- Complete isolated unit suite: **2,035 passed**, one existing Starlette/HTTPX
  deprecation warning, 13.07 seconds on the final candidate.
- Full backend Ruff checks and formatting: passed, 459 files checked.
- Full source mypy: exit 0, with existing notes about untyped function bodies.
  LSP was unavailable; the user's earlier decision not to install it was honored.
- Additional mypy check of all four changed source/test files: passed after
  correcting inferred fixture-container annotations.
- Independent code review: **CLEAR / APPROVE** for the exact implementation/test
  tree above, with no findings. The reviewer independently ran all 46 focused
  tests, lint and targeted source typing checks. This is checkpoint approval,
  not approval to merge, deploy or release.

The actual `lookup_property` application function was also executed from the
isolated export against public county services, without model or database calls:

| Real scenario | Observed result |
| --- | --- |
| 600 E 4th St, Charlotte, address lookup | Parcel `12502601`, municipality `CHARLOTTE`, zoning `UC` |
| Same address, point inside its county parcel polygon | Same parcel and zoning |
| Different street address at that same point | No property returned |
| 105 Gilead Rd, Huntersville, two county CAMA rows | No arbitrary first-row selection |

For the Charlotte parcel, the county reports zero legal acres and GIS acreage
`2.67200098`; the returned `116392.3626888` square feet is therefore explicitly
marked **geometry**, not a verified legal lot area. Owner details were omitted
from verification output. No existing app process was restarted or stopped.

## Boundaries and next work

This checkpoint intentionally abstains on multi-row/building inventories,
unresolved condo/tax IDs and address forms that cannot be matched exactly.
Those are coverage gaps to measure, not licenses to guess. The live sample is
small and does not establish municipality-wide reliability or fresh ordinance
coverage. County zoning codes still need the corresponding authoritative rules.

Current building area, use and year built are **not** historical attributes at a
comp's sale date. Closed-sale verification, dated physical evidence, human review,
and broader Florida/NC app workflow validation remain separate release gates.
No authentication setup, paid fallback, deployment or shared migration occurred.

The previous base commit's [GitHub check run](https://github.com/earl562/plotlot-v2/actions/runs/34092803827)
passed all six application/quality/test jobs. Its separate Repository Pair
Release Gate failed with `binding path set matched no files`; repository-variable
listing was empty. That gate was not weakened or marked passed by this repair.
