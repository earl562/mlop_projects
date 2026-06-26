# Spec — Zoning Feasibility Harness

**Status:** Phase 0 specification (the first paid feature slice contract).
**Master spec ref:** §4 (First Paid Feature Slice), §10 (Harness Run Service),
§11 (Context Engineering), §12 (Report Builder Spec), §15 (API Endpoint Spec).

## 1. Goal

The first production feature: **South Florida Zoning Feasibility Memo.**

Given a South Florida address or parcel + intended development use, produce a
cited zoning feasibility memo for a land developer. The memo answers:

- What jurisdiction governs the site?
- What zoning district applies?
- What code / land-development source supports that?
- Is the intended use permitted, conditional, prohibited, or unknown?
- What dimensional standards apply?
- What density / FAR / height / setback / parking constraints apply?
- What overlays or entitlement risks are known?
- What facts are missing or require municipal confirmation?
- What are the next due-diligence actions?
- What source citations and evidence IDs support every material claim?

**No material zoning, entitlement, or development claim may be generated
without a recorded evidence item.** Unknowns are explicit ("unknown / requires
verification"), never guessed.

## 2. Run API

```
POST /api/v1/harness/runs
GET  /api/v1/harness/runs/{run_id}
GET  /api/v1/harness/runs/{run_id}/events
POST /api/v1/harness/runs/{run_id}/cancel
POST /api/v1/harness/runs/{run_id}/approve
```

### Request (POST /api/v1/harness/runs)
```json
{
  "workspace_id": "...",
  "project_id": "...",
  "site": { "address": "...", "parcel_id": null },
  "skill_name": "zoning_feasibility_memo",
  "intended_use": "multifamily | townhomes | self-storage | warehouse | industrial | retail | data-center | mixed-use | other",
  "assumptions": {}
}
```

### Response shape
```json
{
  "analysis_run_id": "...",
  "status": "completed | failed | needs_review",
  "site_summary": {...},
  "zoning_summary": {...},
  "use_permission": {...},
  "dimensional_standards": {...},
  "parking_requirements": {...},
  "entitlement_path": {...},
  "risks": [...],
  "unknowns": [...],
  "recommendation": {...},
  "report_id": "...",
  "evidence_ids": [...]
}
```

## 3. Run service behavior (deterministic enough to replay)

1. Authenticate user.
2. Validate workspace membership.
3. Check billing entitlement (Phase 8).
4. Create Site if needed; Create Analysis if needed; Create AnalysisRun.
5. Emit `run_started`.
6. ContextBroker builds bounded context (§11 layers).
7. Run skill (`zoning_feasibility_memo`) with GLM5.2 / configured model.
8. Route **all** tool calls through `HarnessRuntime` (one execution path).
9. Persist ToolRun / EvidenceItem / ModelRun / Event.
10. Generate report from evidence IDs via `EvidenceReportBuilder`.
11. Validate report claims (reject uncited material claims).
12. Emit `run_completed` or `run_failed`.

## 4. Context engineering (ContextBroker)

Output layers:
1. System policy and domain role
2. Workspace/project/site summary
3. Current task and user assumptions
4. Top evidence IDs + snippets (prefer IDs over long excerpts)
5. Tool affordance summary
6. Prior run reflections / reviewer notes
7. Unknowns and missing-data warnings
8. Citation requirements

Rules: external source text labeled as source text; source text may not grant
tool permissions; separate facts from assumptions; include unknowns explicitly;
bounded + deterministic.

## 5. Report builder (EvidenceReportBuilder)

Report sections:
1. Executive feasibility summary
2. Site and parcel facts
3. Jurisdiction and zoning district
4. Intended use analysis
5. Dimensional standards
6. Parking/loading/access requirements
7. Entitlement path
8. Overlays and risk flags
9. Unknowns requiring confirmation
10. Recommended next actions
11. Source appendix

### Material claim shape
```json
{
  "key": "...",
  "text": "...",
  "material": true,
  "evidence_ids": ["ev_..."],
  "confidence": "high | medium | low | unknown",
  "needs_verification": true
}
```

### Validation rules
- Reject material claims without `evidence_ids`.
- Reject `evidence_ids` not in the run/project/site scope.
- Warn on stale evidence (freshness).
- Add legal caveat for ordinance sources.
- Add unknowns rather than guessing.

## 6. Tool contracts (via HarnessRuntime — one path)

All tools registered in `tool_registry.py`, invoked through `default_runtime.py`.
Existing primitives: `HarnessRuntime`, `HarnessPolicyEngine`, `get_tool_contract`,
`list_tool_contracts`, `tool_risk_class`. Risk classes: READ_ONLY,
EXPENSIVE_READ, WRITE_INTERNAL, WRITE_EXTERNAL. See master spec §9 for the
full required tool list.

## 7. Acceptance (this feature slice)

- Existing lookup/chat behavior not broken.
- All production tool calls go through HarnessRuntime.
- Server authors ToolContext (client/model cannot set `actor_user_id`,
  `approved_approval_ids`, `live_network_allowed`).
- Reports reject uncited material claims.
- External writes require approval.
- System says "unknown / needs verification" instead of guessing.

## 8. Definition of Done (Phase 0 — this spec)

- [x] Run API contract defined
- [x] Report builder contract defined
- [x] Context layers defined
- [x] Validation rules defined
- [ ] BDD scenarios reference this contract
