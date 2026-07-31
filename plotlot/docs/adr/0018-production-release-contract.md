# ADR 0018: Production release contract

- Status: Accepted
- Date: 2026-07-26
- Owners: Platform Operations and Release Management

## Context

PlotLot needs one production architecture contract before tenancy, persistence,
integration, and staging work can rely on deployment assumptions. Existing
Railway and free-Render descriptors remain useful for local development and
historical reference, but they do not define an acceptable production target.

This ADR defines the production target. The machine-readable source is
`artifacts/release/manifests/production-architecture.json`; its JSON Schema is
`artifacts/release/release-manifest.schema.json`. A candidate is not releasable
until `scripts/release/validate_manifest.py` accepts its signed manifest.

## Decision

### Canonical topology

- The customer-facing Next.js frontend runs on paid Vercel with public HTTPS.
- PlotLot API, PlotLot worker, ByRight API, and ByRight worker run on paid
  Render services. Only the PlotLot API has public ingress; workers and ByRight
  are private services.
- Every Render hop requires TLS. Each service presents an Ed25519 service
  assertion with schema version, audience, issuer, key ID, owned signing key,
  signed-payload SHA-256, base64url signature, issued-at time, and an expiry no
  more than five minutes later.
- Neon PostgreSQL is private and uses `verify-full` TLS. PlotLot uses the
  `plotlot` schema through `plotlot_app`; ByRight uses the `byright` schema
  through `byright_engine`. Sharing either application role is forbidden.
- Immutable evidence is held in private S3-compatible storage with TLS,
  encryption, and object lock. The encryption key has a named owner.

The manifest binds the Vercel deployment ID, each service image digest, the
database migration head and schema hash, and the PlotLot/ByRight OpenAPI hash.
The PlotLot producer hash and ByRight consumer expectation must match.

### Security and ownership

All database credentials, service-assertion keys, and evidence-encryption keys
have named owners and rotation intervals. Release manifests are signed with
Ed25519 by Release Management. Unsigned candidates are never production
releases.

### Data governance

Every retained class records:

- classification;
- contractual, licensed, or legal rights basis;
- positive retention duration; and
- deletion owner.

Customer-confidential and licensed-source records remain access controlled.
Released evidence is immutable for its declared retention period; deletion is
performed only by the named owner under the applicable policy.

### Recovery and service levels

Neon backup and point-in-time recovery are mandatory. Platform Operations owns
restore. Production releases require RPO at most 15 minutes and RTO at most
4 hours.

The private-beta SLOs are:

- 99.5% monthly availability;
- first event p95 at most 2 seconds;
- queue start p95 at most 10 seconds; and
- terminal analysis p95 at most 120 seconds and p99 at most 180 seconds at
  concurrency two.

Compliance owns evidence durability. The Incident Commander owns incidents;
the Release Manager owns rollback to the previous signed manifest.

### Customer operations

Private-beta entitlement is manual and owned by the Workspace Admin. A
dedicated customer deployment is a paid setup using the same image digests,
database schema, and contracts as the shared deployment. Customer code forks
are forbidden.

### Validator policy codes

The validator fails closed and emits these stable policy codes:

| Policy code | Rejected condition |
| --- | --- |
| `PROD_FREE_PLAN` | Free frontend or service plan |
| `DATABASE_PUBLIC` | Public database network access |
| `TLS_REQUIRED` | Missing frontend HTTPS or service/database/object-store TLS |
| `SECRET_OWNER_REQUIRED` | Unowned secret, assertion key, or storage key |
| `DATABASE_ROLE_ISOLATION` | Reused database application role |
| `BACKUP_PITR_REQUIRED` | Backup, PITR, or restore owner absent |
| `RPO_BREACH` | RPO exceeds 15 minutes |
| `RTO_BREACH` | RTO exceeds 4 hours |
| `RETENTION_POLICY_REQUIRED` | Retention is missing or non-positive |
| `CONTRACT_HASH_MISMATCH` | PlotLot and ByRight OpenAPI hashes differ |
| `CUSTOMER_CODE_FORK_FORBIDDEN` | Dedicated deployment enables a code fork |
| `RELEASE_SIGNATURE_REQUIRED` | Release signature fields are absent |
| `SERVICE_ASSERTION_UNSIGNED` | A service assertion omits its signature |
| `SERVICE_ASSERTION_INVALID` | A service assertion has malformed signed fields |
| `SERVICE_ASSERTION_WINDOW_INVALID` | Assertion expiry is non-positive or exceeds five minutes |
| `DEDICATED_PARITY_REQUIRED` | Image-digest or schema parity is disabled |

Malformed manifests fail separately with `MANIFEST_SCHEMA_INVALID`.

## Supersession and compatibility

This decision supersedes Railway and free-Render configurations as production
targets. It does not delete or modify `railway.toml`, `render.yaml`, local
Docker Compose, `.env.example`, or other development descriptors. Those
descriptors cannot be used as production-release evidence.

## Consequences

Later deployment automation must materialize this contract and prove service
assertions, backup/restore, SLOs, and rollback rather than infer readiness from
provider deployment success. Any customer-specific topology remains compatible
only while its digests, schemas, and contracts stay in parity with the
canonical release.
