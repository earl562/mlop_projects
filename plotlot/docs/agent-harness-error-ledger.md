# Agent Harness Error Ledger

Last updated: 2026-07-29

This ledger records failures observed while running PlotLot's agent chat against the
ByRight South Florida lead list. A browser symptom is not closed until its root cause
has an automated regression test and a repeated live acceptance run.

## Acceptance Set

| Lead | Expected APN | Live result |
| --- | --- | --- |
| 11925 SW 88th Ct, Miami, FL 33176 | 30-5009-025-0010 | Parcel resolved as `3050090250010`; zoning `EU-1`; ordinance standards blocked |
| 5301 NW 77 CT, Unincorporated, FL 33073 | 474231030160 | Parcel resolved; zoning `RS-4`; ordinance standards blocked |
| 5331 NW 77 CT, Unincorporated, FL 33073 | 474231030130 | Parcel resolved; zoning `RS-4`; ordinance standards blocked |
| 719 9TH ST, West Palm Beach, FL 33401 | 74434316010120080 | Exact official parcel match verified; lot-area contradiction requires review |
| 623 4TH ST, West Palm Beach, FL 33401 | 74434321060170150 | Exact parcel and APN resolved; valuation now blocked without required ordinance and underwriting evidence |

## Regression Ledger

| ID | Symptom | Root cause | Fix and regression coverage | Status |
| --- | --- | --- | --- | --- |
| AH-001 | One prompt ran `run_deal_analysis` twice | Forced grounding result was not represented in the model tool trajectory | Hide tools after a successful full harness run; `test_chat_does_not_repeat_forced_deal_analysis_in_same_turn` | Fixed and live verified |
| AH-002 | A single ordinance lookup launched nationwide Municode discovery and hundreds of requests | Interactive handler called `get_municode_configs()` and repeated resolution inside section extraction | Use targeted authority discovery and pass the resolved config through search and rule extraction; two bounded-discovery tests in `test_harness_runtime.py` | Fixed |
| AH-003 | Harness task remained visually marked running after the answer completed | Forced grounding emitted `tool_use` but no matching `tool_result` | Emit terminal complete/error event for every forced tool call; chat endpoint regression asserts one matched event pair | Fixed and live verified |
| AH-004 | Provider error text reported OpenRouter while isolated tests configured no key or NVIDIA | Chat error helper resolved provider from a different settings instance and treated mock attributes as credentials | Resolve provider from active chat settings and accept only non-empty string credentials; existing API provider-error tests | Fixed |
| AH-005 | Model launched legacy parcel/ordinance tools after the full harness completed | Full harness result was treated as a warm-up rather than the complete analysis trajectory | Full harness completion leaves narration-only synthesis; empty tool set asserted in chat regression | Fixed and live verified |
| AH-006 | Model emitted a fake `analyze_property(...)` call or promised a future call | Completion state was not an explicit final system constraint | Add a final "FULL HARNESS RUN COMPLETE" synthesis contract and forbid function syntax/future tool plans | Fixed; output quality still monitored |
| AH-007 | Model fabricated placeholder evidence IDs such as `evt_abc123` | Narrator output was not validated against the run evidence ledger | Deterministically reject evidence ID tokens absent from session/run evidence and surface an evidence warning; endpoint regression covers rejection | Fixed |
| AH-008 | Failed parcel lookup was narrated as a successful tool run or an unavailable tool | Tool execution success and harness result success were conflated | Preserve failed result status, emit error state, and bypass the model with a deterministic blocked-analysis answer; `test_chat_surfaces_failed_forced_deal_analysis_without_fake_followup` | Fixed |
| AH-009 | Both West Palm Beach leads returned property not found | Palm Beach query normalized `9TH` to `9` and `4TH` to `4`, but the official ArcGIS layer stores ordinal suffixes | Query the raw official street form first, then normalized fallbacks; ordinal regression test plus live exact-APN checks | Fixed; both APNs live verified |
| AH-010 | Chat omitted APN/folio and guessed that an unknown lot source was assessor data | Runtime payload and compact harness context dropped `lot_size_source`, folio, and owner | Preserve fields through adapter, runtime payload, compact context, and active prompt; runtime and bridge tests | Fixed |
| AH-011 | Palm Beach assessor acreage appeared with an unknown source | Palm Beach provider did not classify its official `ACRES` field | Set `lot_size_source=assessor`; Palm Beach provider tests assert the classification | Fixed and live verified |
| AH-012 | 623 4TH ST displayed a `$282,805-$653,589` valuation despite missing official dimensional standards, deterministic capacity, and verified underwriting inputs | A completed evidence-collection run was treated as a completed property evaluation | Add a deterministic evaluation-readiness gate, suppress valuation fields when blocked, bypass model narration, and render the evidence gaps and acquisition plan; readiness, bridge, API, and live browser regressions | Fixed and live verified |
| AH-013 | The analysis console changed a blocked tool result back to complete and retained stale `Running...` labels | The terminal `done` event overwrote the more specific tool outcome and preview rows did not consume the terminal result | Persist the blocked turn outcome through completion, update task/event rows, and render `Needs data` / `Blocked`; desktop and mobile Playwright regression | Fixed and live verified |
| AH-014 | Readiness could pass on authority metadata without dimensional fields, accept completed/unverified/zero-value inputs, or expose blocked valuation artifacts through an ordinary tool call | The first readiness predicate checked stage labels instead of cited input completeness, and only compact chat context was redacted | Require cited dimensional values, verification-clean mode-specific positive underwriting inputs, fail closed on missing live readiness, and return an evidence-safe blocked payload; direct negative regressions cover every bypass | Fixed |
| AH-015 | Parallel harness/tool tests produced a 19 MB trace ledger containing concatenated JSON snapshots, causing unrelated tool calls to fail validation | Tool-call persistence used an unlocked in-place read/modify/write cycle across the live server and test processes | Add cross-process file locking, atomic replacement, concurrent-write regression, and conservative recovery for concatenated complete snapshots; preserve the malformed local file as forensic evidence | Fixed |
| AH-016 | A deterministic verification run reported failures from the caller's database hostname and from live ArcGIS/seeded-database checks even though unit behavior was correct | One health test inherited `DATABASE_URL`, while three integration modules documented live dependencies but did not enforce the existing `PLOTLOT_LIVE_TESTS=1` opt-in | Isolate the health test settings and gate seeded-database and county-network modules behind the explicit live-test lane; targeted provider tests remain deterministic | Fixed |
| AH-017 | The documented dimensional-standard seed command could downgrade verified Fort Lauderdale rows and fail to mark Miami/Hollywood assumptions as staged | Every seed row omitted `verification_status`, so the typed default `unverified` was persisted regardless of the source boundary described by the script | Assign `VERIFIED` only to ordinance-backed Fort Lauderdale rows and `STAGED` to assumption-grade rows; unit provenance regression plus seeded-DB functional checks | Fixed |
| AH-018 | Live ArcGIS discovery crashed on one Miami-Dade service and the universal provider returned no parcel for all three target South Florida counties | The crawler assumed every layer's `fields` value was iterable, and the generic provider rediscovered datasets before consulting already-registered authoritative county adapters | Reject malformed layer schemas at the parser boundary and route known counties through their dedicated official providers before generic discovery; unit regressions plus opt-in county live checks | Fixed |
| AH-019 | The REST harness exposed request and calculator types for NOI valuation but returned 404 for the corresponding deterministic calculation | The API adapter imported `run_noi_valuation` and defined `NoiValuationCalculationRequest` without registering a route | Add `/api/v1/deal-analysis/noi-valuation` with the shared persistence path and an HTTP regression that verifies formula outputs | Fixed |
| AH-020 | The unit suite stalled while comp tests made live Miami-Dade property-detail requests | Comp tests mocked sales discovery and search but not the automatic county enrichment step | Make Miami-Dade enrichment an explicit offline passthrough for this unit module; targeted comp regression completes without network access | Fixed |
| AH-021 | MLflow emitted duplicate `trace_info` inserts, and a trace-finalization exception could execute the decorated agent action a second time | Async SQL trace export was enabled by default, the wrapper retried the underlying function after telemetry exceptions, and the shared span context manager ignored the tracing opt-in flag | Disable MLflow span export by default, make every span path honor the same opt-in flag, and own span lifecycles so telemetry failure cannot rerun application work; exactly-once and disabled-span regressions plus a clean live database log | Fixed and live verified |
| AH-022 | A completed harness tool returned evidence IDs while the persisted Evidence Library was empty, and document generation was not exercised through its approval boundary | The full-harness adapter returned before shared persistence, dropped analysis/tool-run linkage, and the lifecycle test assumed governed document generation completed immediately | Route full and legacy outputs through shared persistence, preserve lifecycle context IDs, and require approval plus replay in the database-backed Playwright lifecycle | Fixed and live verified |
| AH-023 | The public homepage emitted repeated image 404s in desktop and mobile visual tests | The page and manifest still referenced 24 historical product assets that had been removed, while the repository hygiene checker documented but did not apply its canonical public-assets exception | Restore the exact historical assets and enforce the public-assets exception with a focused hygiene regression; desktop and mobile Playwright visual coverage | Fixed and live verified |
| AH-024 | Three unit tests attempted the developer's default PostgreSQL connection after durable tool persistence was added | Router-parity tests did not apply their in-memory session boundary, and evidence-by-ID did not fall back to the replay ledger when the durable database was explicitly unavailable | Apply the existing fake-session boundary to router unit tests and use the replay ledger only for typed database connection failures; targeted regressions preserve real database coverage in Playwright | Fixed |

