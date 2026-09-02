# PlotLot De-Slop, Lead Intelligence, and Evaluation Architecture

**Date:** 2026-09-01  
**Revision:** 2026-09-01 — integrated dual-plane architecture approved; reliable comps moved before underwriting  
**Base:** `cpt-pro@a3531aed37b6d7186addc1ef3b8ee00ec5199778`  
**Work branch:** `feat/cpt-pro-deslop`

## Approved Product Decision

PlotLot will use **Option 1: one integrated product with two controlled data planes**.

1. **Property Intelligence Plane** — parcel identity, zoning, site constraints, reliable comparable sales, underwriting, evidence, and decision support.
2. **Restricted Contact and Outreach Plane** — owners, trusts, entities, registered agents, sellers, brokers, contact observations, verified contact points, suppression records, outreach, responses, and follow-ups.

The planes share one authenticated product, application-service layer, PostgreSQL deployment, evidence model, audit trail, and human-review workflow. Sensitive contact data is not flattened into unrestricted property records and is never copied into public fixtures, ordinary logs, analytics events, or model traces.

A second architectural decision is also approved:

> **Reliable comparable-sale qualification is completed before market-derived underwriting.**

Underwriting may not independently select comps, accept an unqualified market value, or produce an acquisition recommendation before a `CompQualificationResult` exists. When comparable evidence is insufficient, PlotLot must abstain, request inputs, or produce an explicitly incomplete scenario. It may not silently substitute an LLM estimate.

## Objective

Reduce PlotLot to one understandable, reproducible product architecture while preserving the useful multi-agent harness and expanding it into a governed property-to-outreach system.

The system must:

- resolve the correct property and parcel
- retrieve source-backed zoning and site evidence
- qualify reliable comparable transactions
- perform deterministic underwriting only after comps are qualified
- resolve owners, entities, sellers, agents, and contact points with provenance
- independently verify all decision-critical claims
- present one review packet to a human
- generate and execute compliant outreach only after approval
- track responses and follow-ups into a warm-lead pipeline
- support exact replay against stored evidence and refresh against current sources

The cleanup must not conceal existing failures, invent market coverage, weaken approval controls, expose sensitive contact data, or make an LLM responsible for deterministic zoning, comparable-sale, or underwriting calculations.

## Program Deliverables

1. Establish and record the real operational and test baseline.
2. Work in an isolated branch based on `cpt-pro`.
3. Add characterization and architecture tests before moving behavior.
4. Remove tracked AI workspace state, stale personal instructions, and disconnected scaffolding.
5. Introduce one canonical analysis application service for JSON, SSE, chat, MCP, CLI, and agent tools.
6. Introduce one governed tool-execution transaction for all transports.
7. Add deterministic comparable-sale qualification as a prerequisite to underwriting.
8. Refactor underwriting to consume qualified comps and explicit, versioned assumptions.
9. Add restricted party, ownership, contact-observation, contact-point, suppression, and outreach models.
10. Add a read-only independent Verification Agent and a unified human-review packet.
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

These are baseline defects. Cleanup work may fix them, but must not relabel, skip, or suppress them.

## Architectural Decision

Use an incremental strangler migration, not a rewrite and not a new microservice.

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
6. Acquisition decision packet    Contact-match and channel eligibility
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

Contact enrichment may begin after the property identity is resolved and may execute concurrently with zoning and comps retrieval. This parallelism does not change the financial dependency: **reliable comps must finish before underwriting**, and both must pass verification before the case can advance.

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
- Existing deterministic provider, ordinance, calculation, comps, and pro-forma components are reused behind explicit interfaces.
- No API route imports underscore-prefixed pipeline functions.
- Partial coverage and timeouts become explicit typed outcomes.
- The current `lookup_address()` function remains a compatibility adapter until all callers migrate.
- The service records a claim ledger and evidence references rather than returning only narrative prose.
- The pipeline order is enforced in code and tests: property identity, zoning/site evidence, qualified comps, underwriting, and decision packet.

