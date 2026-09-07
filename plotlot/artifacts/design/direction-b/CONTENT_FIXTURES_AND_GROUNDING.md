# Content Fixture, Calculations, Evidence, and Grounded Analysis

## Deterministic redacted fixture

All examples in Direction B derive from `fixture-direction-b-v1.json`. It contains no street address, coordinates, owner, customer, or source URL. The canonical redacted identity is `30-••••••-••••`; it is a formatting sample, not an APN. The SHA-256 of this exact fixture is recorded in `checksums.sha256`.

The sample is deliberately incomplete: rear setback and overlay review are unresolved. Its capacity and purchase-ceiling values must therefore remain absent. A polished non-zero unit count or dollar figure would violate the interface contract.

## Coverage truth

| Territory | Product state | What is allowed | What is prohibited |
| --- | --- | --- | --- |
| Miami-Dade | private beta | resolve eligible parcels, surface sourced evidence, run gated deterministic/grounded workflows | representing all municipalities/records as complete or generally available |
| Broward / Palm Beach | municipality-conditional | resolve context and show coverage policy; enable only after municipality and sources pass policy | countywide claim, pre-filled feasibility result, implied eligibility |
| San Diego | planned / not enabled | capture a locator or interest context and display planned policy | zoning/capacity/ceiling result, LLM feasibility answer, “beta” implication |

## Evidence record schema and replay

```ts
type EvidenceRecord = {
  id: string;                    // E-01, immutable within a dossier version
  kind: "survey_or_plat" | "zoning_record" | "dimensional_schedule" | "constraint_layer" | "comp_source";
  authority: string;
  retrievedAt: string;
  sourceVersion?: string;
  contentHash: `sha256:${string}`;
  locator: { page?: number; section?: string; featureId?: string };
  extraction?: { method: "verbatim" | "structured"; transformVersion: string };
  status: "verified" | "needs_verification" | "conflict" | "unavailable";
};

type EvidenceReplay = {
  record: EvidenceRecord;
  excerptOrFeature: string;
  usedBy: Array<{ claimId: string; displayField: string; calculationVersion?: string }>;
  supersedes?: string;
};
```

Replay is a graph, not an attachment preview. The UI must show source identity, retrieval date, hash, source locator, extraction method, and all downstream claims that used the record. A content hash cannot be fabricated from a summary. Restricted source material may expose redacted metadata plus the reason the excerpt cannot be displayed.

## Deterministic capacity / max-units contract

Capacity is a derived claim, not a zoning label. It is computed only when the required source inputs are verified and mutually compatible.

```text
buildable_envelope = parcel_geometry − front_setback − side_setbacks − rear_setback
zoning_density_limit = floor(net_lot_area / minimum_lot_area_per_unit)
envelope_limit = yield_from(buildable_envelope, height, coverage/FAR, parking, applicable rules)
overlay_limit = applicable_overlay_limit_or_infinity
max_units = min(zoning_density_limit, envelope_limit, overlay_limit)
```

Required inputs: canonical parcel geometry, jurisdiction/district, current applicable dimensional rules (including exceptions), density/minimum lot area, coverage/FAR/height where applicable, overlays, and calculation version. Parking, access, lot splits, concurrency, use permissions, and entitlement discretion are represented separately, never silently assumed away.

| Input state | Output behavior |
| --- | --- |
| all governing inputs verified | show `Derived estimate: N units`, governor, formula, units, and citations |
| explicit lower/upper bounds verified | show range and why it is a range; never call the upper end “max units” |
| one materially governing value absent (fixture case) | `Capacity unavailable — rear setback / overlay review required`; no numeric unit count |
| records conflict | `Capacity abstains — conflicting records`; show conflict sources and affected formula input |
| market not enabled | no formula evaluation, no capacity card value |

## Constraints and survey/plat contract

Constraints are scoped facts: flood/overlay records report layer/source date and whether geometry intersection was evaluated; environmental, historic, access, utility, and title items each report their own authority/scope. “No mapped feature” is not “no constraint.”

Survey/plat content shows document type, recording/date, page/locator, boundary extraction, and conflicts with atlas geometry. If survey/plat boundary disagrees with a parcel layer, the map uses a conflict outline and calculations abstain unless the governing geometry policy selects a cited source.

## Comps and provisional purchase ceiling

Comps are a source set with a transparent inclusion rule, not an unlabeled market card. Every comparable identifies type, date, source, distance/market rationale, adjustment policy, exclusion reason, and confidence status. Inferred adjustments are labeled as such.

```text
provisional_purchase_ceiling = stabilized_value
                              − hard_cost
                              − soft_cost
                              − finance_and_carry
                              − contingency
                              − target_margin
```

The sheet pins the capacity calculation version and comp-set version. It explicitly lists excluded risks (for example entitlement timing, unknown utilities, or environmental mitigation). If capacity is unavailable, comp set is inadequate, or costs/margin are not supplied under a cited assumption set, it displays no dollar conclusion. It can state: `Purchase ceiling unavailable — resolve capacity and comp basis.`

## Grounded LLM analysis and abstention

The LLM is a bounded synthesis layer, not a research authority. It receives only the parcel identity, coverage policy, record excerpt/structured fields, source IDs, evidence status, calculation outputs, and approved templates. It must return structured JSON that validates citations before render.

```ts
type GroundedBrief = {
  status: "supported" | "partial" | "abstains";
  observations: Array<{ text: string; evidenceIds: string[] }>;
  derivedSummary?: { text: string; calculationVersion: string; evidenceIds: string[] };
  unknowns: Array<{ field: string; reason: string; evidenceIds: string[] }>;
  nextEvidenceRequest?: { need: string; why: string; allowedSourceKinds: string[] };
  prohibitedContent: "no_external_facts" | "no_legal_advice" | "no_uncited_capacity_or_price";
};
```

Render gate:

1. Reject an observation without one or more existing evidence IDs.
2. Reject citations that are not in the dossier or whose status cannot support the claim.
3. When a required capacity/ceiling input is unresolved, force `status: abstains`; do not permit a prose workaround or “likely” estimate.
4. State the blocking record and next acceptable evidence request in plain language.
5. Never browse the open web or fill a missing authority from model memory in this surface.

Fixture-safe example:

> `Abstains. The available dimensional schedule does not verify a rear setback, and the constraint layer requires review (E-03, E-04). A maximum-unit estimate and purchase ceiling are therefore unavailable. Request the current rear-setback schedule and a reviewed overlay record.`

This is an example of rendered copy, not a legal, engineering, or valuation conclusion.
