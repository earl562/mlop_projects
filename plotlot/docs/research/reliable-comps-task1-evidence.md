# Reliable comps Task 1 evidence

Date: 2026-09-04

Scope: the frozen comparable-sale input contract, JSON-safe qualification output contract,
deterministic qualification rules, transaction reconciliation, and unit tests. No network,
credentialed, paid-provider, commit, push, external API, or frontend operation was performed
as part of Task 1; adjacent in-process adapter/runtime/API tests were included in verification.

## Published contract

The public import surface is `plotlot.comps`:

- `SaleEvidence`, `CompSubject`, and `CompPolicy` are frozen Pydantic models with unknown
  fields forbidden.
- `CompDecision` and `CompSetResult` are frozen, slotted dataclasses. Their complete object
  graph contains only JSON-safe scalars, tuples, and `None`; no `date` or `datetime` objects
  cross the output boundary.
- `qualify_comps(subject, candidates, policy)` returns a `CompSetResult`.
- Result statuses are `qualified` and `insufficient_evidence`.
- Insufficient evidence always produces null `value_low`, `value_median`, and `value_high`.
- Value bases are `price_per_acre`, `price_per_unit`, or the empty string for an unsupported
  category.
- Policy version is `reliable-comps-v1`.

`CompDecision` retains the complete candidate ledger: evidence and parcel identifiers,
jurisdiction and address, sale fields, date precision, coordinates, size and units, property
type and category, source qualification and provenance, review attestation, construction
completion evidence, comparability attributes, calculated distance, rejection reasons, and
the accepted flag.

## Red-to-green history

The implementation followed a failing-test-first cycle. Representative observed red states:

1. `uv run pytest tests/unit/test_comp_qualification_contract.py -q` initially failed during
   collection because `plotlot.comps` did not exist, then failed the callable export assertion
   before `qualify_comps` was implemented.
2. `uv run pytest tests/unit/test_comp_qualification_land.py -q` initially returned
   `insufficient_evidence` for the three-sale land happy path before land qualification and
   valuation were implemented.
3. `uv run pytest tests/unit/test_comp_qualification_rejections.py -q` initially had no
   rejected-candidate ledger. Subsequent targeted red cases exposed and drove fixes for:
   all-party conflicting-transaction rejection, duplicate evidence identifiers, repeated
   transfers of one parcel, whitespace parcel identifiers, derived-value overflow, strict
   review attestation, review after a historical valuation date, date-range boundaries, and
   construction completion after sale.
4. The exhaustive literal-state refactor produced one final red result:
   `assert_never('disqualified')`. The model's unchanged `disqualified` enum member was added
   to the explicit rejection branch and the full suite returned green.
5. Independent review reproduced a connected-identity bypass. The new
   `test_conflict_connected_by_source_record_blocks_different_document_aliases` initially
   returned `qualified` instead of `insufficient_evidence`; unioning every available
   transaction identity made the connected conflicting group fail closed.
6. The new `test_explicit_gift_qualification_code_cannot_be_marked_as_qualified` initially
   raised `IndexError` because the contradictory gift row was accepted. An exact typed
   source-code guard now returns `non_market_transfer` without keyword matching arbitrary
   classification prose.
7. The new `test_radius_gate_uses_full_precision_before_rounding_display_distance` initially
   raised `IndexError` because a true 3.0000004-mile candidate was accepted after premature
   rounding. Eligibility and selection now use full precision; only the output is rounded.

The final focused command was:

```text
uv run pytest tests/unit/test_comp_qualification_contract.py \
  tests/unit/test_comp_qualification_finished.py \
  tests/unit/test_comp_qualification_land.py \
  tests/unit/test_comp_qualification_reconciliation.py \
  tests/unit/test_comp_qualification_rejections.py -q
```

Result: `73 passed in 0.35s`.

## Qualification evidence covered

