# Semantic State Matrix

States are semantic. Color, icon, label, accessible text, action availability, and replay behavior must agree.

| Domain | State | Visible meaning | Permitted action | Forbidden implication / behavior |
|---|---|---|---|---|
| Coverage | `private_beta_enabled` | `MIAMI-DADE PRIVATE BETA` plus locality scope and policy date | begin supported gate | countywide public/live coverage |
| Coverage | `municipality_conditional` | `BROWARD — MUNICIPALITY-CONDITIONAL` | resolve municipality / capture intake | Broward-wide analysis availability |
| Coverage | `planned_not_enabled` | `SAN DIEGO — PLANNED, NOT ENABLED` | save intake / enablement interest | analysis, capacity result, or review approval |
| Coverage | `unsupported` | unsupported jurisdiction | export intake | hidden or ambiguous failure |
| Parcel | `resolved` | stable redacted folio/APN and jurisdiction | proceed | exact street address leakage |
| Parcel | `ambiguous` | multiple candidate records; confirmation required | select/research | choosing a parcel silently |
| Zoning / rule | `verified` | citation, effective date, source hash | use in calculation | entitlement guarantee |
| Zoning / rule | `partial` | known value plus named missing field | request evidence | presenting a fully supported formula |
| Zoning / rule | `stale` | source past freshness policy | refresh/review | using stale rule as current |
| Zoning / rule | `conflict` | competing values / sources shown | reconcile conflict | picking the favorable rule silently |
| Document | `scanning` | extraction pending with source preserved | wait / cancel | treating OCR text as verified |
| Document | `verified` | version/date/pages/hash and linked claims | cite/replay | unversioned upload as source of truth |
| Document | `superseded` | prior version retained with successor link | replay history | deleting old decision lineage |
| Document | `corrupt_or_unsupported` | readable reason and request | replace source | fake parsed content |
| Constraint | `clear` | reviewed constraint, scope and evidence named | calculate under stated scope | claiming site is constraint-free |
| Constraint | `possible` | risk / investigation remains | hand off investigation | using as pass/fail conclusion |
| Constraint | `governing` | specific rule/input controls capacity | explain formula | visual bar-only explanation |
| Capacity | `verified` | formula, source IDs, max units, governing constraint | use downstream | legal approval / build guarantee |
| Capacity | `provisional` | missing/assumed input named | request evidence | final purchase ceiling without policy exception |
| Capacity | `abstained` | `MAX UNITS — ABSTAINED` plus reason | resolve blocker | substitute “best guess” number |
| Comps | `included` | rationale, date, distance/market fit, adjustment basis | use in basis | unexplained automated comparable set |
| Comps | `excluded` | exclusion rationale retained | inspect rationale | silently disappearing outlier |
| Purchase ceiling | `supported` | formula inputs + capacity revision + evidence replay | request review | investment recommendation certainty |
| Purchase ceiling | `provisional` | explicit assumption/exception badge | limited scenario compare | primary approval value |
| Purchase ceiling | `unavailable` | dependent blocker named | resolve blocker | blank money tile or zero |
| Grounded LLM | `supported` | claim has adjacent citations and limitation | replay / route claim | open-ended unsupported answer |
| Grounded LLM | `provisional` | claims and unsupported portions distinguished | request evidence | mixing provisional and supported prose |
| Grounded LLM | `abstained` | question + missing evidence + next source | create handoff | hallucinated interpretation |
| Handoff | `draft` | sender composing bounded request | edit/send | invisible work assignment |
| Handoff | `sent` / `acknowledged` | recipient, immutable inputs, expected output, timestamp | monitor/replay | changing inputs without versioning |
| Handoff | `waiting_evidence` | exact evidence request and owner | provide evidence | vague “pending” state |
| Handoff | `requires_review` | package ready for named approver | approve/return | implicit approval |
| Approval | `approved` | approver, gate version, timestamp | advance next gate | legal/municipal approval wording |
| Approval | `returned` | required correction and new owner | address/re-submit | retaining ready badge |
| Approval | `exception_accepted` | exception rationale and approver | continue under exception | hiding unmet exit criterion |
| Evidence replay | `hash_bound` | source → extraction → calculation → claim trace | inspect/copy IDs | mutating historical result |
| Evidence replay | `hash_mismatch` | mismatch blocks reliance | replace/reconcile | showing supported claim |

## Gate transition rules

```text
not_started → in_progress
in_progress → waiting_evidence | ready_for_review | blocked | not_enabled
waiting_evidence → in_progress | blocked | not_enabled
ready_for_review → approved | returned | blocked | exception_accepted
returned → in_progress
approved | exception_accepted → next gate in_progress
blocked | not_enabled → only owner/coverage resolution transitions
```

`approved` refers to an internal gate decision, never a government permit, zoning approval, entitlement approval, or investment recommendation.
