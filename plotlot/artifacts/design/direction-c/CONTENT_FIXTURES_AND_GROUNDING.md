# Redacted Fixtures, Evidence, Grounding, and Handoffs

## Fixture privacy and legal limits

All values below are deterministic, fictional, and stable-redacted. They are interface fixtures only; they do not identify an owner, customer, or exact street address, and are not zoning, appraisal, underwriting, engineering, legal, or entitlement advice.

```yaml
deal:
  deal_id: deal_mia_beta_0142
  label: Northwest infill — review binder
  folio: "30-3115-•••-0420"
  apn: null
  locality: "Example supported locality, Miami-Dade"
  coverage: private_beta_enabled
  coverage_copy: "MIAMI-DADE PRIVATE BETA — locality scope verified before analysis"
  parcel_area_sqft: 12500
  zoning_code: RU-2
  target_program: "two-unit infill"
  target_land_basis_usd: 390000
```

## Coverage truth

| Market request | Product state | Correct UI copy | What is allowed |
|---|---|---|---|
| Miami-Dade supported locality | private beta | `MIAMI-DADE PRIVATE BETA` plus resolved locality | gated analysis only after locality/coverage checks |
| Broward request | municipality conditional | `BROWARD — MUNICIPALITY-CONDITIONAL` | capture intake and resolve an enabled municipality; no countywide result |
| Palm Beach request | municipality conditional | `PALM BEACH — MUNICIPALITY-CONDITIONAL` | same municipality-first behavior |
| San Diego request | planned, not enabled | `SAN DIEGO — PLANNED, NOT ENABLED` | save intake / enablement interest only; no analysis or approval |

Neither a county name nor a planned pipeline establishes coverage. A failure to resolve coverage is an explicit state, not a quiet fallback to generic data.

## Subject / source fixture

| Evidence ID | Kind | Effective / acquired | Hash stub | Linked fact | State |
|---|---|---|---|---|---|
| `P-01` | parcel identity record | 2026-07-01 / 2026-07-02 | `sha256:2a19…8e61` | folio and 12,500 sqft lot | verified |
| `Z-03` | zoning code excerpt | 2026-06-15 / 2026-07-02 | `sha256:7f4a…c91e` | RU-2 designation | verified |
| `D-04` | dimensional standards excerpt | 2026-06-15 / 2026-07-02 | `sha256:541b…a095` | setbacks 20' / 7.5' / 15' | verified |
| `S-02` | signed survey / plat packet | 2026-05-19 / 2026-07-03 | `sha256:391c…c52a` | boundary, easement note, datum | verified |
| `C-06` | constraints screen | 2026-07-03 / 2026-07-03 | `sha256:ee88…b0d4` | access/easement investigation | partial |
| `PK-01` | parking standard | unknown / none | none | off-street parking ratio | missing |
| `CMP-07` | comparable set | 2026-06-30 / 2026-07-03 | `sha256:bb04…37d1` | price-adjustment inputs | verified |

## Capacity and constraints worksheet

The fixture presents a deterministic calculation contract, not a claim that any real parcel may be developed this way.

| Constraint | Input / source | Calculation | Output | State |
|---|---|---|---:|---|
| Lot-area theoretical cap | 12,500 sqft, `P-01`; illustrative 6,250 sqft/unit, `Z-03` | floor(12,500 / 6,250) | 2 units | verified |
| Setback/buildable envelope | 20' / 7.5' / 15', `D-04`; boundary `S-02` | engineering/site layout required | not independently unit-limiting in fixture | partial |
| Easement/access | `S-02`, `C-06` | verify no buildable-area/drive impact | unresolved | partial |
| Parking | `PK-01` missing | no source-bound ratio | **ABSTAIN** | missing |
| Overlay/environmental | `C-06` partial | screen complete only for listed scope | not clear | partial |

For a **scenario view only**, the lot-area cap is 2 units and the governing available constraint is lot area. The production decision is nevertheless `MAX UNITS — ABSTAINED` until parking and site constraints are evidence-bound. A governing constraint may change after survey/plat, parking, access, or overlay evidence updates; replay must preserve the revision.

## Survey, plat, and document handling