- Policy requires 3-50 independent comps, maximum at least minimum, radius greater than zero
  and no more than three miles, a 1-120 month window, and a canonical `YYYY-MM-DD` valuation
  date. The library intentionally does not compare valuation dates with the wall clock so
  historical and deterministic replay remain possible; the public API rejects future request
  dates at its boundary.
- Sale prices, coordinates, parcel/building sizes, units, radius, and tolerance reject invalid
  bounds and non-finite values. Derived values are also checked so finite inputs cannot emit
  an infinite per-acre or per-unit result.
- Day and month evidence preserve precision. Missing, invalid, unknown, future, expired, or
  boundary-straddling sale dates reject deterministically.
- County qualification is necessary provenance, not proof of comparability. Category,
  property type, distance, size, zoning, neighborhood, waterfront, subject identity, and
  relevant target attributes are evaluated independently.
- County, recorder, and user-reviewed sources have distinct provenance rules. Listing and
  unknown sources never establish a closed transaction. User review requires a real source
  reference, classification basis, reviewer, and parseable review time. Review can occur
  after the historical valuation date because it attests provenance rather than sale recency.
- New-construction evidence requires a canonical completion day and source, and completion
  must precede the sale.
- Candidates sharing an evidence identifier are all rejected. Candidates that refer to the
  same documented transaction are connected through every available recorded-document and
  source-record identity and are all rejected when their material transaction facts conflict.
  Local source-record identifiers are namespaced by source kind and URL to avoid false
  collisions. Exact duplicates retain one deterministic source-priority representative.
  Distinct transfers are not conflated, but only the latest otherwise-qualified transfer per
  parcel/category is eligible, so multiple sales of one property cannot satisfy the
  independent-comp minimum.
- `qualification` remains the normalized market determination supplied by an official adapter
  or explicit human review. County-specific raw codes must be mapped there. The core adds only
  an exact, case-insensitive `gift` qualification-code contradiction guard; it does not guess
  transfer meaning from free-text `classification_basis` content.
- Selection is deterministic and bounded by `max_comps`, while the complete accepted/rejected
  candidate ledger remains visible. Radius comparisons and selection use full-precision
  distance while the retained display value is rounded to six decimal places.

## Broader verification

The adjacent qualification, county adapter, import, runtime, API, cache, tool guard, and
document guard suites ran together:

```text
uv run pytest tests/unit/test_comp_document_guards.py \
  tests/unit/test_comp_qualification_contract.py \
  tests/unit/test_comp_qualification_finished.py \
  tests/unit/test_comp_qualification_land.py \
  tests/unit/test_comp_qualification_reconciliation.py \
  tests/unit/test_comp_qualification_rejections.py \
  tests/unit/test_comp_tool_guards.py tests/unit/test_comps.py \
  tests/unit/test_comps_field_mapping.py tests/unit/test_comps_rentcast.py \
  tests/unit/test_comps_sources_south_fl.py tests/unit/test_county_comp_arcgis.py \
  tests/unit/test_county_comp_broward.py tests/unit/test_county_comp_miami_dade.py \
  tests/unit/test_county_comp_palm_beach.py tests/unit/test_county_comp_sources.py \
  tests/unit/test_deal_paper_comp_guards.py tests/unit/test_florida_comp_import.py \
  tests/unit/test_florida_comp_import_cli.py tests/unit/test_reliable_comps_analysis.py \
  tests/unit/test_reliable_comps_api.py tests/unit/test_reliable_comps_cache.py \
  tests/unit/test_reliable_comps_runtime.py -q
```

Result: `285 passed in 2.12s`, with 12 deprecation warnings from legacy document helper tests.

Additional final checks:

- Ruff: all checks passed for the six owned source files and five Task 1 test files.
- Mypy: success, no issues in the six owned source files.
- Programming no-excuse checker: no violations in eleven files.
- `git diff --check`: passed for the owned scope.
- All six source modules are under 250 pure lines; no owned function has more than three
  parameters.
