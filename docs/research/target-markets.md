# PlotLot target-market acquisition fact base

**Markets:** San Diego County, Miami-Dade County, Broward County, and Palm Beach County
**Primary audience:** PlotLot founders
**Sources accessed:** July 25, 2026
**Scope:** General contractors, land developers, public lead sources, procurement, permitting data, and integration constraints

This report separates **verified facts** from **recommendations/inferences**. All market facts link to a government source. Recommendations are based on those facts and PlotLot's current operating model; they are not claims made by the cited agencies.

## Executive decision

**Recommendation/inference:** Launch customer acquisition in this order:

1. **Miami-Dade County and the City of San Diego as the first data-led markets.** Both have official, machine-readable permit feeds. Miami-Dade also publishes a contractor dataset and purchase-order data. These sources make it possible to identify accounts, enrich outreach, and prototype a repeatable connector with less manual work.
2. **Palm Beach County as the first land-developer-focused expansion.** County zoning and Development Review Officer records provide useful entitlement signals, but county permitting covers only unincorporated territory and the county contains 39 municipalities.
3. **Broward County as a procurement- and partner-led expansion.** The county has a strong public procurement channel and local contractor directory, but county permitting jurisdiction is a small unincorporated area. County-wide coverage requires municipal connectors.

The four markets collectively contain:

- **7,997 employer establishments** in NAICS 236, Construction of Buildings, employing 52,447 people in 2023.
- **52,712 nonemployer establishments** in NAICS 236 in 2023, showing that the small-business universe is much larger than employer-only counts suggest.
- **35,160 authorized residential housing units** in 2025.

Those are useful demand proxies, not PlotLot's serviceable obtainable market. They do not count unique general contractors or land developers, and the residential permit measure excludes nonresidential construction.

## Market sizing proxies

### Employer establishments

The latest currently published Census County Business Patterns county file is 2023. CBP covers employer businesses with paid employees. The table uses NAICS 236, Construction of Buildings, which includes residential and nonresidential building contractors but is broader than PlotLot's ideal-customer profile.

| County | NAICS 236 establishments | Employment | Residential building establishments | Nonresidential building establishments |
|---|---:|---:|---:|---:|
| San Diego | 2,847 | 23,326 | 2,390 | 457 |
| Miami-Dade | 2,009 | 10,379 | 1,601 | 408 |
| Broward | 1,535 | 10,113 | 1,212 | 323 |
| Palm Beach | 1,606 | 8,629 | 1,358 | 248 |
| **Total** | **7,997** | **52,447** | **6,561** | **1,436** |

