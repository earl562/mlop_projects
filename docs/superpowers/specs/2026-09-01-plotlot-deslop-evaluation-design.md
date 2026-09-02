# PlotLot De-Slop, Lead Intelligence, and Evaluation Architecture

**Date:** 2026-09-01  
**Revision:** Integrated dual-plane architecture approved; reliable comps moved before underwriting  
**Base:** `cpt-pro@a3531aed37b6d7186addc1ef3b8ee00ec5199778`  
**Work branch:** `feat/cpt-pro-deslop`

## Approved Decisions

PlotLot will use **Option 1: one integrated product with two controlled data planes**.

1. **Property Intelligence Plane** — property identity, zoning, site constraints, reliable comparable sales, underwriting, evidence, and decision support.
2. **Restricted Contact and Outreach Plane** — owners, trusts, entities, registered agents, sellers, brokers, contact observations, verified contact points, suppression records, outreach, responses, and follow-ups.

Both planes share one authenticated product, application-service layer, PostgreSQL deployment, evidence model, audit trail, and human-review workflow. Sensitive contact data is not flattened into unrestricted property records and is never copied into Git, public fixtures, ordinary logs, analytics events, exception messages, or model traces.

The second approved decision is a hard dependency:

> **Reliable comparable-sale qualification is completed before market-derived underwriting.**

Underwriting may not retrieve or select its own comps, accept an unqualified market value, or produce an acquisition recommendation before a `CompQualificationResult` exists. When comparable evidence is insufficient, stale, or conflicting, PlotLot must abstain or produce an explicitly incomplete hypothetical scenario. It may not substitute an LLM estimate.

## Objective

Create one understandable and reproducible property-to-outreach system that can:

- resolve the correct property and parcel
- retrieve source-backed zoning and site evidence
- qualify reliable comparable transactions
- perform deterministic underwriting only after comps qualify
- resolve owners, entities, sellers, agents, and contact points with provenance
- independently verify every decision-critical claim
- present one review packet to a human
- execute policy-governed outreach only after approval
- track responses and follow-ups into a warm-lead pipeline
- replay a historical result and refresh it against current sources

The cleanup must not hide existing failures, invent coverage, weaken approvals, expose sensitive contact data, or make an LLM responsible for deterministic zoning, comp selection, valuation, underwriting, suppression, or channel eligibility.

## Program Deliverables

1. Establish and record the operational and test baseline.
2. Work in an isolated branch based on `cpt-pro`.
3. Add characterization and architecture tests before moving behavior.
4. Remove tracked AI workspace state, stale personal instructions, and disconnected scaffolding.
5. Introduce one canonical analysis application service for JSON, SSE, chat, MCP, CLI, and agent tools.
6. Introduce one governed tool-execution transaction for all transports.
7. Add deterministic comparable-sale qualification as a prerequisite to underwriting.
8. Refactor underwriting to consume qualified comps and explicit, versioned assumptions.
9. Add restricted party, property-party relationship, contact, suppression, and outreach models.
10. Add a read-only independent Verification Agent and unified human-review packet.
11. Maintain separate repository-safe and restricted evaluation corpora.
12. Integrate approved outreach, response classification, and follow-up tracking without creating a second product architecture.

## Current Baseline

### Known green lanes on `cpt-pro`

- repository hygiene
- Ruff lint and formatting
- mypy
- backend unit tests with PostgreSQL
- frontend lint, build, and UI tests
- Playwright no-DB

### Known failing lanes

- DB-backed Playwright: the lookup report scenario receives an unexpected HTTP 503 after migrations and backend health succeed.
- Nightly provider health on `main`: Hub discovery rejects Miami-Dade, Broward, and Palm Beach candidates; Broward legacy lookup also times out.
- Deployed API health on `main`: the Render health endpoint does not return within the current 15-second single-attempt probe.

These are baseline defects. Cleanup may fix them but may not relabel, skip, or suppress them.

## Architectural Decision

Use an incremental strangler migration, not a rewrite and not a new outreach microservice.

