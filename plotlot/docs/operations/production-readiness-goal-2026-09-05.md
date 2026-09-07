# PlotLot production-readiness goal

## Launch scope revised September 7, 2026

The user replaced San Diego with Lee County, Florida, and Mecklenburg and Gaston
counties, North Carolina. The six launch counties are Miami-Dade, Broward, Palm
Beach, Lee (FL), Mecklenburg (NC, including Charlotte), and Gaston (NC). Charlotte
means the city in Mecklenburg County, not Charlotte County, Florida.

San Diego is deferred, not a launch prerequisite. Preserve its existing code,
source corpus, tests, and research; this decision does not authorize deletion.
New target coverage is not implemented or verified coverage. Existing Mecklenburg
property-provider code requires validation; automatic comps currently have no
pinned source for any of the three newly targeted counties.

Reliable useful property, zoning, and comp results remain the immediate priority;
sign-in configuration stays deferred. Provider budgets, evidence standards, human
approval, tenant isolation, and all other final release requirements are unchanged.
The app goal control was observed paused on September 7; this document records the
new scope but does not resume it or mutate the saved goal-control prompt.
The user subsequently authorized small verified checkpoint commits and pushes to
GitHub as the ongoing standard. This supersedes earlier no-commit/no-push wording;
it does not authorize production deployment, merges or history rewriting.

## Executable goal prompt

Complete evidence-backed production readiness for PlotLot on the existing
`cpt-pro` worktree. Replace NVIDIA NIM text inference with OpenRouter DeepSeek V4
Flash as the direct primary for analysis and chat. Keep Groq image review advisory.
Use the existing roughly $4 OpenRouter balance conservatively with price, token,
credit, timeout and retry safeguards. Never silently route to other paid models.

Build, test and iterate through real workflows for Miami-Dade, Broward, Palm Beach,
and Lee counties in Florida, and Mecklenburg and Gaston counties in North Carolina:
authoritative parcel identity and zoning; qualified closed-sale comps and explicit
accepted/rejected provenance; reviewed at-sale construction/condition facts;
abstention when evidence is insufficient or conflicting; gated underwriting and
documents; authenticated tenant isolation; truthful provider/schema readiness;
and responsive, accessible UI behavior. Photos and price jumps are advisory only.

Completion requires current passing checks and observed real-app success and
failure scenarios, independent review, no unresolved release-critical defects,
and a clear release-readiness receipt. Credentials, mocks and a successful build
alone do not establish readiness. Missing real evidence or authentication remains
a blocker, never a fact to invent or a guard to bypass.

Preserve unrelated changes and secrets. Create reviewed, verified checkpoint
commits and push them to the confirmed GitHub development branch (`origin/cpt-pro`
for this work). Do not deploy, merge to main, force-push, rewrite history, alter
provider accounts, buy credits, change auto-top-up, migrate shared/production
databases, or perform outreach. Use isolated local databases and task-owned processes.
Exhaust safe local alternatives; ask for exact missing authority/information when
necessary. Respect user pauses; when running, keep the goal active until achieved
or genuinely blocked under goal rules. San Diego is outside launch scope; preserve
its existing work without requiring new San Diego acquisition or release checks.

## Historical execution board (September 5-6)

The entries below retain their original evidence and dates. Their test counts and
goal-control state are not current verification. The September 7 scope above
supersedes their South Florida/San Diego market references.

1. completed: direct OpenRouter primary, bounded spending, independent safety
   review and real analysis/chat/stream QA. Broader release checks remain below.
2. completed: close missing reference migrations, least-privilege readiness,
   Stripe absent-secret rejection and ordinance-search outage behavior on isolated
   local services. Schema, Stripe guard and ordinance fixes accepted/live-checked.
   Deployment defaults accepted; actual Docker build/default fail-closed startup
   verified. No-credentials image never served a request.
   Repair plan:2026-09-05-production-blocker-repairs.md.
3. blocked: production sign-in verification needs real Clerk configuration/test
   accounts and persisted memberships; secure location requested. Account-private
   subscription RLS/writer repair completed and independently accepted after all
   three permission findings were fixed. Current2683 combined backend checks and
   62 database/storage checks pass. Actual restricted-login helper QA confirms
   post-commit isolation and quota persistence. This does not prove real sign-in.
   Additional observed gaps: browser calls omit bearer identity and backend parses
   legacy organization claims only. Scoped sign-in repair approval requested.
4. blocked: representative positive comps and responsive/accessibility QA need
   reviewed real evidence and real sign-in, preserving qualification and approval.
   Existing image-aware Groq routing is not an implemented visual-comp workflow.
   Advisory authorized-photo workflow design approval and real reviewed evidence
   requested; no photo-classification accuracy claim yet.
5. blocked: final whole-change release review depends on the remaining gates.
   A bounded current checkpoint is recorded in
   ../research/production-readiness-checkpoint-2026-09-06.md.
   Dependency fixes accepted: frozen production backend audit171dependencies/zero
   vulnerabilities and frontend production audit zero. Current backend combined
   2683passed, storage62passed and crash-recovery1passed; frontend80tests/build pass.
   Current account-source Docker build passes; production startup rejects missing
   identity. Local test services stopped, test logins disabled, evidence retained.

The execution prompt was created and run. The overall goal is not complete;
remaining steps are blocked on the explicit configuration/evidence/design gates,
not declared successful from synthetic checks. No deployment was attempted.

2026-09-06 09:30UTC: after three consecutive revalidated input-blocked turns,
the goal was marked blocked, not complete. Resume with the secure Clerk test
configuration path and the remaining recorded evidence/design handoffs.

This goal supersedes earlier NVIDIA/free-only routing choices only for the named
OpenRouter text model. All other evidence, safety and authorization constraints remain.
