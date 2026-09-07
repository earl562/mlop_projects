# Acquisition Decision Contract

## Product decision

The first-release buyer is a South Florida general-contractor/developer acquisition or preconstruction lead. Private investors and land developers use the same contract. The contract answers one question: pursue or control this Opportunity at what Verified Ceiling?

Required inputs are the Primary Buyer persona, property identity, Municipality Lane, Development Program, verified Local Truth, verified constraints and capacity, verified market evidence, verified underwriting, municipality support receipts, and a distinct Reviewer. Required outputs are the Decision Recommendation, Verified Ceiling when permitted, five readiness dimensions, blocker codes, and Evidence Receipts.

The machine contract is `PlotLotAcquisitionDecisionContractV1`. Its canonical Python/TypeScript projection hash is:

`ab82ad9aaebc10b32535ae89556f772827b00b72ef90a55cec2553b0ddab033f`

## Independent dimensions

| Dimension | States |
| --- | --- |
| Processing Status | `not-started`, `running`, `complete`, `blocked` |
| Decision Readiness | `blocked`, `provisional`, `ready` |
| Pricing Readiness | `unpriced`, `provisional`, `evidence-supported` |
| Review Status | `unreviewed`, `review-required`, `approved` |
| Release Status | `blocked`, `eligible`, `released` |

The aggregate Decision Status is `blocked`, `provisional`, or `released`. It cannot widen beyond any component dimension. A Verified Ceiling is omitted whenever evidence is ambiguous, stale, conflicting, outside coverage, or too thin. An analyst cannot approve their own release.

## Coverage ledger

The initial Municipality Lanes are:

- Miami, Miami Gardens, and Unincorporated Miami-Dade
- Fort Lauderdale, Miramar, and Hollywood
- West Palm Beach, Boca Raton, and Unincorporated Palm Beach/Loxahatchee

Each lane has ten explicit Support Coordinates:

| Workflow | Fact Families |
| --- | --- |
| `opportunity-intake` | `property-identity`, `jurisdiction` |
| `constraints-and-capacity` | `zoning`, `development-constraints`, `legal-capacity` |
| `market-underwriting` | `land-comps`, `finished-resale-comps`, `underwriting` |
| `decision-release` | `pricing-readiness`, `reviewer-approval` |

The generated ledger therefore lists 90 distinct coordinates. Every coordinate defaults to `unsupported` with no Evidence Receipts. Promotion accepts exactly one enabled county, Municipality Lane, Workflow, and Fact Family plus one or more issued receipts. The county must own the lane. Receipt IDs and coordinates are unique; an identical retry is idempotent, while duplicate or conflicting promotions fail closed. County enablement booleans supplied by callers are forbidden.

An `IssuedSupportRegistryV1` is a trusted runtime dependency and is never accepted inside an Opportunity request. Each immutable issuance binds its ID to the exact county, lane, workflow, and fact family, plus a source ID, evidence SHA-256, known issuer and key version, issuance time, expiry, and optional revocation time. Pydantic is used only for the untrusted boundary document; validation then constructs a separate opaque, slot-sealed trust object with no model-copy, update, dump, or mutable collection API. Evaluation type-requires that verified object and blocks document or request-body substitution. Evaluation receives the registry and authoritative evaluation time from the host. It blocks unissued, forged, rebound, revoked, expired, or not-yet-issued receipts. Unknown registry, issuer, or key versions fail schema validation. The deterministic public-test authority contains no secret and exists only for cross-runtime contract tests and CLI demonstrations; production must load its registry from an access-controlled system of record.

## Private beta and external actions

Miami-Dade may be labeled `Miami-Dade private beta` only after its required Municipality Lanes independently pass release gates. Broward and Palm Beach remain visibly disabled until their own coordinates pass; neither inherits Miami-Dade status, and no South Florida coverage claim is permitted before all three counties pass.

Decision input never accepts a self-reported support status. Support is derived from the complete coordinate receipt set. Aggregate status, recommendation, ceiling, and release must exactly match their processing, readiness, pricing, review, evidence, and blocker dimensions; an incoherent projection is rejected at the boundary.

Seller contact, lender delivery, offer submission, contract language, and fund movement are disabled. The only automatic outbound action is a tenant-configured signed status/result webhook for an already released decision.
