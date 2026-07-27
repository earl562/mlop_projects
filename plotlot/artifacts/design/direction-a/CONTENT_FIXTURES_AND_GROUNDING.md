# Content fixtures, evidence provenance, and grounded analysis

## Fixture boundaries

The canonical fixture is [`fixtures/redacted-acquisition-case.json`](fixtures/redacted-acquisition-case.json). It is deliberately synthetic and redacted: `12•• NW 67 ST`, `FOLIO 30-3115-•••-0420`, and `APN 436-302-••-00` are display fixtures, not customer or private addresses. All zoning, setbacks, capacity, comps, and price values demonstrate product shape only. They are not legal, title, survey, appraisal, underwriting, entitlement, or investment advice.

### Coverage truth

| Area shown in the workbench | Truthful state | Allowed experience |
|---|---|---|
| Miami-Dade | **Private beta** | Parcel-level evidence and analysis may proceed when jurisdiction/evidence gates pass |
| Broward | **Municipality-conditional** | Ask for/select a supported municipality; no countywide enabled claim |
| Palm Beach | **Municipality-conditional** | Ask for/select a supported municipality; no countywide enabled claim |
| San Diego County | **Planned, not enabled** | Context capture/waitlist only; no activated zoning/capacity/underwriting analysis |

The “City of San Diego” APN display row is included solely to make planned coverage understandable. It does not imply that San Diego is live, countywide, municipality-wide, or powered by this product direction.

## Evidence sequence and example values

| Ledger order | Evidence | Illustrative output | Provenance requirement | If unavailable/conflicting |
|---:|---|---|---|---|
| 1 | Parcel identity | Redacted parcel, folio, legal description, small parcel outline | `PA-24-98123`, issuer, effective date, SHA-256 | Block all jurisdiction/rule claims |
| 2 | Jurisdiction and coverage | Unincorporated Miami-Dade; private beta | `GIS-24-55110` and coverage state | Route to municipality selection or planned state |
| 3 | Zoning | `RU-2` | `Z-03`, ordinance section, hash | Do not infer permitted program |
| 4 | Setbacks/dimensional rules | Front 25 ft, side 7.5 ft, rear 15 ft, max height 35 ft, lot coverage 35% | `D-07`, jurisdiction match, effective date, hash | Mark provisional/abstain if governing |
| 5 | Overlays and constraints | Flood zone X; other overlays none applicable in fixture | `OV-11`, map/source date, hash | Surface as unresolved constraint, never “none” by absence |
| 6 | Capacity / maximum units | `2 units`, governed by lot area in fixture | `IC-02` formula + `Z-03`, `D-07`, parcel input hashes | State **Abstain** if a governing rule is missing/not hash-bound |
| 7 | Survey / plat / construction documents | Boundary survey, 2024-12-04, 2 pages | `S-24-4487`, document version/pages/hash | Ask for current survey/plat or flag superseded/corrupt |
| 8 | Comps | Three sales, 0.91–1.08 adjustment range | `CMP-06`, inclusion/exclusion logic and hash | Exclude unsupported comparables; do not imply appraisal |
| 9 | Underwriting | Conditional purchase ceiling `$418,000` | `UW-09`, explicit dependencies and run hash | Withhold reliance-ready ceiling when required input fails |
| 10 | Provenance / replay | Root hash and claim-to-artifact graph | replay ID, artifact set, extraction/model version | Quarantine claims on mismatch |

## Capacity and purchase-ceiling semantics

The fixture’s deterministic capacity record is transparent:

```text
formula: floor(lot_area_sf / min_lot_area_per_unit_sf)
fixture result: 2 units
fixture governing constraint: lot area
```

The presence of `PARKING-RULE` in `not_hash_bound` state means the display is a conditional scenario, not a reliance-ready development program. The system must say:

> Abstain: parking rule is not hash-bound.

Consequently, `$418,000` is a conditional modeling value. It may appear with its dependencies and sensitivity, but it cannot be labeled a recommendation, “safe offer,” approved budget, or final purchase ceiling until required parking evidence is hash-bound and jurisdiction-matched.

## Survey, plat, and construction-document treatment

- A document row names type, issuer, date/version, page count, extraction state, hash, and linked claims.
- Survey/plat boundaries are evidence inputs, not decorative attachments. A stale, superseded, corrupt, or unsupported document is excluded from the active calculation.
- Construction documents are displayed as versioned evidence and may be `uploaded`, `scanning`, `extracted`, or `verified`; extraction alone never verifies an extracted datum.
- A user can compare versions and see why a source stopped governing. The product does not silently replace a source or preserve a derived answer after its source hash changes.

## Grounded LLM contract

The opportunity brief is downstream of validated evidence. It is structured, short, citation-adjacent, and must never stream speculative text into the decision rail.

| Field | Required behavior |
|---|---|
| Status | `supported`, `partially grounded`, `abstained`, or `error` written in text |
| Claims | One to three concise claims; each has direct citation IDs and replay linkage |
| Inputs | The prompt receives only the current artifact IDs, extracted claims, provenance state, and redacted deal context |
| Unsupported facts | Omit them; do not fill gaps from a model prior, web result, or stale memory |
| Abstention | Name the exact insufficiency, its consequence, and the accepted next artifact |
| Citation action | Each citation focuses the relevant ledger row and exposes its source/hash |

### Fixture output: partially grounded

```text
AI-generated · partially grounded
Claim: Two-unit infill case is supportable. [Z-03] [IC-02]
Basis: fixture zoning excerpt and deterministic lot-area capacity calculation.
Limitation: Parking rule is not hash-bound. Do not rely on the capacity or purchase ceiling as a final entitlement or offer recommendation.
Next evidence: Current jurisdiction-matched parking rule with issuer, effective date, section, and SHA-256.
```

### Fixture output: abstained

```text
AI-generated · abstained
I cannot determine a reliance-ready maximum-unit program or purchase ceiling because the parking rule is not hash-bound.
Request the current jurisdiction-matched parking rule; then replay capacity and underwriting against the updated evidence set.
```

## Evidence and replay schema

Every material item exposes: `artifact_id`, `kind`, `issuer/origin`, `acquired_at`, `effective_date`, `jurisdiction`, `extraction_version` where applicable, full SHA-256, and linked claim IDs. Every derived calculation additionally exposes formula, normalized inputs, result/unit, governing marker, calculator version, and deterministic run ID.

Replay is read-only and deterministic for an immutable input set:

1. Load the referenced artifact IDs and verify their stored SHA-256 values.
2. Reject the replay if an artifact is missing, superseded without explicit selection, jurisdiction-mismatched, or hash-mismatched.
3. Re-run deterministic calculations with the recorded formula/version.
4. Regenerate an LLM brief only from the replay’s validated claims; preserve the earlier brief as a timestamped audit event.
5. Display input/output hashes, run ID, and any change in claim state.

This retains a developer or reviewer’s ability to answer “what evidence produced this number?” without exposing customer addresses or creating false legal certainty.