```text
HTTP JSON / SSE / Chat / MCP / CLI / Multi-agent coordinator
                            |
                            v
                    Application services
   AnalysisService / ContactIntelligenceService / VerificationService
      ReviewPacketService / OutreachService / ToolExecutor
                            |
                            v
            Domain rules and deterministic capabilities
 Property identity -> zoning -> reliable comps -> underwriting -> decision
 Party resolution -> contact verification -> suppression -> outreach state
                            |
                            v
             Provider ports / repositories / integrations
                            |
                            v
      PostgreSQL: property schemas + restricted contact schemas
```

Transport modules may authenticate, validate transport envelopes, and render results. They may not independently orchestrate geocoding, property lookup, ordinance retrieval, comp selection, underwriting, contact eligibility, approvals, evidence persistence, outreach, or report generation.

## Canonical End-to-End Sequence

```text
1. Property intake
        |
        v
2. Property and parcel identity resolution
        |
        +------------------------------+
        |                              |
        v                              v
3. Zoning and site evidence       Contact and party enrichment
        |
        v
4. Reliable comparable-sale qualification
        |
        v
5. Deterministic underwriting
        |
        +------------------------------+
        |                              |
        v                              v
6. Acquisition decision packet    Contact verification and channel eligibility
        |                              |
        +---------------+--------------+
                        v
7. Independent verification
                        |
                        v
8. Unified human-review packet
                        |
                        v
9. Human approval
                        |
                        v
10. Outreach execution
                        |
                        v
11. Response classification and governed follow-up
                        |
                        v
12. Qualified or warm-lead pipeline
```

Contact enrichment may start after property identity resolves and may run concurrently with zoning and comp retrieval. This parallelism does not alter the financial dependency: **comps finish before underwriting**, and property analysis plus contact eligibility pass independent verification before the case becomes approval-ready.

## Canonical Analysis Service

Introduce a transport-neutral application service.

```python
class AnalysisService:
    async def analyze(
        self,
        request: AnalysisRequest,
        *,
        emit: AnalysisEventSink | None = None,
    ) -> AnalysisResult: ...
```

Requirements:

- One execution path for synchronous JSON and streamed SSE analysis.
- Structured events are emitted by the service; SSE only serializes them.
- Existing provider, ordinance, comp, calculation, and pro-forma components are reused behind explicit interfaces.
- No API route imports underscore-prefixed pipeline functions.
- Partial coverage and timeouts become typed outcomes.
- `lookup_address()` remains a compatibility adapter until callers migrate.
- The service records a claim ledger and evidence references rather than only narrative prose.
- The execution order is enforced in code and tests: identity, zoning/site evidence, qualified comps, underwriting, decision packet.

## Canonical Tool Executor

`HarnessRuntime` remains the low-level policy and handler runtime. One application-level `ToolExecutor` transaction owns:

1. canonical contract lookup and argument validation
2. workspace, project, site, property, party, and outreach-case context resolution
3. durable approval validation
4. role and purpose authorization
5. governed runtime execution
6. tool-run persistence
7. evidence validation and persistence
8. artifact, report, and document persistence
9. sensitive-field redaction for logs and traces
10. audit events
11. commit or rollback
12. transport-neutral result mapping

REST tools, chat, HTTP MCP, FastMCP, and multi-agent execution must call this executor instead of duplicating approval, sensitive-data access, persistence, or policy behavior.

## Property Identity Contract

An address string is an input, not the permanent identity of a site.

The property resolver produces:

- stable internal `property_id`
- canonical address
- jurisdiction, municipality, county, and state
- parcel, folio, or APN identifiers
- geographic coordinates
- parcel geometry or authoritative geometry reference
- multi-parcel and unit ambiguity flags
- source observations and retrieval timestamps
- identity confidence

Owner, zoning, comp, underwriting, contact, and outreach records may attach only after identity resolution. Ambiguous or conflicting parcel resolution returns `ambiguous_property` and blocks underwriting and outreach.

## Reliable Comparable Sales — Required Before Underwriting

Comparable qualification is a dedicated deterministic capability, not a prompt instruction or hidden underwriting step.

### Inputs

- resolved subject property and parcel
- property and land-use classification
- lot and building attributes
- jurisdiction and geometry
- candidate transactions with provenance
- configurable buy-box and qualification policy

### Candidate rejection rules

A candidate is rejected when it is:

