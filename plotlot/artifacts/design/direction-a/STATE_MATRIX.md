# Semantic state matrix

Labels and explanatory text accompany every state. Green means provenance checks passed for a displayed artifact; it never means an entitlement, legal opinion, or construction approval.

| Domain | State | User-visible treatment | Permitted action / derived behavior |
|---|---|---|---|
| Coverage | `enabled_private_beta` | “Miami-Dade private beta” with parcel-level evidence availability | Allow evidence-backed analysis; mark beta freshness and policy caveat |
| Coverage | `municipality_required` | “Broward — municipality required” or “Palm Beach — municipality required” | Capture parcel/jurisdiction; disable analysis until a supported municipality is selected |
| Coverage | `planned_not_enabled` | “San Diego County — planned, not enabled” | Permit waitlist/context capture only; no zoning, capacity, or underwriting result |
| Coverage | `unknown_jurisdiction` | Neutral unresolved coverage gate with requested jurisdiction | Do not infer countywide support; route to jurisdiction resolution |
| Parcel identity | `verified` | Folio/APN, jurisdiction, source ID, acquired time, hash | Downstream lookup may continue |
| Parcel identity | `ambiguous` | Competing records and exact mismatch | Block zoning/capacity; request authoritative parcel match |
| Parcel identity | `missing` | “Parcel/folio or APN not resolved” | Offer lookup/retry; no derived claim |
| Evidence artifact | `resolving` | Text progress and source target | Keep prior verified value visibly distinct; do not substitute a spinner for status |
| Evidence artifact | `verified` | Status icon + “Verified” + source/citation/hash | Eligible input when fresh and jurisdiction-compatible |
| Evidence artifact | `partial` | “Partial — [missing field]” | A calculation may show only if missing field is non-governing; otherwise abstain |
| Evidence artifact | `missing` | Exact requested artifact and acceptable issuer/form | Create blocker/handoff; no inferred value |
| Evidence artifact | `stale` | Date/policy reason and last known value | Prevent reliance when policy says stale; request refresh |
| Evidence artifact | `conflict` | Both values, sources, and conflict reason | Block affected conclusion; do not average or choose silently |
| Evidence artifact | `hash_mismatch` | Brick error, expected and observed hash labels | Quarantine linked claims and replay; create evidence-integrity blocker |
| Zoning / dimensional rule | `cited_current` | Rule value beside ordinance section and source hash | Eligible capacity input |
| Zoning / dimensional rule | `cited_but_ambiguous` | Exact ambiguity and review owner | Show provisional context but do not call it a buildable rule |
| Zoning / dimensional rule | `not_hash_bound` | “Abstain: [rule] is not hash-bound” | Withhold dependent capacity/ceiling claim and request source artifact |
| Constraint ladder | `verified_calculation` | Formula, inputs, unit cap, and explicit governing marker | May state maximum units as illustrative/supportable, with citations |
| Constraint ladder | `provisional_calculation` | Inputs and missing/conditional marker | Show only a provisional scenario; decision rail remains conditional |
| Constraint ladder | `abstained` | “Maximum units unavailable” and exact missing input | No numeric unit claim; route blocker |
| Documents | `uploaded` / `scanning` / `extracted` | Document type, date, pages, issuer, extraction state | Extraction is not verification |
| Documents | `verified` | Hash-bound document and linked claims | May support cited rows |
| Documents | `superseded` / `corrupt` / `unsupported_format` / `missing` | Version/error/correct replacement request | Exclude from current derived result |
| Comps | `included` | Inclusion basis, date/range, adjustment summary | Supports underwriting only, never zoning capacity |
| Comps | `excluded` | Reason for exclusion | Retained in audit trail; not used in ceiling |
| Underwriting | `ready` | Inputs, formula, sensitivity, evidence completeness | Show purchase ceiling only if all governing inputs are verified |
| Underwriting | `conditional` | Ceiling labeled conditional plus dependency | May present scenario value; no “ready to buy” language |
| Underwriting | `abstained` | “Purchase ceiling unavailable” | Withhold price recommendation; point to missing capacity/parking/comps evidence |
| Grounded LLM brief | `grounded` | “AI-generated · supported” and adjacent citations | May summarize only hash-bound source claims |
| Grounded LLM brief | `partially_grounded` | Supported claim(s) and named limitation | Unsupported portion is omitted, not completed by model intuition |
| Grounded LLM brief | `abstained` | Exact insufficiency, e.g. parking rule not hash-bound | Says what it cannot conclude and the next evidence request |
| Agent handoff | `draft` / `queued` / `running` | Owner, immutable inputs, expected output, last event | No claim of completion |
| Agent handoff | `waiting_for_evidence` / `requires_review` | Blocker and named reviewer | Decision stays gated |
| Agent handoff | `complete` / `failed` / `cancelled` | Audited terminal event | Completion does not alter an evidence state without new artifact validation |

## Decision-rail truth table

| Required condition | Rail result |
|---|---|
| Enabled coverage + verified parcel + cited rules + verified governing inputs + current evidence | Maximum units and purchase ceiling may be shown as an evidence-backed scenario; legal/advisory caveat remains |
| Any required rule or document is partial, stale, conflicting, or conditional | Label relevant figure **Conditional**; show dependency and blocker |
| Parking, lot area, jurisdiction, or another governing input is missing/not hash-bound | **Abstain** from maximum-unit or purchase-ceiling conclusion affected by that input |
| Municipality-required or planned/not-enabled coverage | Disable analysis and underwriting; never render stale values as current results |
| Replay hash mismatch | Quarantine every linked claim pending evidence revalidation |
