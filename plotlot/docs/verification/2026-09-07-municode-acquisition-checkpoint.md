# Municode acquisition safety checkpoint

This checkpoint prevents a failed or ambiguous Municode acquisition from being
accepted as a successful chapter import. It is not a release approval or proof
that a municipality's configured source is its current, applicable zoning code.

## Scope and review binding

Base commit: `b1cf3c4c34bc211f34f9b6307af9e5670e9f6641`.
Verified and independently reviewed source/test tree:
`ef7fa0da8790597f52f1b1e46168e0ad5cd6e72f`.
This note is the only addition after that reviewed seven-file tree.

- Nonempty `Docs` responses must contain exactly one requested document ID.
  Missing, duplicate or malformed document evidence is rejected.
- Failed or empty expected leaves and depth-truncated traversals stop chapter
  acquisition; successful siblings are not returned as a complete import.
- Outstanding TOC and leaf tasks are cancelled and awaited before the shared
  HTTP client closes, including when the caller cancels the chapter.
- The shared SDK preserves existing HTTP exception types. Live search retains
  its empty/skip behavior on unavailable or invalid evidence.
- The on-demand coordinator emits terminal `incomplete_source` for typed source
  failures before embedding or storage. Only its two error handlers are included;
  unrelated embedding, adapter and database changes remain outside this commit.

## Executed checks

Checks ran against an isolated export of the staged tree, not the mixed working
tree. Python 3.12 used explicit `PYTHONPATH` to that export, a task-owned temporary
directory and a non-serving localhost database test URL. No credentials were
copied into the export and no production database or paid model was called.

| Check | Observed result |
| --- | --- |
| Original acquisition/identity regressions against base | 11 failed, 5 passed |
| Review regressions against initial candidate | 9 failed, 2 passed |
| Final focused acquisition, identity, failure and live-service tests | 30 passed |
| Full backend unit suite | 2,003 passed; one existing Starlette deprecation warning |
| Ruff lint and formatting | Passed; 457 files already formatted |
| Scoped mypy | Passed for all seven changed Python files |
| Independent read-only re-review | APPROVE; no critical, high or medium findings |

Review caught and this checkpoint corrected two intermediate defects: changing
the shared SDK's HTTP exception contract broke live-search degradation, and
fail-fast gathering left sibling requests alive after terminal failure. Fresh
wire-level regressions cover HTTP 503, transport timeout, identity mismatch,
duplicate identity and task cleanup for both TOC and leaf requests.

Manual SDK/adapter/coordinator checks used four owned loopback HTTP servers.
Unique requested documents in either response order preserved section A content.
Missing and duplicate requested IDs emitted terminal `incomplete_source`, with
zero model and database calls. All owned servers stopped. The earlier baseline
wrong-document case reached the embedding tripwire; the corrected case does not.

A fresh read-only [public Municode response](https://api.municode.com/CodesContent?jobId=488330&productId=10933&nodeId=PTIITHCO_CH62PLZO_ARTIINGE_S62-1OAREWHTEZOMA)
returned 834 HTML characters for the requested node. SHA-256:
`3dc877641fdca492725c8bd67d197ec956a8a5acea46a88c52ec40bf69ca5866`.
This establishes response compatibility only, not current Miami zoning authority.

## Remaining boundaries

Legacy empty-`Docs` `Document`/`document` content remains supported and does not
provide document-ID proof. Source currency, full inventory coverage, city-designated
routing, land-use applicability and exact live-search citation URLs are not solved
by this checkpoint. General Miami code must not be presented as verified Miami21.

The existing coordinator is still oversized (285 nonblank/noncomment lines;
258 at base). The review recorded this as low-priority structural debt; this
checkpoint intentionally keeps its changes at the acquisition error boundary.

There are no frontend, sign-in, deployment or database-schema changes here.
The broader launch remains incomplete. GitHub release-pair configuration is a
separate known CI blocker; passing application checks does not waive that gate.
