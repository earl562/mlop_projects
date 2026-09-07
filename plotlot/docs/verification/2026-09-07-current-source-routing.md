# Current city zoning routes: live verification

Checked September 7, 2026 on `cpt-pro`, base commit
`0673ac844faf26e73bf1a0998aa069c5b785aa12`, using the existing Python 3.12.13
environment. This is an investigation checkpoint, not an implemented repair or
production-readiness assessment. The worktree contains unpublished changes;
the adapter and test observations below describe that worktree, not just HEAD.

## Reproduced routing gap

Calling the actual `resolve_adapter` with a 60-second per-city deadline produced:

| Municipality / state | Observed result |
| --- | --- |
| West Palm Beach / FL | `NoAdapterError` |
| Miami / FL | `MunicodeAdapter`: product `10933`, job `488330`, node `PTIITHCO_CH62PLZO` |

The [official West Palm Beach Planning Division](https://www.wpb.org/Departments/Development-Services/Planning-Division)
was checked again and links its zoning regulations to EncodePlus. The City's
link selects Article I (`202`); the publisher's Chapter 94 root is `201`.
Miami's returned general-code node does not itself prove acquisition of Miami 21.
Miami publisher access/currentness was not re-audited in this pass.

## Aggregate Chapter 94 response

A bounded, unauthenticated GET of the publisher's
[Chapter 94 content endpoint](https://online.encodeplus.com/regs/westpalmbeach-fl/doc-view.aspx?ajax=0&secid=201)
returned HTTP 200, **5,128,604 bytes**. SHA-256 of that exact response:
`9236b9b79bdcc66e5de3ee21d02aeae90365fd29302de797d709fc3bd3d68c1c`.

Observed structure:

- `#thePage` identifies `secid=201`, `tocid=002`.
- 1,244 `section[data-secid]` elements, 1,244 distinct IDs and hierarchy paths.
- These sections are DOM siblings, not nested section elements. CSS path tokens
  encode their hierarchy. Every non-root path's immediate parent exists in this
  response.
- Mini-contents links name 301 distinct IDs, all present in the body. Another
  943 body IDs are not named by those links. Mini-contents alone is not a complete
  manifest.
- Section `429` is the FWD provision, with its own table. Definition `902` and
  amendment-table section `1390` are also present.
- 173 image elements occur inside `#thePage`. Image content, diagram meaning,
  and image availability were not verified.

These are counts of one publisher response, not proof of exhaustive municipal
coverage, effective law, codification currency, or applicability to a parcel.
They extend the earlier broad-contents observations: that navigation view was
not an exhaustive list of the content available in the aggregate response.

## Generic HTML adapter is not sufficient

The existing `HTMLAdapter` was driven through its real `fetch_chunks()` method
against that same public chapter URL, with a 90-second overall deadline and no
embedding/storage calls. It returned:

| Measurement | Value |
| --- | ---: |
| Text chunks | 2,207 |
| Distinct source node IDs | 1 |
| Distinct source URLs | 1 |

The one ID is the adapter's URL-derived `html_` identifier. Sample chunks
mentioning FWD carry the Chapter 94 heading, an empty section number, the chapter
URL, and chapter-wide zone/cross-reference metadata. Consequently, adding this
URL to the generic adapter would retrieve text but would not preserve the
publisher's individual section identities or exact section citations.

This is an unsupported use of a per-page adapter, not evidence that an already
registered EncodePlus adapter is broken: no EncodePlus adapter is registered.

## Integration implications

Code inspection and an independent read-only caller audit agree:

- `ingestion/adapters/registry.py` is used by on-demand acquisition.
- `pipeline/ingest.py::_resolve_config` independently resolves Municode configs.
- `land_use/ordinances/service.py` and `harness/default_runtime.py` independently
  resolve Municode for live search.
- The existing authority registry is not the shared routing decision for these
  paths, and `SourceAdapter.fetch_chunks()` returns a bare chunk list without a
  coverage/currentness result.

An adapter registration by itself would leave bypass paths in place. The next
design decision is a shared city-designated source policy plus attributable
source snapshots, keeping authority, acquisition completeness, currency and
parcel applicability distinct. This change is not implemented by this note.

## Verification and boundaries

`pytest tests/unit/test_adapters.py tests/unit/test_municode_document_identity.py -q`
finished with **90 passed in 0.48s** in the current worktree. Those tests do not
cover the missing publisher integration; a passing result does not resolve the
live routing failures above.

The current worktree passes Ruff lint. Its formatting check reports 14 existing
files requiring formatting; none was edited in this investigation. The checkpoint
contains this evidence note only. Its isolated staged snapshot passes Ruff lint
and formatting checks (453 files already formatted), independently of unpublished
work. The archive operation reported a host locale warning; the checks exited 0.

No model requests, paid API calls, database changes, authentication changes,
dependency installations, deployments or production source replacements were
made. No live service was started or stopped. The public raw-response artifact
is local evidence, deliberately excluded from GitHub; this note retains its
source URL, hash and observed contracts. Existing unrelated work remains intact.