- the subject property
- duplicated across sources or recordings
- missing source provenance
- not a verified arm's-length or otherwise policy-eligible transaction
- outside the maximum age
- outside the maximum radius
- incompatible by property type, land-use type, or development potential
- materially incompatible by lot size, building size, unit count, condition, or entitlement state
- a statistical price outlier without corroboration
- missing fields required for the selected valuation basis

### Required output

```python
class CompQualificationResult:
    subject_property_id: str
    accepted: tuple[QualifiedComp, ...]
    rejected: tuple[RejectedComp, ...]
    valuation_range: ValueRange | None
    valuation_basis: str | None
    confidence: float
    source_diversity: int
    policy_version: str
    evidence_ids: tuple[str, ...]
    status: CompQualificationStatus
```

`CompQualificationStatus` is one of `qualified`, `insufficient_evidence`, `conflict`, or `stale`.

Every accepted and rejected candidate retains its source, retrieval time, normalized transaction fields, computed distance, similarity measurements, and exact acceptance or rejection reasons.

Valuation is withheld unless the configured minimum number of qualified transactions remains. The initial default is three qualified sales, subject to a versioned property-type policy. Confidence depends on count, freshness, distance, similarity, transaction quality, and source diversity.

The LLM may explain the result. It may not re-admit an excluded transaction, invent a transaction, alter a recorded value, or create a market value when the deterministic capability abstains.

### Hard underwriting gate

`UnderwritingService` requires a `CompQualificationResult` argument and may not query or select comps itself.

- `qualified`: market-derived underwriting may proceed.
- `insufficient_evidence`: market-derived underwriting is blocked.
- `conflict`: market-derived underwriting is blocked pending review or refresh.
- `stale`: market-derived underwriting is blocked until the comps capability refreshes.

A cost-only or user-supplied hypothetical scenario may still run, but it is labeled `incomplete_scenario`, cannot be represented as market-supported, and cannot produce `advance_for_review`.

## Deterministic Underwriting

Underwriting starts only after the comps gate passes.

The service consumes:

- `CompQualificationResult`
- source-backed zoning and site envelope from the analysis stage
- explicit development-program assumptions
- versioned cost, financing, timing, rent, sale, and exit assumptions
- user overrides with author, timestamp, and reason

It produces:

- market-supported revenue assumptions derived from accepted comps or separately identified evidence
- development, financing, and carry costs
- residual land value
- sensitivity ranges
- missing-input and model-risk flags
- exact formulas and formula version
- evidence and assumption lineage

The acquisition decision basis is the lower supported value of:

- the conservative floor or policy-selected bound of the qualified comp range
- the deterministic residual land-value ceiling

Decision outcomes are:

- `advance_for_review`
- `hold_for_inputs`
- `reject_buy_box`
- `insufficient_evidence`

The later Verification Agent independently rechecks the source-backed zoning inputs, accepted comps, formulas, and outcome. No result is an autonomous purchase instruction, and no missing market input becomes an unlabeled estimate.

## Integrated Dual-Plane Data Model

### Property Intelligence Plane

Core entities:

- `Property`
- `ParcelIdentityObservation`
- `ZoningEnvelope`
- `SiteConstraint`
- `CompCandidate`
- `CompQualificationRun`
- `QualifiedComp`
- `UnderwritingScenario`
- `AcquisitionDecision`
- `Claim`
- `Evidence`
- `AnalysisRun`

### Restricted Contact and Outreach Plane

Core entities:

- `Party`
- `PropertyPartyRelationship`
- `ContactObservation`
- `ContactPoint`
- `ContactVerificationRun`
- `ChannelEligibility`
- `SuppressionRecord`
- `OutreachCase`
- `OutreachMessage`
- `Interaction`
- `FollowUpTask`
- `LeadStatusTransition`

### Relationship-first identity

A party is not assumed to own or represent a property merely because a name appears near it.

`PropertyPartyRelationship` records:

- property and party IDs
- role: owner, co-owner, trustee, manager, officer, registered agent, seller, listing agent, broker, attorney, or other representative
- source and evidence IDs
- effective and observed dates
- match confidence
- verification status

A phone number or email is never stored as an unqualified `owner_phone` or `owner_email`. It begins as a source-linked `ContactObservation` and is promoted to a canonical `ContactPoint` only after normalization, deduplication, and verification.

