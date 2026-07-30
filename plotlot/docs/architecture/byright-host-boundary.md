# PlotLot v2 / ByRight host boundary

**Status:** Accepted product-host baseline

PlotLot v2 is the sole canonical product host for this product. It owns product navigation,
Clerk edge authentication, workspace/project/site/analysis/analysis-run lifecycle, operator and
customer interfaces, queues, and report views.

## Migration compatibility guard

The historical PlotLot tree contained two different migration bodies labeled
`007` and two labeled `008`. The repaired graph assigns unique revisions and
has one head, but an existing database that reports legacy `007` or `008`
cannot reveal which body actually ran. Automatic upgrade must stop for a
manual schema audit; operators must compare the live schema with both legacy
bodies and explicitly stamp the proven revision before continuing. Never infer
or guess the applied body from the version string alone.

ByRight is the governed land-intelligence engine. It owns correct-or-abstain retrieval, evidence
and comp adjudication, deterministic calculations, governance, review/release semantics, and
replay. ByRight is consumed behind one versioned PlotLot adapter; it does not own a product
frontend, a second login, or a competing workspace/project/site/analysis model.

PlotLot Pydantic models and emitted OpenAPI are the canonical transport source. Frontend transport
types must be generated from that document with a pinned generator. Neither repository may
hand-maintain a second transport schema or infer lifecycle identifiers and statuses.

The baseline preserves the reviewed dirty PlotLot product state without changing the original
checkout. It does not declare every preserved behavior correct. Later tasks replace decision-driving
facts and calculations through the ByRight adapter while retaining PlotLot ownership of the host.

## Iterative validation lanes

Validation advances through `preflight -> offline contract -> database integration -> public
GIS/geocode -> live search/provider -> RentCast comps -> PlotLot browser E2E`. A failure is fixed and
rerun from its first failing boundary before the complete regression is repeated.

Task 53 requires the credential-free host baseline. Credential-backed lanes run only when the
runtime environment-readiness contract reports `READY`; no environment file is copied, sourced,
committed, archived, or printed.
