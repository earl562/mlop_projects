# PlotLot Direction C — Preconstruction Deal Room / Stage-Gate Binder

Status: design contract complete; product implementation intentionally out of scope.

## Direction signature

**A deal becomes reviewable only by passing accountable, evidence-replayable gates.** Direction C is a stage-gate binder where the dominant activity is a handoff: Acquisitions establishes the deal thesis, Preconstruction verifies site and zoning inputs, the Analyst produces a cited capacity and basis case, and the Review Lead accepts, returns, or blocks the next gate.

The canonical handoff route is **Acquisitions → Preconstruction → Analyst → Review Lead**; each transition has immutable inputs, an expected output, an owner, and an internal gate decision.

This is deliberately not Direction A’s continuous evidence workbench, a map atlas, a parcel exploration surface, an operational command center, a chat-first assistant, or a folder-browser deal room. The gate itself—not a dashboard metric—is the home object.

## Primary user and decision

**Primary user:** an acquisition manager moving a land deal into preconstruction review.

**Decision:** is this deal sufficiently evidenced to advance from screening to a reviewable purchase ceiling, or must the owner resolve a named missing/conflicting fact first?

**Readers and accountable roles:**

| Role | Owns | May approve | Cannot silently do |
|---|---|---|---|
| Acquisitions | deal thesis, target basis, comparable intake | Gate 01 | infer legal site capacity |
| Preconstruction | parcel, jurisdiction, zoning, survey/plat, constraints | Gates 02–03 readiness | overwrite source provenance |
| Analyst | deterministic capacity, comps selection, underwriting | Gate 04 package | assert an unsupported rule |
| Review Lead | decision quality and exception acceptance | Gate 05 | waive an unresolved blocker without a recorded exception |

## Interface signature

```ts
type Gate = "intake" | "jurisdiction" | "capacity_site" | "basis" | "review";
type GateStatus = "not_started" | "in_progress" | "waiting_evidence" | "ready_for_review" | "approved" | "returned" | "blocked" | "not_enabled";

interface DealBinder {
  open(dealId: string): DealSnapshot;
  advance(input: GateSubmission): GateTransition;
  replay(ref: EvidenceRef): EvidenceReplay;
  requestReview(gate: Gate, packageId: string): Handoff;
}
```

**Usage:** Acquisitions opens a deal, attaches a redacted parcel/folio and target basis, then requests the jurisdiction gate. Preconstruction either supplies cited zoning, setbacks, constraints, and a versioned survey/plat—or returns a single named evidence request. The Analyst can calculate a maximum-unit case and purchase ceiling only after required inputs are hash-bound. The Review Lead sees the same immutable replay package, approval history, outstanding blocker, and the bounded request; they approve, return with a reason, or approve an explicitly recorded exception.

## Route map

| Route | Job | Primary object | Allowed exit |
|---|---|---|---|
| `/deals` | Find retained deals by stage, owner, or coverage status | deal row | open binder |
| `/deals/:dealId/binder` | Read current gate, make/receive handoff, replay evidence | binder | gate detail or evidence replay |
| `/deals/:dealId/gates/:gateId` | Complete one bounded gate | gate dossier | request review, return, or evidence task |
| `/deals/:dealId/evidence/:ref` | Inspect immutable source/derived/LLM evidence | replay sheet | return to invoking gate |
| `/deals/:dealId/approvals/:approvalId` | Inspect signed decision and exceptions | approval record | return to review gate |

No route is a countywide coverage browser or an autonomous analysis chat.

## Content-block jobs

| Block | Job |
|---|---|
| Binder spine | Orient the role, stage, blocker, and owner without turning stages into a vanity funnel |
| Deal identity | Prove the subject parcel/folio/APN and jurisdiction before a rule claim |
| Coverage gate | State exactly whether the requested municipality is eligible for analysis |
| Gate dossier | Put the current gate’s required evidence, result, owner, and exit criterion in one place |
| Capacity worksheet | Show input → formula → constraint → maximum units, including governing constraint |
| Constraints sheet | Keep flood, access, easement, overlay, utility, historic, and dimensional blockers visible |
| Survey / plat packet | Establish document version, extraction status, pages, hash, and linked assertions |
| Comps / basis | Show comparable inclusion/exclusion and a reviewable purchase-ceiling assumption set |
| Grounded analysis | Offer compact, cited, abstaining synthesis downstream of evidence—not chat |
| Handoff rail | Make who has the work, what they received, expected output, due state, and approver visible |
| Evidence replay | Reconstruct a fact or derived conclusion from stable artifact IDs and hashes |
| Approval record | Bind decision, reviewer, gate version, exception, and timestamp without pretending it is legal approval |

## Principal tradeoffs

1. **Gate clarity over cross-deal density.** A manager sees fewer simultaneous metrics than in a command center, but every active deal has a decisive next action and accountable owner.
2. **Bounded handoffs over a free-form collaboration feed.** The binder is less conversational, but review inputs and output expectations are inspectable and replayable.
3. **Evidence versioning over a familiar folder metaphor.** Documents are not simply browsed; each is presented as an evidence object with issuer, effective date, hash, extraction version, and linked claim.
4. **Abstention over continuity theater.** The purchase ceiling and review action become unavailable when a governing rule or coverage status is missing, conflicting, stale, or not enabled.
5. **Role-specific views over a universal dashboard.** The route preserves one common binder while foregrounding the current role’s deliverable.

## Artifacts

| Artifact | Purpose |
|---|---|
| `DESIGN.md` | Design system, components, motion, accessible interaction contract |
| `ROUTES_FLOW_PANEL_HIERARCHY.md` | Routes, happy/blocked task flow, panel hierarchy, focus and scroll ownership |
| `STATE_MATRIX.md` | Semantic states and correct-or-abstain behavior |
| `RESPONSIVE_WIREFRAMES.md` | 1440×900 / 768×1024 / 390×844 contracts and overflow behavior |
| `CONTENT_FIXTURES_AND_GROUNDING.md` | Redacted fixtures, coverage truth, capacity, constraints, evidence/replay, handoffs, LLM rules |
| `SELF_AUDIT.md` | Accessibility, focus, reduced-motion, overflow, and scope self-audit |
| `reference-direction-c-v1.png` | Single generated visual reference |
| `imagegen.metadata.json` | Prompt binding, output facts, validation notes |
| `checksums.sha256` | Package integrity hashes |
| `DONE_CLAIM.json` | Bounded completion claim |

## Non-goals

- Countywide coverage claims for Miami-Dade, Broward, or San Diego
- Legal advice, entitlement guarantees, or automatic approval
- Private street addresses or identifiable customer details in fixtures
- Map-first analysis, satellite imagery, beach/luxury real-estate aesthetics
- Generic AI conversation, generic SaaS dashboard, or screen-within-device imagery

## Reference-image authority

The generated image establishes binder geometry, material, hierarchy, and role-to-handoff emphasis. It does not establish product facts. Written specifications override any generated raster typo or fictional content.
