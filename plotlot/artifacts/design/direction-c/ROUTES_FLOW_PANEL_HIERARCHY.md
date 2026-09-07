# Routes, Flow, and Panel Hierarchy

## Gate model

| Gate | Owner | Entrance criterion | Exit criterion |
|---|---|---|---|
| 01 Intake thesis | Acquisitions | deal is retained | redacted parcel/folio/APN, target basis, and intended program identified |
| 02 Jurisdiction & rules | Preconstruction | subject identity exists | eligible coverage + cited zoning/dimensional evidence, or named coverage/evidence blocker |
| 03 Capacity & site | Preconstruction → Analyst | rules packet is current | survey/plat/constraints checked; deterministic capacity completes or abstains |
| 04 Basis & ceiling | Analyst | supported/provisional capacity state known | comps, assumptions, and purchase ceiling are replayable—or unavailable |
| 05 Review decision | Review Lead | package is ready or exception is recorded | approve, return, block, or exception-accept with signature |

## Task flow: ordinary supported case

1. Acquisitions creates Intake with `folio`, jurisdiction candidate, target program, and target land basis.
2. The coverage gate resolves Miami-Dade to **private beta** at the supported municipality scope. It does not mark a whole county as live.
3. Preconstruction attaches/links zoning and setbacks evidence, then requests survey/plat review and constraints extraction.
4. The Capacity worksheet traces lot-area, setbacks/buildable envelope, parking, height, and overlay constraints. It marks the governing constraint and computes `max_units` only from current hash-bound inputs.
5. Analyst selects/excludes comps, reveals adjustment assumptions, and computes a purchase ceiling. The ceiling references the capacity revision it depends on.
6. The grounded brief emits cited claims with `[source]` links and limitations. It abstains from any claim lacking bound evidence.
7. Analyst sends Gate 04 to Review Lead with immutable inputs, desired decision, and expected outcome.
8. Review Lead replays evidence, then signs `approved`, `returned`, `blocked`, or `exception_accepted`; the binder keeps the complete decision history.

## Task flow: missing parking rule / not-enabled coverage

1. If the parking rule is unresolved, Capacity shows `MAX UNITS — ABSTAINED`; a visually plausible fallback number is forbidden.
2. `Request review` remains disabled, with an accessible explanation naming `Parking rule: source missing or not hash-bound` and the required evidence.
3. A `Resolve parking rule` handoff routes to Preconstruction with source requirements and a specific output contract.
4. If jurisdiction is Broward but municipality support is unknown, state `BROWARD — MUNICIPALITY-CONDITIONAL`; no analysis is offered until an enabled municipality is resolved.
5. If jurisdiction is San Diego, state `SAN DIEGO — PLANNED, NOT ENABLED`; capture may remain available, but gate analysis and review are disabled. This is not a failure state and must never imply planned coverage is live.

## Panel hierarchy and scroll ownership

```text
BinderShell (bounded 100dvb; desktop/tablet document does not scroll)
├── UtilityHeader (fixed, 56px)
│   ├── Deal switcher
│   ├── Coverage status
│   └── Replay / notifications / profile controls
└── BinderBody
    ├── BinderSpine (248px; own vertical scroll)
    │   └── GateTab ×5
    ├── GateDossier (flex; primary vertical scroll)
    │   ├── DecisionSentence + exit criterion
    │   ├── DealIdentity + coverage gate
    │   ├── RequiredEvidencePackets
    │   ├── CapacityWorksheet / ConstraintsSheet
    │   ├── SurveyPlatPacket
    │   ├── CompsBasisPacket
    │   └── GroundedBrief + replay links
    └── HandoffRail (328px; own vertical scroll only when overflowed)
        ├── CurrentOwner + SLA
        ├── HandoffCard
        ├── ApprovalLine
        ├── Blocker
        └── EvidenceReplay index
```

The three desktop/tablet scroll regions have distinct retained jobs. No nested scroll exists inside a packet. On mobile only the document column scrolls; the decision dock is fixed and non-scrollable.

## Focus order and escape behavior

1. Header controls in visual order.
2. Selected-deal identity and coverage explanation.
3. Gate tabs, top to bottom; current gate uses `aria-current="step"`.
4. Dossier heading, decision, blocker, evidence packet actions, formula, brief citations.
5. Handoff rail task, approval actions, replay index.
6. Mobile decision dock action is last in DOM, not first solely because it is visually fixed.

Replay sheets trap focus while open, close on Escape, provide a visible Close control, and restore focus to the invoking evidence link. Return/approve dialogs require confirmation and return focus to their initiating button. No automatic focus jumps occur for background status updates.

## State-dependent actions

| Current state | Primary action | Disabled / replacement behavior |
|---|---|---|
| required evidence current + gate ready | Request review | none |
| source missing / stale / conflict | Resolve named blocker | Request review disabled with `aria-describedby` reason |
| calculation provisional | Request evidence | purchase ceiling visibly provisional/unavailable by policy |
| municipality conditional | Resolve municipality | analysis controls unavailable until enabled locality established |
| planned/not enabled | Join enablement list / save intake | all analysis/review actions disabled; no implied ETA |
| review returned | Address review note | prior approval not presented as current |