Sources: [Census CBP API and data documentation](https://www.census.gov/data/developers/data-sets/cbp-zbp/cbp-api.html), [2023 County Business Patterns release](https://www.census.gov/data/datasets/2023/econ/cbp/2023-cbp.html), and [official 2023 county file](https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23co.zip).

**Limitation:** An establishment is a location, not necessarily a unique firm or decision-maker. Sole proprietors and other nonemployers are not represented.

### Nonemployer and land-subdivision signals

Nonemployer Statistics covers businesses with no paid employees and at least $1,000 in annual receipts, except construction, for which the threshold is $1. NAICS 237210, Land Subdivision, is a narrow developer-related category; many actual land developers will instead appear under another industry, entity, or project applicant.

| County | Nonemployer Construction of Buildings | Employer Land Subdivision | Nonemployer Land Subdivision |
|---|---:|---:|---:|
| San Diego | 7,170 | 56 | 30 |
| Miami-Dade | 28,462 | 62 | 73 |
| Broward | 10,608 | 22 | 34 |
| Palm Beach | 6,472 | 30 | 20 |
| **Total** | **52,712** | **170** | **157** |

Sources: [Census Nonemployer Statistics API documentation](https://www.census.gov/data/developers/data-sets/nonemp-api.html), [official 2023 Nonemployer Statistics file](https://www2.census.gov/programs-surveys/nonemployer-statistics/data/2023/NS2300NONEMP.zip), and the CBP sources above.

**Limitation:** These counts are not licensed-contractor or developer counts and should not be added directly to the employer table as a unique-account total. A practical prospect universe requires entity resolution across licenses, businesses, locations, and project records.

### Residential authorizations

The Census Building Permits Survey measures new privately owned residential construction. The 2025 county estimates are final and include imputation.

| County | 1-unit | 2-unit | 3–4-unit | 5+-unit | Total units | Authorized value |
|---|---:|---:|---:|---:|---:|---:|
| San Diego | 3,506 | 628 | 262 | 7,311 | 11,707 | $2.506B |
| Miami-Dade | 2,666 | 318 | 259 | 13,292 | 16,535 | $4.730B |
| Broward | 712 | 64 | 10 | 1,904 | 2,690 | $715.1M |
| Palm Beach | 2,495 | 118 | 112 | 1,503 | 4,228 | $1.667B |
| **Total** | **9,379** | **1,128** | **643** | **24,010** | **35,160** | **$9.618B** |

Sources: [Census Building Permits Survey](https://www.census.gov/construction/bps/index.html) and [official 2025 county estimates](https://www2.census.gov/econ/bps/County/co2025a.txt).

**Limitation:** These are housing units authorized, not projects, construction value, land transactions, or nonresidential permits.

## Build the prospect universe from licenses, then qualify it with activity

### California

The Contractors State License Board provides:

- A [city, ZIP code, and classification search](https://cslb.ca.gov/OnlineServices/checklicenseII/ZipCodeSearch.aspx). Class B is General Building and Class A is General Engineering.
- A [public data portal](https://web.cslb.ca.gov/Onlineservices/DataPortal/) with downloadable license master, workers' compensation, and personnel files. The license master includes business name, address, phone, status, dates, and classifications, but not email.
- A [live license-status check](https://web.cslb.ca.gov/OnlineServices/CheckLicenseII/checklicense.aspx).

**Recommendation/inference:** Build the San Diego seed list from active A and B licenses, deduplicate businesses across classifications and locations, then rank them using recent permit and entitlement activity. Do not treat a license as evidence of current demand.

### Florida

The Florida Department of Business and Professional Regulation distinguishes a **certified contractor**, licensed to work statewide, from a **registered contractor**, whose work is limited to the jurisdictions where local competency requirements were met. The prefixes C and R identify those categories. See the [DBPR Construction Industry overview](https://www2.myfloridalicense.com/construction-industry/).

DBPR provides:

- An [authoritative license search](https://www.myfloridalicense.com/wl11.asp?mode=0) by name, license number, city/county, and license type.
- [Public license downloads](https://www2.myfloridalicense.com/construction-industry/public-records/) for active, inactive, and voluntarily inactive licenses. The download excludes null-and-void, delinquent, and involuntarily inactive records.

Florida law continues to assign counties and municipalities responsibility for permits, fees, and inspections. A statewide credential therefore does not create a single statewide permitting workflow. See [Florida Statutes §489.131](https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&Search_String=&URL=0400-0499%2F0489%2FSections%2F0489.131.html) and [§489.117](https://www.leg.state.fl.us/statutes/index.cfm?App_mode=Display_Statute&Search_String=&URL=0400-0499%2F0489%2FSections%2F0489.117.html).

The Florida Division of Corporations offers [Sunbiz entity search](https://search.sunbiz.org/Inquiry/CorporationSearch/ByName) and [bulk corporate data downloads](https://dos.fl.gov/sunbiz/other-services/data-downloads/). These are useful for validating legal names, officers, and entity status, but they are not contractor-license records.

**Recommendation/inference:** Seed each South Florida market from DBPR's certified and registered contractor records, validate live status before outreach, then join county and municipal contractor records where available. Use Sunbiz for entity resolution, not qualification.

**Finding/inference:** No official general-purpose “land developer” registry was found. Build that segment from named applicants, owners, agents, and related entities in entitlement, plat, zoning, environmental-review, permit, parcel, and public-record sources.

## County acquisition and data playbooks

## 1. San Diego County

### Jurisdiction reality

San Diego County contains 18 incorporated cities, while the county government handles the unincorporated area. The [County's jurisdiction FAQ](https://www.sandiegocounty.gov/content/sdc/redistricting/frequently-asked-questions--faq-.html) confirms this split.

**Implication/inference:** “San Diego County coverage” is not one connector. The City of San Diego is the best first wedge; the unincorporated county and the other cities should be added by account demand and permit volume.

### Verified lead sources

1. **City permit activity.** The City of San Diego publishes a [Development Permits dataset](https://data.sandiego.gov/datasets/development-permits/) updated daily. Downloadable CSVs include project title and scope, address, assessor parcel number, dates, status, estimated valuation, unit and floor information, and permit holder. The [2026 approvals-issued CSV](https://seshat.datasd.org/development_permits/approvals_issued_2026_datasd.csv) is a current example.
2. **State entitlement activity.** [CEQAnet](https://ceqanet.lci.ca.gov/) supports advanced search by date, document type, lead agency, and public agency. Individual environmental documents may identify an applicant or agent. See [CEQAnet advanced search](https://ceqanet.lci.ca.gov/Search/Advanced).
3. **County procurement.** [BuyNet](https://www.sandiegocounty.gov/content/sdc/purchasing/DoingBusiness.html) publishes RFQs, RFBs, RFPs, RFSQs, and RFIs. Registration is free and vendors can subscribe by commodity.
4. **City procurement.** The City uses [PlanetBids](https://www.sandiego.gov/purchasing/bids-contracts/vendorreg) for vendor registration, solicitations, planholders, addenda, and awards.

**Recommendation/inference:** Use permit activity as the high-volume GC signal and CEQAnet as a lower-volume, earlier-stage developer signal. Treat environmental notices as warm account research, not as a complete land-developer registry.

### Data and integration posture

- **Supported now:** Daily City of San Diego CSV ingestion and CSLB bulk/license-status joins.
- **Portal workflow:** The unincorporated county uses [Accela Citizen Access](https://publicservices.sandiegocounty.gov/CitizenAccess/Cap/CapApplyDisclaimer.aspx?TabName=LUEG-PDS&module=LUEG-PDS). A documented bulk permit API was not verified during this review.
- **Discovery source:** The county maintains a [directory of public data portals](https://www.sandiegocounty.gov/content/sdc/cob/public-records/data_portals.html).

**Initial account thesis/inference:** Favor active Class B firms with multiple permits in the last 180 days, higher cumulative valuation, repeated work in PlotLot-covered project types, and a named preconstruction, estimating, acquisitions, development, or operations leader.

## 2. Miami-Dade County

### Jurisdiction reality

Miami-Dade has [34 incorporated municipalities](https://www.miamidade.gov/global/management/municipalities.page). The county's code administration supports [35 building departments](https://www.miamidade.gov/global/economy/board-and-code/home.page), effectively the municipalities plus the unincorporated county. Each municipality has its own building official and permitting process. The [county-and-municipal approval page](https://www.miamidade.gov/global/economy/building/county-municipal-approval.page) and [permit application guidance](https://www.miamidade.gov/global/economy/building/how-to-apply-for-permit.page) explain the split. County permitting generally applies to properties whose folio begins with “30,” identifying unincorporated Miami-Dade.

**Implication/inference:** The county feed is a strong first connector but not complete coverage of Miami, Miami Beach, Coral Gables, Doral, or the other municipalities.

### Verified lead sources

1. **Machine-readable permits.** Miami-Dade publishes a [permit FeatureServer](https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/miamidade_permit_data/FeatureServer) covering the prior two years through the present. [Layer 0](https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/ArcGIS/rest/services/miamidade_permit_data/FeatureServer/0) exposes permit and process numbers, dates, project type, proposed use, value, comments, folio, owner, property address, architect, contractor identity and phone, square footage, units, floors, inspections, and fees. The service supports standard ArcGIS queries and JSON/GeoJSON responses.
2. **Machine-readable contractor records.** The county publishes a [contractor daily-data FeatureServer](https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/contractor_daily_data/FeatureServer). Its contractor layer contains contractor identity, license/type, business address and phone, status and renewal data, DBA, email, trade class, category, and expiration fields.
3. **Public permit lookup.** The [building permit search](https://www.miamidade.gov/global/service.page?Mduid_service=ser149695713973833) supports address, permit, and process searches. Some plans are on microfilm or subject to fees.
4. **Procurement pipeline.** The county routes competitive goods, services, A&E, and design-build solicitations through [INFORMS](https://www.miamidade.gov/global/service.page?Mduid_service=ser1555532436896147). It also publishes [future solicitations](https://www.miamidade.gov/apps/ISD/stratproc/Home/FutureSolicitations).
5. **Incumbent/spend intelligence.** The [2026 procurement purchase-order FeatureServer](https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/miamidade_procurement_data_informs_2026/FeatureServer) exposes supplier, purchase-order amount and date, description, category, and contract ID.
6. **Land-development pipeline.** The county's [Comprehensive Development Master Plan portal](https://www.miamidade.gov/global/economy/planning/cdmp/home.page) publishes amendment cycles and hearing information.
7. **Entity and property enrichment.** The [Property Appraiser search](https://www.miamidadepa.gov/pa/real-estate/property-search.page) provides folio, ownership, address, and sales information. The county also provides a [local contractor search](https://wwwx.miamidade.gov/Apps/RER/BCCOContractorMenu) for Certificates of Competency and status.

### Data and integration posture

- **Supported now:** ArcGIS REST queries for permits, contractors, and purchase orders; DBPR bulk and live status; Sunbiz entity validation.
- **Terms control:** The county's ArcGIS item metadata states that open data is provided as-is and may be approximate; it should not be used alone for site-specific or financial commitments. Preserve the source and terms metadata with every record. See the [official item metadata](https://www.arcgis.com/sharing/rest/content/items/6db5f56e886446df88313ca279e59120?f=pjson).
- **Municipal gap:** Connector discovery is still required for each city that matters to a signed customer.

**Initial account thesis/inference:** Start with contractors and developers tied to multiple recent permits, major valuations, multifamily units, commercial work, or repeated folios. The county contractor feed makes this the best market for testing a license-to-activity-to-contact pipeline.

## 3. Broward County

### Jurisdiction reality

Broward has 31 municipalities plus county government. The remaining Broward Municipal Services District is a small unincorporated area. See the [Broward Planning Council setting](https://www.broward.org/PlanningCouncil/Pages/Setting.aspx) and [current county quick facts](https://www.broward.org/Planning/Demographics/Pages/QuickFacts.aspx).

The county's building division handles the unincorporated area and directs projects in incorporated areas to the relevant city. See [State Contractor Registration](https://www.broward.org/Building/Contractors/Pages/StateContractorRegistration.aspx).

**Implication/inference:** A county-only permit integration would miss most Broward construction activity.

### Verified lead sources

1. **Local contractor records.** Broward provides a [contractor-license search](https://dpepp.broward.org/BCS/Default.aspx?PossePresentation=SearchForContractorLicense) by license, name, or firm. The county says its board issues local certificates of competency to more than 12,000 tradespeople; that figure is not a count of general contractors. See the [Contractor Licensing page](https://www.broward.org/Building/Contractors/Pages/Default.aspx).
2. **Permit routing.** [ePermits OneStop](https://www.broward.org/Building/BuildingPermits/Pages/ePermits-OneStop.aspx) coordinates county approvals with participating cities, but a project begins with its local municipality.
3. **Procurement.** Broward uses [BPRO/Bonfire](https://www.broward.org/Purchasing/Pages/BPRO.aspx) for vendor registration, solicitation search and response, bid results, and notices. The [Purchasing page](https://www.broward.org/Purchasing/Pages/Default.aspx) is the current starting point.
4. **County buying signal.** [Broward Is Buying](https://www.broward.org/EconDev/Outreach/Pages/BrowardIsBuying.aspx) says county buying averages more than $1 billion annually and identifies development, A&E, project management, renovation, grading, demolition, utility, and trade categories.
5. **Partner/subcontractor discovery.** The [Certified Firm Directories](https://www.broward.org/EconDev/DoingBusiness/Pages/CertifiedFirmDirectories.aspx) include contact details, business descriptions, NAICS codes, and a downloadable dashboard. This is a certified-firm directory, not the entire GC market.
6. **Development pipeline.** County [plat review](https://www.broward.org/Planning/Development/platting/Pages/default.aspx), [Development Review](https://www.broward.org/Planning/Development/pages/default.aspx), and [Local Planning Agency agendas](https://www.broward.org/Planning/Pages/LPA.aspx) expose plats, development reviews, rezonings, and comprehensive-plan actions.
7. **GIS discovery.** The county's [GIS page](https://www.broward.org/Planning/Pages/GIS.aspx) links to the [Broward GeoHub](https://geohub-bcgis.opendata.arcgis.com/).

### Data and integration posture

- **Supported now:** DBPR bulk and live status, Sunbiz enrichment, and available Broward GeoHub datasets.
- **Portal workflow:** Broward contractor search, ePermits OneStop, and BPRO are portal-led. A documented bulk API for a county-wide normalized permit feed or BPRO was not verified.
- **Avoid stale workflow:** Some older county pages still reference BidSync. BPRO/Bonfire is the current procurement route.

**Initial account thesis/inference:** Enter Broward through public procurement, certified partner relationships, and high-confidence municipal pilot customers. Do not promise county-wide automated permit coverage until the customer's actual municipalities and supported export methods are mapped.

## 4. Palm Beach County

### Jurisdiction reality

Palm Beach County lists [39 municipalities](https://discover.pbc.gov/Pages/Municipalities.aspx), each with its own local policies. The county [Permit Center](https://discover.pbc.gov/pzb/building/Pages/Permit-Center.aspx) serves unincorporated Palm Beach County.

**Implication/inference:** Like Broward, Palm Beach requires a municipal connector roadmap. The county's zoning pipeline is still valuable for land-development targeting.

### Verified lead sources

1. **County permits.** The county offers ePZB and [permit-record search services](https://discover.pbc.gov/pzb/administration/Pages/Search-Services-Administration.aspx) for unincorporated territory. The workflow is portal/account based, and certified searches may carry a fee.
2. **Contractor verification.** [Contractor Regulations](https://discover.pbc.gov/pzb/CodeCompliance/Pages/Contractor-Regulations.aspx) links county and state license searches. State preemption has changed the set of locally licensed trades, so DBPR must remain the statewide authority.
3. **Procurement.** The county's [Business Opportunities](https://discover.pbc.gov/procurement/Pages/Business-Opportunities.aspx) page directs vendors to Vendor Self Service as the official solicitation advertising system. [IFB/RFP guidance](https://discover.pbc.gov/procurement/Pages/IFB-RFP.aspx) explains that email alerts depend on accurate commodity codes.
4. **Vendor discovery.** The [public county vendor search](https://pbc.gov/pbcvendors) exposes company, city, commodity, ownership/classification, email, and phone fields. It is useful for incumbents and partners, not a complete GC universe.
5. **Development pipeline.** The [Zoning Development Review](https://discover.pbc.gov/pzb/zoning/Sections/Development-Review.aspx) and [DRO Results and Certification](https://discover.pbc.gov/pzb/zoning/Pages/DRO-Results-and-Certification.aspx) pages expose submitted, approved, administrative, and hearing-ready applications.

### Data and integration posture

- **Supported now:** DBPR bulk/live status, Sunbiz enrichment, and downloadable documents or exports explicitly offered by county systems.
- **Portal workflow:** ePZB, Vendor Self Service, and local permit systems require account/workflow validation. A documented county bulk permit API was not verified.
- **Municipal gap:** West Palm Beach, Boca Raton, Delray Beach, Palm Beach Gardens, Jupiter, and other cities operate their own local procedures.

**Initial account thesis/inference:** Target developers appearing in DRO/zoning activity and active contractors with repeated single-family or community-scale work. Sell a customer-specific workflow first, then add the municipality connectors that customer actually needs.

## Founder acquisition operating plan

### 1. Define the initial ICP

**General contractor ICP**

- Active, verifiable general-building/general-contractor license.
- At least two relevant permit or procurement signals in the last 180 days.
- Work in PlotLot-supported project types and geographies.
- A repeatable preconstruction, estimating, zoning, feasibility, or site-selection workflow.
- A reachable decision-maker in preconstruction, estimating, operations, business development, or the executive team.

**Land developer ICP**

- Named applicant, owner, agent, or related entity in a recent entitlement, plat, environmental, zoning, or master-plan action.
- Multiple active sites or a visible repeat-development pattern.
- A need to compare parcels, zoning constraints, buildability, or early project economics.
- A reachable acquisitions, development, land, entitlement, or principal-level decision-maker.

### 2. Allocate the first 200 named accounts

**Recommendation/inference:**

| Market | Initial accounts | Primary source |
|---|---:|---|
| Miami-Dade | 70 | Permit + contractor ArcGIS feeds |
| San Diego | 55 | City permit CSV + CSLB + CEQAnet |
| Palm Beach | 40 | DBPR + DRO/zoning + county vendors |
| Broward | 35 | DBPR/local licenses + BPRO + plats |

This is a learning allocation, not a TAM allocation. Rebalance after four weeks using qualified-reply, discovery-call, and pilot-conversion rates.

### 3. Score for a reason to contact now

Suggested 100-point model:

- 25 points: two or more recent project signals.
- 20 points: high cumulative valuation, unit count, square footage, or public contract value.
- 15 points: entitlement or pre-permit stage where PlotLot can change a decision.
- 15 points: active license and verified entity.
- 15 points: project type and jurisdiction already supported by PlotLot.
- 10 points: named, role-appropriate decision-maker with a business contact channel.

Every outreach note should cite one current, property- or project-specific reason for contacting the account.

### 4. Use a controlled outreach sequence

**Recommendation/inference:**

1. Send a brief, manually reviewed email about the observed project/workflow and the decision PlotLot can accelerate.
2. Do not include the demo URL in the first cold message. Share it after a reply or during a scheduled walkthrough.
3. Follow up once with an additional useful observation, not a generic bump.
4. Use manual calling only where the business number and legal basis are clear.
5. Stop and suppress the account immediately after an opt-out or do-not-call request.
6. Never source or enrich from CoStar.

### 5. Measure the funnel by source and jurisdiction

At minimum, track:

```text
source_system
source_record_id
source_url
retrieved_at
terms_version
jurisdiction
property_address
apn_folio_pcn
owner_or_applicant
contractor_name
contractor_license
permit_or_application_type
status
application_date
issue_or_hearing_date
estimated_value
units_or_square_feet
contact_role
outreach_status
do_not_contact
```

Track conversion separately for license-only, permit, entitlement, procurement, and referral leads. That will show which public signal predicts a real PlotLot buyer rather than merely producing names.

## Customer implementation guide

The market research changes implementation strategy in one important way: the integration boundary must be defined by the customer's jurisdictions and source systems, not merely by county name.

### Discovery and solution design

1. Inventory the customer's decision workflow from parcel discovery through feasibility, entitlement, estimating, approval, and handoff.
2. Identify the systems of record: CRM, project management, document storage, GIS, parcel/permit sources, estimating tools, and identity provider.
3. List the exact municipalities where the customer works and the monthly volume by jurisdiction.
4. Classify every source as API, supported bulk export, customer-provided file, authenticated portal, or manual workflow.
5. Agree on the decisions PlotLot will support and the human approval points. Do not promise fully autonomous permitting or financial decisions.

### Pilot

1. Select one workflow, one project type, and one or two jurisdictions.
2. Back-test against 10–20 completed projects to measure recall, accuracy, freshness, and time saved.
3. Run 5–10 live projects in parallel with the customer's existing process.
4. Require source citations and confidence/status markers in every customer-facing result.
5. Record exceptions: missing municipality, stale permit, parcel mismatch, restricted document, or ambiguous contractor/entity match.

### Production integration

1. Use official APIs and supported exports first; do not bypass authentication, CAPTCHAs, rate limits, or terms.
2. Maintain a source registry with owner, jurisdiction, authentication method, terms, schema version, refresh cadence, and incident contact.
3. Normalize jurisdiction-specific records into PlotLot's canonical parcel, permit, entitlement, contractor, and source-evidence models.
4. Preserve raw source identifiers and retrieval timestamps so every answer is auditable.
5. Use least-privilege service accounts, tenant isolation, encryption, retention rules, and customer-approved roles.
6. Write results back only to systems and fields approved during implementation. Keep a complete change log.
7. Monitor freshness, failed syncs, schema drift, duplicate/entity-match rates, citation completeness, and customer corrections.
8. Expand municipality by municipality after the pilot meets agreed acceptance thresholds.

### Suggested acceptance criteria

These thresholds should be negotiated per customer:

- At least 95% successful scheduled syncs.
- 100% of material PlotLot findings link to or identify their source record.
- No cross-tenant data exposure.
- Human review for low-confidence parcel/entity matches and any external write.
- A documented fallback when a portal or government feed is unavailable.
- Customer sign-off on back-test accuracy and live-project time savings before expanding scope.

## Outreach, privacy, and procurement controls

This section is operational guidance, not legal advice. Counsel should review the final acquisition program and customer data terms.

- **Commercial email:** The FTC says CAN-SPAM applies to B2B email. Headers and subject lines must be accurate; commercial messages need a valid postal address, a clear opt-out, and opt-outs honored within 10 business days. The sender remains responsible for vendors acting on its behalf. See the [FTC CAN-SPAM compliance guide](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business).
- **Calls and texts:** Default to manually reviewed business email and manual dialing. Do not use automated or prerecorded calls or marketing texts without counsel-confirmed consent and suppression controls. Florida's [Telephone Solicitation Act](https://www.leg.state.fl.us/Statutes/index.cfm?App_mode=Display_Statute&URL=0500-0599%2F0501%2FSections%2F0501.059.html) and federal TCPA rules require specific analysis.
- **California privacy:** Publicly available government and professional-license records may receive different treatment under the CCPA, but combining, selling, sharing, or using personal information can still create obligations if PlotLot is in scope. Public availability is not marketing consent. See the [California Attorney General's CCPA guidance](https://oag.ca.gov/privacy/ccpa).
- **Procurement contacts:** Miami-Dade's [Cone of Silence](https://www.miamidade.gov/global/strategic-procurement/procedures-cone-of-silence.page) restricts certain communications after a solicitation is advertised. Broward also publishes procurement communication and lobbying rules on its [Purchasing](https://www.broward.org/Purchasing/Pages/Default.aspx) and [Lobbyist Information](https://www.broward.org/Commission/Pages/LobbyistInformation.aspx) pages. Route solicitation communications only through the authorized channel.
- **Protected plans:** Some commercial building plans and security-related records are restricted under Florida public-records law. Miami-Dade explains this on its [Construction Permitting Procedures](https://www.miamidade.gov/global/economy/building/construction-permitting-procedures.page). PlotLot should not acquire or expose restricted plans.
- **Data provenance:** Store source URL, source record ID, retrieval time, jurisdiction, and applicable terms with every record. Prefer business contact details over home/personal information, minimize retained data, and maintain a cross-channel suppression list.

## Verified access versus remaining validation

| Status | Source/access pattern | Current implication |
|---|---|---|
| **Green — machine-readable** | City of San Diego permit CSV; Miami-Dade permit, contractor, and purchase-order ArcGIS services; CSLB and DBPR public license files | Suitable for a supported ingestion proof of concept, subject to terms, schema, and freshness monitoring |
| **Yellow — searchable/portal-led** | CEQAnet; San Diego County Accela; Broward ePermits, contractor search, BPRO, and GeoHub; Palm Beach ePZB, VSS, and zoning documents | Use supported search/export workflows; verify API/export rights and authentication with the agency or customer before automation |
| **Red — not yet normalized** | All municipalities across San Diego, Miami-Dade, Broward, and Palm Beach; de-duplicated contractor/developer universe; customer contact permissions | Do not represent this as complete county-wide coverage; validate and build by signed-customer need |

## Decisions the founders should make next

1. Approve City of San Diego and unincorporated Miami-Dade as the two public-data connector proofs of concept.
2. Assign an owner to build the first 200-account list and record a source URL for every account.
3. Choose one GC workflow and one developer workflow for customer discovery; avoid a generic “AI for construction” pitch.
4. Define a standard customer source inventory and municipality-coverage checklist.
5. Have counsel review the outreach sequence, privacy notice, data processing terms, and automated-communications policy before scaling.
6. Set explicit “supported,” “customer-provided,” and “manual research” labels in product and sales materials so county-wide claims remain accurate.