### Contact-point contract

A canonical contact point records:

- party ID
- channel: phone, email, mailing address, or professional profile
- encrypted normalized value
- keyed hash for exact-match lookup and deduplication
- masked display value
- source observations
- retrieval and last-verification dates
- party-match confidence
- deliverability or validity status
- suppression status
- channel eligibility and policy version

Public availability is source provenance, not blanket permission to use every channel.

## Sensitive-Data Isolation and Access

Contact values use application-layer envelope encryption. Encryption keys are managed outside PostgreSQL; plaintext canonical values are not stored in database columns. A keyed hash supports equality matching without exposing the value.

Additional requirements:

- role-based and purpose-based authorization
- masked values in ordinary UI, support tooling, logs, and analytics
- explicit audit events for every unmask, export, verification, and outreach use
- no real contact values in Git, fixtures, prompts, CI output, telemetry, exceptions, or model traces
- minimum-necessary context passed to models and agents
- configurable retention and deletion policies
- workspace and tenant isolation
- suppression checks before a contact becomes send-eligible

Initial roles:

- property analyst
- contact reviewer
- outreach operator
- workspace administrator
- read-only auditor

## Contact Intelligence Service

The service resolves the legal or represented party first and enriches contact points second.

### Individual ownership

```text
authoritative ownership record
    -> identity candidates
    -> corroborating records
    -> candidate contact observations
    -> party-match and contact-match scoring
```

### Entity, trust, or institutional ownership

```text
ownership record
    -> legal entity, trust, or institution
    -> registration or business records
    -> officers, managers, trustees, registered agents, or authorized representatives
    -> candidate contact observations
    -> role-specific match scoring
```

Confidence that a party controls or represents the property is distinct from confidence that a contact point belongs to that party.

Contact outcomes:

- `verified`
- `likely_match`
- `ambiguous`
- `stale`
- `invalid`
- `wrong_party`
- `insufficient_evidence`

In the initial release, only `verified` contact points are send-eligible. A `likely_match` may appear in the review packet for manual research but cannot be scheduled or sent. Changing that rule requires a separate approved policy revision.

## Channel Eligibility and Suppression

`ChannelEligibility` is deterministic, versioned, and evaluated outside the LLM. It considers:

- party role and contact verification status
- workspace campaign type and purpose
- source restrictions and provider terms
- jurisdiction and channel policy profile
- consent or relationship evidence where required
- company-specific and statutory suppression records
- prior opt-outs, complaints, bounces, and invalidations
- allowed contact windows and frequency caps

Policy profiles are approved operational configuration, not model-generated rules. If the required policy or suppression provider is unavailable, sending fails closed.

## Independent Verification Agent

The Verification Agent is read-only and cannot approve, rewrite, promote contacts, change accepted comps, or send.

It receives the claim ledger, evidence references, deterministic inputs, and proposed outcomes. It must not merely reread the final prose and agree with it.

Verification behavior:

1. Re-resolve property identity from authoritative sources.
2. Re-fetch decision-critical zoning and transaction records where practical.
3. Use an alternate source or adapter when available.
4. Recompute distance, similarity, density, valuation, and underwriting calculations.
5. Verify party-to-property relationships separately from contact-point ownership.
6. Verify freshness, validity, suppression, and channel eligibility.
7. Compare evidence hashes, effective dates, retrieval dates, and policy versions.
8. Record conflicts without overwriting the original run.

Every critical claim receives one status:

- `verified`
- `partially_verified`
- `conflict`
- `stale`
- `unverifiable`
- `insufficient_evidence`

A critical property, zoning, comp, underwriting, ownership, contact, suppression, or channel conflict blocks approval readiness. A contact conflict or suppression match blocks outreach regardless of the property score.

## Unified Human-Review Packet

The case is presented in five sections.

### 1. Property identity

Canonical address, parcel or folio, jurisdiction, geometry, identity confidence, source observations, and unresolved ambiguity.

### 2. Development feasibility

Zoning, permitted uses, density, dimensional standards, site constraints, calculations, citations, discretionary approvals, and coverage gaps.

### 3. Comparable transactions and underwriting

