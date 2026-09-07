# Florida and North Carolina launch-source inventory

Date: September 7, 2026. Preliminary source discovery, not integration, permission,
coverage, valuation, or production-readiness proof. User-selected launch scope:
Miami-Dade, Broward, Palm Beach, Lee (FL), Mecklenburg (NC), and Gaston (NC).
San Diego is deferred with existing work preserved. No accounts, paid datasets,
outreach, bulk extraction, or application-code changes were made in this pass.

## Lee County, Florida

The official [GIS landing page](https://www.leegov.com/gis) links the county's
[Data Explorer](https://gisexplorer.leegov.com/). The public
[PropertySales service](https://gismapserver.leegov.com/gisserver910/rest/services/DataExplorer/PropertySales/MapServer)
is a concrete candidate for integration. Root independently inspected
[layer 15](https://gismapserver.leegov.com/gisserver910/rest/services/DataExplorer/PropertySales/MapServer/15):
it is **2026, under Improved Single-Family Residential**, not a whole-county,
all-property-type feed. It exposes STRAP/FOLIOID, site address, four sale slots
with date/amount/official-record number, and VI/transaction-code fields. It has
polygon geometry, a 2,000-record response cap, and pagination support.

Before integration: resolve the complete year/category layer inventory, published
transaction-code meanings, sale qualification, historical attribute semantics,
pagination completeness, parcel changes, and data-use terms. Current stated/GIS
area is not automatically the area transferred at an earlier sale. Do not infer
new construction from NEWBUILT or later building fields without a documented basis.

The [Clerk's Official Records service](https://www.leeclerk.org/departments/official-records-services)
is the deed/document corroboration path. Interactive access is not proof of a
licensed bulk/API feed. [Community Development](https://www.leegov.com/dcd)
handles unincorporated Lee County; municipal properties require the applicable
municipal authority. [Zoning](https://www.leegov.com/dcd/zoning) and
[permitting](https://www.leegov.com/dcd/buildingpermitservice) must be evaluated
alongside parcel-specific flood and development restrictions.

## Mecklenburg County, North Carolina

Research identified county [GIS/POLARIS](https://gis.mecknc.gov/) and
[Land Records Management](https://gis.mecknc.gov/Land-Records-Management) as property
identity leads. Root's independent web fetch of the GIS landing returned HTTP403;
this is an access observation, not evidence that public access is prohibited or
that the service is unavailable to all clients.

The [Register of Deeds real-estate records](https://deeds.mecknc.gov/services/real-estate-records)
is the document corroboration lead. A repeatable county-wide sale-price/date feed
and its authorized production-use contract were not verified in this bounded pass.

Root verified Charlotte's [official zoning page](https://www.charlottenc.gov/Growth-and-Development/Planning-and-Development/Zoning/Zoning-Ordinance):
the current zoning standards are in UDO Articles 1-22, while the prior ordinance
is archived and may remain relevant to some conditional districts. This does not
establish one zoning authority for every parcel in Mecklenburg County. Resolve
the parcel's municipality and planning jurisdiction before selecting an ordinance.

Current repository inspection found a registered Mecklenburg property provider,
but no Mecklenburg automatic comp route. The existing provider uses first-result
selection and a value-based area-unit heuristic; these behaviors require source-
contract and real-property validation before launch. Existing code is not coverage
proof, and no runtime repair was attempted in this scope-change pass.

## Gaston County, North Carolina

Root verified the county's [Tax Mapping / GIS page](https://www.gastongov.com/677/Tax-Mapping-GIS).
It identifies the county-wide tax parcel layer as derived from deeds, plats and
other public records, and links the [county GIS](https://gis.gastoncountync.gov/),
[Register of Deeds](https://deeds.gastongov.com/), and
[Wedge property-tax search](https://gastonnc.devnetwedge.com/). These are different
sources with different purposes; a tax assessment is not a closing price.

Exact transaction amounts/dates, historical property characteristics, bulk/API
access, and data-use terms remain to be verified. Identify the municipality and
zoning jurisdiction before choosing a county or city ordinance. No dedicated
Gaston property provider or automatic comp route was found in the inspected
registration/source-router files.

## Scope and next acceptance work

Recommended sequence: stabilize Miami-Dade/Broward/Palm Beach first, validate Lee,
then Mecklenburg and Gaston. Each target needs real representative subject and
sale evidence, deterministic qualification, reviewable rejection/conflict reasons,
and repeated real-app success/failure cases. San Diego's unavailable sale feed is
no longer a launch prerequisite. State political labels are not a source-quality,
parcel-entitlement, or investment-feasibility rule.

The app goal was observed paused. This inventory does not resume it. Provider
budgets and the priority of reliable results before sign-in remain unchanged.