`S-02` displays: document type, issuer, signed date, pages, datum, uploader/origin, SHA-256, extraction version, page-level references, extraction confidence, and supersession chain. It does not rely on filename alone. A survey or plat is linked to only the claims/page regions it supports; unlinked OCR text cannot enter a capacity formula.

Document states: uploaded → scanning → extracted → verified or rejected; verified → superseded retains historical replay; corrupt/unsupported requests a replacement. Uploading does not mean truth, and an extraction confidence score does not replace human/signed-source verification.

## Comps and purchase ceiling

| Basis input | Value | Evidence / disclosure |
|---|---:|---|
| Illustrated supported capacity | unavailable for decision; 2-unit scenario only | capacity worksheet revision `cap-r03` |
| Included comparable adjusted land signal | $465,000 | `CMP-07`, inclusion reason and adjustment notes |
| Risk / carry / entitlement reserve | $47,000 | underwriting assumption `UW-02`, analyst-owned |
| Illustrative purchase ceiling | $418,000 | `$465,000 − $47,000`; conditional on resolved capacity |

The UI labels this fixture `Purchase ceiling — unavailable for review` until parking is bound. If a scenario is shown, label it `Scenario only — not reviewable` and attach its assumptions. There is no blank money tile, zero, or implied recommendation.

## Evidence replay contract

```ts
interface EvidenceReplay {
  replayId: string;
  assertion: string;
  lineage: Array<{
    sequence: number;
    kind: "source" | "extraction" | "calculation" | "llm_claim" | "handoff" | "approval";
    ref: string;
    createdAt: string;
    sha256?: string;
    supersedes?: string;
  }>;
  integrity: "hash_bound" | "hash_mismatch" | "unavailable";
}
```

Example lineage for a future supported max-unit claim: `P-01 → Z-03 → D-04 → S-02 → PK-01 → cap-r04 → LLM-02 → H-19 → A-11`. Every calculation captures input refs/version IDs and its formula. Replay says what changed between revisions; a hash mismatch invalidates dependent supported claims until reconciled.

## Grounded LLM contract and abstention

The LLM is an analysis renderer, not a source of property facts or a reviewer. It receives selected, current evidence snippets/structured inputs and may produce only:

```ts
interface GroundedClaim {
  text: string;
  status: "supported" | "provisional" | "abstained";
  citations: string[];
  assumptions: string[];
  limitations: string[];
  requestedEvidence?: Array<{ fact: string; acceptableSource: string; owner: string }>;
}
```

Allowed fixture output:

- `supported` only when exact cited evidence supports the narrow statement: `RU-2 is recorded in the current zoning excerpt [Z-03].`
- `provisional`: `The 2-unit lot-area scenario depends on the stated illustrative lot-area ratio and remains subject to site, parking, and other rules [P-01] [Z-03] [D-04] [S-02].`
- `abstained`: `I cannot state a supportable maximum-unit result or reviewable purchase ceiling because the parking rule is not hash-bound. Request the current parking standard from Preconstruction [PK-01 missing].`

The UI forbids citations that are invented, inaccessible, stale beyond policy, hash-mismatched, or unrelated to the statement. It never says “approved,” “permitted,” or “safe to build” unless those terms appear in an appropriate human/government decision record and are scoped precisely.

## Approval and handoff fixtures

```yaml
handoff:
  handoff_id: H-19
  from: Preconstruction
  to: Analyst
  gate: capacity_site
  status: waiting_evidence
  task: "Bind current parking standard and recompute capacity revision."
  immutable_inputs: [P-01, Z-03, D-04, S-02, C-06]
  expected_output: "PK-01 source record plus capacity revision with governing constraint."
  acceptance: "Rule has effective date, source hash, municipality scope, and linked calculation."
  owner_due_state: "Owner: Preconstruction · no artificial deadline fixture"
approval:
  approval_id: A-11
  gate: basis
  status: returned
  reviewer: Review Lead
  revision: basis-r02
  note: "Return: purchase ceiling depends on capacity that remains abstained."
```

Handoffs version inputs rather than silently mutating them. Approval is an internal stage decision with an approver, revision, timestamp, comment, and optional exception record. It is never represented as a municipal approval, legal opinion, or investment committee certainty.