## Open Defects And Accepted Blocks

| ID | Condition | Required next action | Release effect |
| --- | --- | --- | --- |
| AH-O01 | Miami-Dade `EU-1`, Broward `RS-4`, and West Palm Beach `NWD-R` dimensional standards are not reliably indexed | Add authoritative ordinance adapters/ingestion and golden field expectations | Blocks firm unit count, FAR, setbacks, height, and supported offer |
| AH-O02 | Targeted Municode state-client request currently receives HTTP 429 | Add cache/backoff and alternate official publisher routing; keep no-results explicit | Warning only when indexed official ordinance evidence exists; otherwise blocks zoning claims |
| AH-O03 | 719 9TH ST has a lot-area conflict: the ByRight fixture records 6,750 sqft while the current official Palm Beach GIS response records about 7,375 sqft | Preserve both values as contradictory evidence, determine effective/source dates, and add a golden contradiction case before using lot area in capacity math | Blocks firm capacity and valuation for this lead |
| AH-O04 | Alembic has duplicate `007` and `008` revisions and multiple heads | Repair the migration graph in an isolated migration change with upgrade-from-empty and upgrade-from-prior tests | Blocks production migration readiness; local `Base.metadata.create_all` is not a substitute |
| AH-O05 | Mobile Playwright capture shows the Next.js development button near the composer | Verify production build removes it; otherwise reserve composer space | Development-only visual warning until production-build capture |
| AH-O06 | Evidence token validator recognizes `ev_` and `evt_` IDs only | Move validation to structured citation objects and final response schema | Residual unsupported-citation risk |
| AH-O07 | Playwright runs attached to the existing dev server can stall; Next build and dev/Playwright also corrupt each other's `.next` output when run concurrently | Use isolated ephemeral Playwright ports and sequence production builds after all dev-server browser runs; add server-readiness diagnostics | Test-infrastructure reliability risk; does not alter production evidence |
| AH-O08 | The explicit `run_deal_analysis` acceptance prompt is labeled `document generation` in the visible intent trace | Prioritize explicit tool/analysis-type commands before generic document-language classification and add an intent regression | Misleading trace/UI label; forced harness routing still executes correctly |
| AH-O09 | Evidence IDs from a live run use a `run_fixture_...` run prefix | Generate source-neutral run IDs and keep fixture/live provenance in typed source-mode metadata | Provenance naming is misleading even though the evidence records are marked live |

## Required Closure Evidence

Every ledger item must include:

1. A deterministic unit or integration regression.
2. A browser acceptance rerun using a real lead when the defect is user-visible.
3. A screenshot or trace for visual/trajectory defects.
4. Exact source and evidence IDs for trust-critical lookup fixes.
5. Before/after behavior and any remaining warning condition.

No open item may be silently reclassified as complete because the model produced a
plausible answer. Unknown and blocked fields remain unknown and blocked.