Every accepted and rejected comp, exact qualification reason, source and freshness, valuation range, confidence, underwriting assumptions, formulas, residual value, sensitivities, and verifier results.

The UI makes the dependency visible: **comps qualified first; underwriting calculated second**.

### 4. Ownership and contact intelligence

Each party, its property role, effective dates, contact observations, canonical contact points, provenance, match confidence, freshness, validity, suppression, and channel eligibility.

### 5. Decision and outreach

Decision status, unknowns, conflicts, proposed next action, proposed message and channel, follow-up schedule, approvals, and audit context.

Human corrections are versioned labels and never silently mutate the historical run. Labels include:

- correct
- incorrect
- uncertain
- needs newer source
- wrong property
- wrong person
- wrong relationship
- wrong contact
- wrong comp
- calculation error
- policy or suppression error

## Outreach and Follow-Up Service

The initial production release requires human approval before external outreach.

The service may:

- generate a property-specific draft from verified facts
- propose an eligible channel
- schedule an approved message
- execute through an authenticated connector
- record delivery, bounce, reply, opt-out, and error events
- classify responses into neutral workflow states
- propose follow-up tasks
- stop follow-ups when opt-out, suppression, conflict, invalidation, or policy rules require it

The service may not:

- send to a likely, ambiguous, stale, invalid, wrong-party, or suppressed contact
- infer sensitive personal traits
- conceal sender identity
- bypass provider, platform, privacy, suppression, or communication rules
- continue after an opt-out
- represent a hypothetical development outcome as an approved entitlement
- let an LLM decide eligibility or suppression

Reducing human review later requires a separate approved design backed by precision, complaint, suppression, and conversion evidence.

## Evaluation Corpora

Two corpora are required because repository-safe testing and real-world contact verification have different privacy requirements.

### Repository-safe CI corpus

Contains property-level and synthetic data only:

- normalized address, jurisdiction, and parcel identifiers
- asking price and physical attributes
- property type and zoning hint
- expected workflow and outcomes
- synthetic parties and contacts for policy unit tests

It contains no real owner names, phones, emails, mailing addresses, seller or agent contact data, free-text contact notes, or outreach history.

The existing privacy-safe `LeadEvaluationCase` remains appropriate for this corpus. It is not the full production lead schema.

### Restricted evaluation corpus

Contains real source material needed to measure production quality:

- property and parcel identity
- owners, entities, trusts, sellers, agents, and representatives
- evidence-backed party relationships
- mailing addresses, phones, emails, and professional contact points
- provenance and freshness
- comp and underwriting outcomes
- outreach and response history
- human correctness labels

Requirements:

- encrypted storage outside Git
- explicit authenticated refresh
- workspace and role access controls
- redacted benchmark output by default
- no raw values in logs or model traces
- versioned manifests with source IDs and extraction timestamps
- retention and deletion support

CI consumes only the repository-safe corpus. Restricted benchmarks run as explicit authenticated jobs.

## Reproducibility Contract

Every material run records:

- analysis run ID
- property and parcel IDs
- normalized input
- source record identifiers and retrieval timestamps
- source hashes or immutable references
- ordinance effective dates
- provider and adapter versions
- code commit SHA
- tool-contract, comp-policy, formula, contact-policy, and channel-policy versions
- model and prompt versions
- accepted and rejected comp IDs
- contact-observation and contact-point IDs
- verification run ID
- human-review version
- outreach approval and execution IDs

Rerun modes:

- **Replay** — use the exact stored evidence snapshot to reproduce the historical result.
- **Refresh** — retrieve current evidence and produce a structured change report.

## Evaluation Metrics and Initial Gates

### Property and zoning

- parcel and jurisdiction precision
- zoning and dimensional-standard accuracy
- citation coverage
- calculation exactness
- correct abstention rate

### Comparable sales

- accepted-comp precision and relevant-comp recall
- rejection-reason accuracy
- subject and duplicate rejection rate
- recorded-price accuracy
- source diversity and freshness
- valuation difference from manual review
- confidence calibration

### Underwriting

- formula exactness
- assumption-lineage completeness
- sensitivity reproducibility
- conservative-basis accuracy
- recommendations produced without required inputs: zero