- A public-interface driver produced a qualified three-sale land result, a finite median,
  and passed `json.dumps(asdict(result), allow_nan=False)`.
- A post-review public-interface driver independently exercised connected transaction
  conflict, explicit gift rejection, and the full-precision radius boundary. It printed:
  `{'connected_conflict': 'insufficient_evidence', 'gift': 'non_market_transfer',
  'radius': 'outside_radius', 'display_miles': 3.0}`.

## Files

- `src/plotlot/comps/__init__.py`
- `src/plotlot/comps/models.py`
- `src/plotlot/comps/dates.py`
- `src/plotlot/comps/qualification_rules.py`
- `src/plotlot/comps/reconciliation.py`
- `src/plotlot/comps/qualification.py`
- `tests/unit/test_comp_qualification_contract.py`
- `tests/unit/test_comp_qualification_finished.py`
- `tests/unit/test_comp_qualification_land.py`
- `tests/unit/test_comp_qualification_reconciliation.py`
- `tests/unit/test_comp_qualification_rejections.py`
- `docs/research/reliable-comps-task1-evidence.md`

## Remaining boundary

`basedpyright` diagnostics were unavailable because that language server is not installed and
installation was previously declined; Mypy provided the final static type check. This work
does not claim live county-source correctness, deployment verification, or external-provider
availability. Independent review is owned by the root task. Concurrent unrelated worktree
changes were preserved. `qualification_rules.py` is in the 200-250 pure-line warning band at
222 lines; its next substantive expansion should split source provenance from comparability
rules rather than add more responsibilities. `test_comp_qualification_land.py` is also in the
warning band at 228 pure lines; its next expansion should move date/value behavior into a
separate test module.

## GitHub checkpoint verification, September 7, 2026

The user subsequently authorized regular verified commits and pushes to `origin/cpt-pro`.
This checkpoint contains only the six standalone core modules, their five direct test
files, and this receipt. The broader adapter/runtime/API checks above are historical
working-tree evidence, not a claim those adjacent changes are included in this commit.
The later `apply_source_completeness` helper remains uncommitted with its separate
pipeline integration and tests; its working-tree contents were preserved.

The staged index was exported into a fresh directory, with `PYTHONPATH` explicitly
pointing to that export. The imported `plotlot.comps` path was checked to ensure the
dirty editable checkout was not supplying uncommitted dependencies. The tested index
tree was `4ce7058d7604315b8e7f943a1a12b920a8a5ebc5`; this receipt was appended afterward.
The existing Python 3.12 environment was reused without installing dependencies.

Fresh checkpoint results:

- Focused core tests: 73 passed before four test files received formatting-only changes.
- Final exported backend unit suite: **1,976 passed**, one existing Starlette/httpx
  deprecation warning, in 13.49 seconds. This includes all 73 core tests.
- Full exported backend Ruff lint passed; formatting check reported 453 files already
  formatted. Full source Mypy exited successfully with informational untyped-body notes.
- Public-library manual check: three synthetic sales qualified with median 200,000;
  two sales returned insufficient evidence with null valuation; strict JSON serialization
  passed. Synthetic examples establish behavior, not actual property values.
- Repository hygiene, staged whitespace, manual diff review and a limited staged
  credential-pattern scan passed. No credentials, generated diagnostics or unrelated
  production changes were staged.

The first full-suite attempt had one health-test failure because the verification
command supplied database host `127.0.0.1` while the existing test and CI expect
`localhost`. Repeating against the same exported code with `localhost:59999` passed;
no source code or test assertion was changed to resolve that environment mismatch.
No live database or model provider was needed for these checks.

Local XML receipts are retained under `/tmp/plotlot-checkpoint-20260907.RAsdJ7/`:
`comp-core.xml`, `full-unit.xml` (initial environment mismatch), and
`full-unit-localhost.xml` (final passing run). This is a core-library checkpoint,
not a whole-application build, live county-source, GitHub CI, or production approval.
