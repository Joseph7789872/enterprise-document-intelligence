# Security & Compliance

This document is for security and compliance reviewers evaluating EDIP. It summarizes the
security model, maps implemented controls to SOC 2 Trust Service Criteria, describes data
handling and privacy, and — importantly — states honestly what is **not yet** in place.

> EDIP is pre-1.0. The controls below are implemented in code; the project has **not**
> undergone a formal third-party SOC 2 audit or penetration test. This is a control
> *summary* to support due diligence, not an attestation.

## Security model overview

- **Multi-tenancy**: every tenant-scoped row carries a `tenant_id`, always derived from
  the authenticated principal's token — never from client input. Cross-tenant access
  returns 404 (no existence disclosure).
- **Encryption at rest**: application-level envelope encryption (a master KEK wraps
  per-record DEKs; AES-256-GCM authenticated encryption). Document bytes *and* chunk text
  are encrypted; only stemmed lexemes (not plaintext) are stored for keyword search.
  `encryption_key_version` columns support rotation; the KEK is CMEK/KMS-swappable.
- **Encryption in transit**: TLS 1.3 (deployment/ingress-enforced).
- **Authentication**: custom JWT (access + refresh) with Argon2 password hashing; tenant
  + role baked into the token.
- **Authorization**: role-based checks plus **document-level ACLs** resolved in one place
  (`authz`) and enforced at *retrieval time* — deny-by-default, fail-closed (an empty
  permitted set yields no results, never all results).
- **Auditability**: a single `audit_service.write_event` path; the audit log is
  append-only (PostgreSQL `REVOKE UPDATE/DELETE` + a trigger), capturing actor, action,
  resource, outcome, IP, and trace id on every sensitive action.
- **AI-specific controls**: retrieved context is delimited and treated as data, not
  instructions (baseline prompt-injection defense); a verifier scores grounding and flags
  confidentiality concerns; low-confidence answers are held for human approval;
  confidential/privileged documents can be routed to self-hosted models (fail-closed).

## SOC 2-style control summary

Mapped to the Trust Service Criteria. "Where" points at the implementing code/feature.

### Security (Common Criteria)

| Control | Implementation | Where |
|---|---|---|
| Logical access — authentication | JWT access/refresh, Argon2 hashing, failed-login auditing | `core/security.py`, `services/auth_service.py` |
| Logical access — authorization | Role checks + per-document ACLs, deny-by-default, centralized resolution | `services/authz.py`, `core/deps.py` |
| Encryption at rest | Envelope AES-256-GCM for bytes + chunk text; key versioning | `core/crypto.py` |
| Encryption in transit | TLS 1.3 at ingress; HSTS header | `core/middleware.py` (HSTS) |
| Audit logging | Append-only log on every sensitive action; immutable via DB trigger | `services/audit_service.py`, migration 0006 |
| Network/app hardening | Security headers (CSP, X-Frame-Options DENY, nosniff, Permissions-Policy), rate limiting | `core/middleware.py` |
| Secret management | Secrets via env/secret-manager; fail-fast prod validator; gitleaks in CI | `core/config.py`, `.github/workflows/ci.yml` |
| Vulnerability management | Trivy fs + image scans, dependency pinning, `uv.lock` | `.github/workflows/ci.yml` |
| API key management | Per-tenant keys, argon2-hashed at rest, revocable/expiring, scoped to a principal | `services/api_key_service.py` |
| Change quality gate | RAGAS eval gate + lint/type/test block merges | `.github/workflows/eval-gate.yml`, `ci.yml` |

### Confidentiality

| Control | Implementation |
|---|---|
| Data classification | `classification_level` (public/internal/confidential/privileged) on every document |
| Need-to-know enforcement | Retrieval-time ACL filtering; matter/department/client groups; attorney-client matter walls |
| Confidential routing | Classification-aware model routing to self-hosted LLMs; **fail-closed** (no silent cloud fallback) |
| Minimized egress to AI providers | Metadata-only tracing by default; self-hosted/air-gapped modes with a startup validator |

### Availability

| Control | Implementation |
|---|---|
| Health/readiness | `/health`, `/health/ready` probes for orchestration |
| Abuse protection | Rate limiting (429) |
| Recoverability | DB + object-store backups; documented DR + key custody (see DEPLOY.md) |

### Processing Integrity

| Control | Implementation |
|---|---|
| Answer grounding | Verifier scores grounding/confidence; cited answers map markers to real chunks |
| Human-in-the-loop | Low-confidence / confidentiality-flagged answers held for reviewer approval |
| Quality regression gate | RAGAS faithfulness / context precision / answer relevancy thresholds in CI |
| Integrity of stored data | AES-GCM auth tags detect tampering; SHA-256 of document plaintext recorded |

### Privacy

| Control | Implementation |
|---|---|
| Data subject access/export | GDPR DSR endpoints assemble the subject's record/documents/queries/audit |
| Right to erasure | DSR erasure deletes the subject's queries + anonymizes the user; audit retained on legal-obligation basis |
| Retention | Configurable retention policies + `AUDIT_LOG_RETENTION_DAYS` |
| Data residency | `DATA_REGION` label + deployment-mode controls over where data is processed |

## Data handling & sub-processors

- **Document content** is encrypted at rest and decrypted in-memory only for the duration
  of a request (to embed, retrieve, or synthesize). It is never persisted in cleartext and
  the agent graph is not checkpointed to disk.
- **Sub-processors** depend on configuration and are surfaced live at
  `GET /compliance/config`: Anthropic (LLM) and OpenAI (embeddings) in the SaaS default;
  **none** in private-cloud/air-gapped mode. Langfuse (if enabled) receives **metadata
  only** unless `LANGFUSE_CAPTURE_IO=true` is explicitly set.

## Known limitations / deferred (honest disclosure)

These are intentionally **not yet** implemented; they are roadmap items, not claims:

- No third-party SOC 2 audit or penetration test has been performed.
- `MASTER_KEK` is env/secret-manager supplied; native KMS/CMEK integration is a seam, not
  a finished integration.
- The rate limiter is in-process (per instance); multi-instance deployments need a
  Redis-backed limiter.
- Audit immutability is enforced by DB privileges + trigger; cryptographic hash-chaining
  of audit records is not yet implemented.
- Prompt-injection defense is a baseline (context delimiting + grounding verifier), not a
  comprehensive guardrail/DLP layer.
- The reference frontend stores its token in `localStorage` (demo); a hardened SPA should
  use httpOnly cookies + refresh rotation.

## Vulnerability disclosure

Please report security issues privately to **security@example.com** rather than opening a
public issue. We aim to acknowledge within 3 business days. Do not access data that is not
yours, and give us reasonable time to remediate before any disclosure.