### Ownership and contacts

- owner and party-role precision
- entity-to-decision-maker precision
- phone, email, and mailing-address precision
- wrong-party, stale, invalid, and bounce rates
- suppression-check coverage

### Verification

- true-error catch rate
- false-conflict rate
- critical-claim coverage
- percentage of human corrections predicted by the verifier
- critical errors reaching human review undetected

### Outreach

- approved-to-sent, delivery, bounce, reply, positive-response, qualified-lead, and meeting rates
- opt-out and complaint rates
- follow-up conversion

### Initial hard gates

- 100% reproducible deterministic calculations
- no underwriting invocation before `CompQualificationResult`
- no market-supported recommendation when comps are insufficient, stale, or conflicting
- no unresolved critical parcel, zoning, comp, underwriting, ownership, or contact conflict
- no outreach to a non-verified or suppressed contact
- 100% suppression and channel-eligibility checks before scheduling or sending
- human approval before production outreach

## Migration from `feature/outreach-agent`

The separate outreach branch is a source of reusable adapters and concepts, not the target architecture.

Selectively reuse or port:

- email enrichment adapters
- authenticated email delivery
- message-drafting patterns
- interaction and pipeline concepts
- provider error handling
- event or professional-network discovery only when it serves an approved workflow

Replace or retire:

- the generic prospect record as the primary property lead identity
- a separate SQLite production database
- direct autonomous campaign execution
- unverified person-to-property matching
- status-only tracking without claim and evidence provenance
- any orchestrator that can enrich and send before verification and approval

The existing PlotLot `OutreachPanel` evolves into the unified review and approval surface rather than remaining a manually entered email form disconnected from party and contact evidence.

## Program Decomposition

This document is the umbrella architecture. It is intentionally decomposed into independently reviewable implementation slices rather than one mega-change.

### Slice A — Canonical core and property identity

Characterization tests, `AnalysisService`, `ToolExecutor`, typed outcomes, claim ledger, and property identity contract.

### Slice B — Reliable comps and underwriting gate

Deterministic comp qualification, immutable accepted and rejected sets, hard `CompQualificationResult` dependency, underwriting refactor, and conservative decision packet.

### Slice C — Restricted contact intelligence

Party and relationship models, encrypted contact observations and points, contact verification, channel eligibility, suppression, and access auditing.

### Slice D — Independent verification and review packet

Read-only verifier, claim comparison, replay and refresh, conflict gates, human labels, and unified review UI.

### Slice E — Governed outreach and evaluation

Approved connector execution, response and follow-up state, restricted benchmark corpus, metrics, and release gates.

Each slice receives its own detailed implementation plan, tests, review, and terminal verification. Slice B must preserve the domain dependency **reliable comps before underwriting**, even if contact work is developed concurrently on a separate branch later.

## High-Level Delivery Order

1. baseline and characterization tests
2. canonical application-service and tool-executor boundaries
3. property identity contract
4. reliable comparable-sale qualification
5. underwriting refactor requiring qualified comps
6. restricted party, relationship, contact, and suppression models
7. Contact Intelligence Service
8. independent Verification Agent
9. unified human-review packet
10. governed outreach and follow-up integration
11. restricted benchmark and release gates

This sequence is architecture, not permission to implement before the written specification is reviewed.

## Testing Strategy

### Characterization and architecture

- Sync and streamed analysis share the same final report for an injected deterministic pipeline.
- All transports return equivalent policy outcomes.
- Approval IDs are validated once through `ToolExecutor`.
- Evidence IDs survive execution and reporting.
- API routes do not import underscore-prefixed pipeline helpers.
- Domain modules do not import API or storage transports.
- Underwriting cannot retrieve or select comps.
- Outreach cannot send outside `OutreachService` and `ToolExecutor`.
- Sensitive contact data cannot be accessed outside authorized services.
- No second property-analysis or outreach architecture is introduced.

### Comps-before-underwriting

- missing qualification results are rejected
- insufficient, stale, or conflicting results block market-derived underwriting
- accepted and rejected sets remain immutable during underwriting
- evidence IDs and normalized values pass into underwriting
- replay reproduces qualification and underwriting outcomes

### Contact and outreach