## Canonical Tool Executor

`HarnessRuntime` remains the low-level policy and handler runtime. Add one application-level `ToolExecutor` transaction around it to own:

1. canonical contract lookup and argument validation
2. workspace, project, site, property, party, and outreach-case context resolution
3. durable approval validation
4. role and purpose authorization
5. governed runtime call
6. tool-run persistence
7. evidence validation and persistence
8. artifact, report, and document persistence
9. sensitive-field redaction for logs and traces
10. audit events
11. commit or rollback
12. canonical transport-neutral result mapping

REST tools, chat, HTTP MCP, FastMCP, and multi-agent execution must call this executor instead of duplicating approval, PII-access, persistence, or policy behavior.

## Property Identity Contract

An address string is an input, not the permanent identity of a site.

The property resolver must produce:

- stable internal `property_id`
- canonical address
- jurisdiction, municipality, county, and state
- parcel, folio, or APN identifiers
- geographic coordinates
- parcel geometry or authoritative geometry reference
- multi-parcel and unit ambiguity flags
- source observations and retrieval timestamps
- identity confidence

Owner, contact, zoning, comp, and outreach records may be attached only after property identity resolution. Ambiguous or conflicting parcel resolution produces `ambiguous_property` and blocks underwriting and outreach.

## Reliable Comparable Sales — Required Before Underwriting

Comparable-sale qualification is a dedicated deterministic capability, not a prompt instruction and not a hidden step inside underwriting.

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
- missing the transaction fields required for the selected valuation basis

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
    status: str
```

Every accepted and rejected candidate retains its source, retrieval time, normalized transaction fields, computed distance, similarity measurements, and exact acceptance or rejection reasons.

Valuation is withheld unless the configured minimum number of qualified transactions remains. The initial default is three qualified sales, subject to property-type-specific policy. Confidence depends on count, freshness, distance, similarity, transaction quality, and source diversity.

The LLM may explain the result. It may not re-admit an excluded transaction, invent a transaction, alter a recorded value, or create a market value when the deterministic capability abstains.

### Hard underwriting gate

`UnderwritingService` requires a `CompQualificationResult` argument. It may not query or select comps itself.

- `qualified`: market-derived underwriting may proceed.
- `insufficient_evidence`: market-derived underwriting is blocked.
- `conflict`: underwriting is blocked until review or refresh.
- `stale`: the comps capability must refresh or the user must explicitly approve a stale-evidence exception.

A cost-only or user-supplied hypothetical scenario may still be calculated, but it must be labeled `incomplete_scenario`, may not be represented as market-supported, and may not produce `advance_for_review`.

## Deterministic Underwriting

Underwriting begins only after the comps gate passes.

The underwriting service consumes:

- `CompQualificationResult`
- verified zoning and site envelope
- explicit development program assumptions
- versioned cost, financing, timing, rent, sale, and exit assumptions
- user overrides with author, timestamp, and reason

It produces:

- market-supported revenue assumptions derived from accepted comps or explicitly identified external inputs
- development costs
- financing and carry costs
- residual land value
- sensitivity ranges
- missing-input and model-risk flags
- exact formulas and formula version
- evidence and assumption lineage

The acquisition decision basis is the lower supported value of:

- the conservative floor or policy-selected bound of the qualified comparable-sale range
- the deterministic residual land-value ceiling

Possible decision outcomes are:

- `advance_for_review`
- `hold_for_inputs`
- `reject_buy_box`
- `insufficient_evidence`

No result is an autonomous purchase instruction. No missing market input becomes an unlabeled estimate.

## Integrated Dual-Plane Data Model

### Property Intelligence Plane

Core entities include:

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

Core entities include:

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

A party is not assumed to be the owner merely because a name appears near a property.

`PropertyPartyRelationship` records:

- `property_id`
- `party_id`
- role: owner, co-owner, trustee, manager, officer, registered agent, seller, listing agent, broker, attorney, or other representative
- source and evidence IDs
- effective and observed dates
- match confidence
- verification status

A phone number or email is never stored as an unqualified `owner_phone` or `owner_email` field. It is a contact observation associated with a party and source, then promoted to a canonical contact point only after normalization, deduplication, and verification.

### Contact-point contract

A canonical contact point records:

- party ID
- channel: phone, email, mailing address, or professional profile
- encrypted normalized value
- masked display value
- source observations
- retrieval and last-verification dates
- ownership or role-match confidence
- deliverability or validity status
- suppression status
- channel eligibility and policy version

Public availability is evidence provenance, not blanket permission to use every channel.

## Contact Intelligence Service

The contact service resolves the legal or represented party first and enriches contact points second.

### Individual ownership

```text
authoritative ownership record
    -> individual identity candidates
    -> corroborating records
    -> candidate contact observations
    -> party and contact match scoring
```

### Entity, trust, or institutional ownership

```text
ownership record
    -> legal entity, trust, or institution
    -> business or registration records
    -> officers, managers, trustees, registered agents, or authorized representatives
    -> candidate contact observations
    -> role-specific match scoring
```

The service distinguishes between confidence that a party controls or represents the property and confidence that a contact point belongs to that party.

Contact outcomes are:

- `verified`
- `likely_match`
- `ambiguous`
- `stale`
- `invalid`
- `wrong_party`
- `insufficient_evidence`

Only policy-approved `verified` and narrowly defined `likely_match` records can advance to human outreach review. All other outcomes block sending.

## Sensitive-Data Isolation and Access

Sensitive contact records remain inside the integrated PlotLot product but receive stricter controls than ordinary parcel facts.

Requirements:

- field-level or application-layer encryption for contact values
- role-based and purpose-based authorization
- masked values in ordinary UI, logs, support tooling, and analytics
- explicit audit events for every unmask, export, verification, and outreach use
- no real contact data in Git, repository fixtures, prompt templates, ordinary CI output, telemetry, exception messages, or model traces
- minimum-necessary context passed to models and agents
- configurable retention and deletion policies
- tenant and workspace isolation
- suppression records checked before drafting, scheduling, or sending

Initial roles should distinguish at least:

- property analyst
- contact reviewer
- outreach operator
- workspace administrator
- read-only auditor

## Independent Verification Agent

The Verification Agent is read-only and cannot approve, rewrite, or send.

It receives a claim ledger, source references, deterministic inputs, and proposed outcomes. It must not merely reread the final prose and agree with it.

### Verification behavior

1. Re-resolve the property identity from authoritative sources.
2. Re-fetch decision-critical zoning and transaction records where practical.
3. Use an alternate source or adapter when one is available.
4. Recompute distance, similarity, density, valuation, and underwriting calculations.
5. Verify party-to-property relationships separately from contact-point ownership.
6. Verify freshness, validity, and suppression status for proposed outreach channels.
7. Compare evidence hashes, effective dates, retrieval dates, and policy versions.
8. Record conflicts without overwriting the original analysis.

### Claim statuses

Every critical claim receives one status:

- `verified`
- `partially_verified`
- `conflict`
- `stale`
- `unverifiable`
- `insufficient_evidence`

A critical property, ownership, zoning, comps, underwriting, or contact conflict blocks the review packet from becoming approval-ready. A contact conflict or suppression match blocks outreach regardless of the property opportunity score.

## Unified Human-Review Packet

The completed case is presented as one review packet with five sections.

### 1. Property identity

- canonical address
- parcel or folio
- jurisdiction
- map boundary
- identity confidence
- source observations
- unresolved ambiguity

### 2. Development feasibility

- zoning and permitted uses
- density and dimensional standards
- site constraints
- deterministic calculations
- citations
- unresolved discretionary approvals or coverage gaps

### 3. Comparable transactions and underwriting

- every accepted and rejected comp
- qualification reasons
- source and freshness
- valuation range and confidence
- underwriting assumptions and formulas
- residual value and sensitivities
- verifier result for each material calculation

The UI must make the approved dependency visible: **comps qualified first, underwriting calculated second**.

### 4. Ownership and contact intelligence

- each party and its property role
- effective dates
- contact observations and canonical contact points
- source provenance
- match and verification confidence
- freshness, validity, deliverability, and suppression status
- outreach eligibility by channel

### 5. Decision and outreach

- supported decision status
- unknowns and conflicts
- proposed next action
- proposed message and channel
- proposed follow-up schedule
- required approvals
- complete policy and audit context

Human corrections are stored as versioned labels. They never silently mutate the historical run.

Supported review labels include:

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

The initial production release uses human approval before external outreach.

The service may:

- generate a property-specific draft from verified facts
- propose the best eligible channel
- schedule an approved message
- execute through an authenticated connector
- record delivery, bounce, reply, opt-out, and error events
- classify responses into neutral workflow states
- propose follow-up tasks
- stop follow-ups when suppression, opt-out, conflict, or policy rules require it

The service may not:

- send to an ambiguous, stale, invalid, wrong-party, or suppressed contact
- infer sensitive personal traits
- conceal sender identity
- bypass provider, platform, statutory, or workspace rules
- continue after an opt-out
- represent a hypothetical development outcome as an approved entitlement
- let the LLM decide channel eligibility or suppression

Later automation may reduce review requirements only after channel-specific precision, complaint, suppression, and conversion gates are met and approved as a separate change.

## Migration from `feature/outreach-agent`

The separate outreach branch is a source of reusable adapters and concepts, not the target architecture.

Selectively reuse or port:

- email enrichment adapters
- authenticated email delivery
- message drafting patterns
- interaction and pipeline concepts
- provider error handling
- event or professional-network discovery only where it serves an approved product workflow

Replace or retire:

- the generic prospect record as the primary property lead identity
- a separate SQLite production database
- direct autonomous campaign execution
- unverified person-to-property matching
- status-only tracking without claim and evidence provenance
- any orchestrator that can enrich and send before verification and human approval

The existing PlotLot `OutreachPanel` should evolve into the unified review and approval surface rather than remain a manually entered email form disconnected from party and contact evidence.

## Evaluation Corpora

Two corpora are required because reproducible testing and real-world contact verification have different privacy requirements.

### Repository-safe CI corpus

Contains only property-level and synthetic data needed for deterministic tests:

- normalized address
- city, county, and state
- parcel or folio
- asking price
- lot and building attributes
- property type
- zoning hint
- expected workflow and outcomes
- synthetic parties and contact points for contact-policy unit tests

It contains no real owner names, phones, emails, mailing addresses, seller or agent contact data, free-text contact notes, or outreach history.

The existing privacy-safe `LeadEvaluationCase` remains appropriate for this corpus. Its purpose is repository and CI safety, not the full production lead schema.

### Restricted evaluation corpus

Contains the real source material needed to measure production quality:

- property and parcel identity
- owners, entities, trusts, sellers, agents, and representatives
- source-backed party relationships
- mailing addresses, phone numbers, emails, and professional contact points
- source provenance and freshness
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
- deletion and retention support

CI consumes only the repository-safe corpus. Restricted benchmarks run as explicit authenticated jobs.

## Reproducibility Contract

Every material run records:

- analysis run ID
- property and parcel IDs
- normalized input
- source record identifiers
- retrieval timestamps
- source-content hashes or immutable source references
- ordinance effective dates
- provider and adapter versions
- code commit SHA
- tool-contract version
- comp-policy version
- formula version
- model and prompt version
- contact-match policy version
- channel-eligibility and suppression-policy versions
- accepted and rejected comp IDs
- contact-observation and canonical contact-point IDs
- verification run ID
- human-review version
- outreach approval and execution IDs

PlotLot supports two rerun modes:

- **Replay** — run against the exact stored evidence snapshot to reproduce the historical conclusion.
- **Refresh** — retrieve current evidence and produce a structured change report.

## Evaluation Metrics and Release Gates

### Property and zoning

- parcel-resolution precision
- jurisdiction-resolution accuracy
- zoning-code accuracy
- citation coverage
- dimensional-standard accuracy
- deterministic calculation exactness
- correct abstention rate

### Comparable sales

- accepted-comp precision
- relevant-comp recall
- rejection-reason accuracy
- duplicate and subject-property rejection rate
- recorded sale-price accuracy
- source-diversity and freshness distribution
- valuation-range difference from manual review
- confidence calibration

### Underwriting

- formula exactness
- assumption-lineage completeness
- sensitivity reproducibility
- conservative-basis accuracy
- rate of recommendations produced without required inputs, which must be zero

### Ownership and contacts

- current-owner precision
- party-role precision
- entity-to-decision-maker precision
- phone-match precision
- email-match precision
- mailing-address accuracy
- wrong-party contact rate
- stale and invalid contact rate
- bounce rate
- suppression-check coverage

### Verification

- true-error catch rate
- false-conflict rate
- critical-claim coverage
- percentage of human corrections predicted by the verifier
- percentage of critical errors that reached human review undetected

### Outreach

- approved-to-sent rate
- delivery and bounce rate
- reply rate
- positive-response rate
- qualified-lead and meeting rate
- opt-out and complaint rate
- follow-up conversion

### Initial hard gates

- 100% reproducible deterministic calculations
- no underwriting invocation before a comp qualification result
- no market-supported recommendation when comps are insufficient
- no unresolved parcel, zoning, ownership, comp, or underwriting conflict
- no outreach to an ambiguous, stale, invalid, wrong-party, or suppressed contact
- 100% suppression check before scheduling and sending
- human approval required before production outreach

## Provider Health

Health checks distinguish:

- application unavailable
- provider unavailable or timed out
- discovery candidate rejected by quality validation
- source reachable but stale
- authorization or quota failure
- contact provider unavailable
- suppression provider unavailable

The deployed API probe uses bounded retries with per-attempt evidence. Provider tests log candidate URLs or source IDs, validation scores, and rejection reasons while redacting sensitive values. A live provider outage does not cause deterministic unit-test failure, but the nightly health workflow remains red and actionable.

## Testing Strategy

### Characterization

- Sync and streamed analysis share the same final report for an injected deterministic pipeline.
- All transports return equivalent policy outcomes for the same tool and context.
- Approval IDs are validated once through the canonical executor.
- Evidence identifiers survive tool execution and reporting.
- Existing specialist boundaries are preserved during migration.

### Architecture

AST and import tests prohibit:

- API routes importing underscore-prefixed pipeline helpers
- chat or MCP directly invoking canonical tool handlers
- domain modules importing API or storage transports
- a second independent property-analysis or outreach architecture
- underwriting selecting or retrieving comps
- outreach sending outside `OutreachService` and `ToolExecutor`
- contact data access outside authorized application services
- tracked `.claude`, `.omo`, or `.omx` paths

### Comps-before-underwriting contract

- `UnderwritingService` rejects a missing comp qualification result
- insufficient, stale, or conflicting comps block market-derived underwriting
- qualified comps pass normalized values and evidence IDs into underwriting
- accepted and rejected sets remain immutable within the underwriting run
- replay reproduces the same qualification and underwriting result

### Contact and outreach

- party and contact confidence are scored separately
- ambiguous relationships block canonical contact promotion
- suppression blocks draft scheduling and sending
- masked fields remain masked without an authorized unmask operation
- every send has evidence, policy, approval, and audit references
- opt-out terminates follow-up tasks

### Verification

- the verifier is read-only
- critical claims are independently re-fetched or recomputed
- conflicts never overwrite the original run
- a critical conflict blocks approval readiness

### Evaluation

- the repository-safe fixture contains no real contact data
- restricted corpus exports are redacted by default
- each property has a normalized identity and stable case ID
- benchmark output records evidence, abstention, conflict, and human-correction behavior

## Error Handling

Canonical application errors include:

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

No unavailable source is replaced with an unlabeled model estimate. No failed contact verification is converted into an eligible contact by narrative reasoning.

## Repository Scaffolding Policy

Remove from the product tree:

- `.claude/`
- `.omo/`
- `plotlot/.omx/`
- root `CLAUDE.md`
- nested `plotlot/CLAUDE.md`
- `GEMINI.md`
- hard-coded personal prospect lists, identities, or outreach instructions used as source code
- generated agent execution evidence used as source code

This restriction does not prohibit authenticated customer or workspace lead records in the production database. It prohibits embedding personal operational data in the repository.

Retain one neutral root `AGENTS.md`. Deterministic fixtures required by tests move to `plotlot/tests/fixtures/`. Repository hygiene fails if removed workspace-state directories or personal-context files return.

Dagster and dbt are not deleted in this first cleanup commit. They remain documented as non-runtime analytics tooling until active ownership and deployment are verified; destructive removal requires a separate evidence-backed decision.

## Non-goals

- a new outreach microservice
- rewriting every county adapter
- replacing PostgreSQL or the existing job queue
- autonomous purchasing or binding offers
- unreviewed or policy-ungoverned mass outreach
- bypassing platform, provider, suppression, privacy, or communication rules
- storing real contact data in Git or public CI artifacts
- deleting analytics projects without ownership evidence
- claiming uniform nationwide zoning, comp, owner, or contact coverage
- a broad visual redesign unrelated to the review and approval workflow

## High-Level Delivery Order

The implementation must preserve the approved dependency order:

1. baseline and characterization tests
2. canonical application-service and tool-executor boundaries
3. property identity contract
4. reliable comparable-sale qualification
5. underwriting refactor to require qualified comps
6. restricted party, relationship, contact, and suppression models
7. contact intelligence service
8. independent Verification Agent
9. unified human-review packet
10. governed outreach and follow-up integration
11. restricted benchmark and release gates

This is sequencing within one architecture, not approval to implement before the written specification is reviewed.

## Definition of Done

1. Baseline failures are documented with reproducible commands and root-cause evidence.
2. The cleanup branch contains no tracked AI workspace state or personal tool instructions.
3. One analysis service powers JSON and SSE while compatibility adapters preserve callers.
4. One governed tool executor owns approvals, sensitive-data access, persistence, evidence, artifacts, and audit outcomes across transports.
5. Property identity is resolved before owner, comp, underwriting, or outreach records are attached.
6. Reliable comps deterministically accept or reject candidates and are completed before underwriting.
7. Underwriting cannot select comps and cannot produce a market-supported recommendation when comps are insufficient.
8. Property and restricted contact data remain linked through evidence-backed party relationships without flattening PII into unrestricted records.
9. The Verification Agent independently checks property, zoning, comps, underwriting, ownership, contacts, and channel eligibility without mutation authority.
10. A unified human-review packet exposes accepted and rejected evidence, calculations, conflicts, contact eligibility, and proposed outreach.
11. Production outreach requires verified contact eligibility, suppression checks, and human approval.
12. Repository-safe and restricted evaluation corpora exist with explicit privacy boundaries and reproducible manifests.
13. Full backend, frontend, Playwright, provider-health, restricted-benchmark, and release gates have explicit terminal results.
14. No cleanup or lead-intelligence commit is merged into `main` without required checks and review.