- party and contact confidence are scored separately
- ambiguous relationships block contact promotion
- only verified contacts become send-eligible
- suppression blocks scheduling and sending
- masked values require an audited authorization to unmask
- every send has evidence, policy, approval, and audit references
- opt-out terminates follow-ups

### Verification and evaluation

- the verifier is read-only
- critical claims are independently re-fetched or recomputed
- conflicts never overwrite the original run
- critical conflicts block approval readiness
- repository-safe fixtures contain no real contact data
- restricted exports are redacted by default
- benchmark output records evidence, abstention, conflict, and human-correction behavior

## Error Handling

Canonical errors include:

- `bad_input`
- `not_found`
- `ambiguous_property`
- `unsupported_market`
- `coverage_gap`
- `provider_timeout`
- `provider_unavailable`
- `source_stale`
- `approval_required`
- `human_approval_required`
- `policy_denied`
- `budget_exceeded`
- `comps_insufficient`
- `verification_conflict`
- `owner_conflict`
- `contact_unverified`
- `contact_suppressed`
- `channel_ineligible`
- `insufficient_evidence`
- `internal_error`

No unavailable source becomes an unlabeled model estimate. No failed contact verification becomes eligible through narrative reasoning.

## Provider Health

Health checks distinguish:

- application unavailable
- provider unavailable or timed out
- discovery candidate rejected by validation
- source reachable but stale
- authorization or quota failure
- contact provider unavailable
- suppression provider unavailable

The deployed API probe uses bounded retries with per-attempt evidence. Provider tests record source IDs, validation scores, and rejection reasons while redacting sensitive values. Live provider outages do not fail deterministic unit tests, but nightly health remains red and actionable.

## Repository Scaffolding Policy

Remove from the product tree:

- `.claude/`
- `.omo/`
- `plotlot/.omx/`
- root and nested `CLAUDE.md`
- `GEMINI.md`
- hard-coded personal prospect lists, identities, or outreach instructions used as source code
- generated agent execution evidence used as source code

This does not prohibit authenticated workspace lead records in the production database. It prohibits embedding personal operational data in the repository.

Retain one neutral root `AGENTS.md`. Deterministic fixtures move to `plotlot/tests/fixtures/`. Repository hygiene fails if removed workspace-state directories or personal-context files return.

Dagster and dbt remain documented as non-runtime analytics tooling until active ownership and deployment are verified. Destructive removal requires a separate evidence-backed decision.

## Non-goals

- a new outreach microservice
- rewriting every county adapter
- replacing PostgreSQL or the existing job queue
- autonomous purchasing or binding offers
- unreviewed or policy-ungoverned mass outreach
- bypassing platform, provider, privacy, suppression, or communication rules
- storing real contact data in Git or public CI artifacts
- deleting analytics projects without ownership evidence
- claiming uniform nationwide zoning, comp, owner, or contact coverage
- a broad visual redesign unrelated to review and approval

## Definition of Done

1. Baseline failures have reproducible commands and root-cause evidence.
2. The branch contains no tracked AI workspace state or personal tool instructions.
3. One analysis service powers JSON and SSE while compatibility adapters preserve callers.
4. One governed tool executor owns approvals, sensitive-data access, persistence, evidence, artifacts, and audit outcomes.
5. Property identity resolves before owner, comp, underwriting, contact, or outreach records attach.
6. Reliable comps deterministically accept or reject candidates and complete before underwriting.
7. Underwriting cannot select comps or issue a market-supported recommendation when comps are insufficient, stale, or conflicting.
8. Property and restricted contact data are linked through evidence-backed party relationships without flattening sensitive values.
9. The Verification Agent independently checks property, zoning, comps, underwriting, ownership, contacts, suppression, and channel eligibility without mutation authority.
10. A unified review packet exposes accepted and rejected evidence, calculations, conflicts, contact eligibility, and proposed outreach.
11. Production outreach requires verified contacts, suppression and eligibility checks, and human approval.
12. Repository-safe and restricted corpora have explicit privacy boundaries and reproducible manifests.
13. Backend, frontend, Playwright, provider-health, restricted-benchmark, and release gates have explicit terminal results.
14. No cleanup or lead-intelligence change merges into `main` without required checks and review.
