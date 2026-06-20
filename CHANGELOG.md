# Changelog

All notable changes to the Enterprise Document Intelligence Platform are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### V1 repurpose — Sales-Enablement Assistant for AEs

Re-framed the enterprise RAG platform into a focused sales-enablement assistant for
Account Executives. The retrieval + multi-agent (cited, streaming) engine, multi-tenancy,
JWT auth, ingestion, and audit logging are reused as-is.

#### Changed
- **Roles** reduced to two effective roles: manager (OWNER/ADMIN) and AE (MEMBER).
  Uploads/curation are manager-only; AEs consume via chat.
- **Content metadata** replaces the legal taxonomy: `documents.content_type`
  (product / pricing / objections / battlecard / case_study / script) + `visibility`
  (rep_visible / manager_only); the former MIME `content_type` column is now `mime_type`.
  Dropped `classification_level`, `department`, `matter_id` (migration `0009`).
- **Visibility-based access**: AEs may VIEW/QUERY all rep-visible content without an
  explicit grant; manager-only content stays grant/role-gated (enforced at retrieval time).
- **Honest low-confidence answers**: with the human-review gate off (v1 default), a
  low-confidence answer is delivered with its confidence surfaced instead of being held.
- **Terminology/branding** reskinned to "Sales Assistant" (API title/description, UI).

#### Added
- **Manager-curated content**: `ramp_topics` + `saved_objections` tables (migration `0010`),
  with `GET /ramp/topics` and `GET /objections` (AE-readable) plus manager CRUD.
- **Frontend**: AE chat with streaming cited answers, an objection-lookup quick mode, and a
  low-confidence banner; a `/ramp` onboarding checklist (deep-links into the chat); a
  manager `/admin` area for content upload (type + visibility), rep invites, and ramp/
  objection curation.
- Streaming `/query/stream` `done` event now carries `confidence`.

#### Feature-flagged off for v1 (kept in the codebase, default on in dev/test)
- `ENABLE_COMPLIANCE` (GDPR/DSR + SIEM audit export), `ENABLE_EVALS` (evals run history),
  and `ENABLE_HUMAN_REVIEW` (the human-approval gate). The MCP server remains unmounted.
- Classification-based self-hosted LLM routing is retired from the product; deployment-mode
  and per-tenant self-hosted policy routing remain.

## [0.1.0] — 2026-06-12

First end-to-end release: a secure, multi-deployment RAG platform built across eight
incremental phases. Pre-1.0 — APIs may still change before the first stable release.

### Phase 0 — Security Foundation
- Multi-tenant data model (tenants, users, roles), custom JWT auth (access + refresh),
  Argon2 password hashing.
- Application-level envelope encryption (KEK→DEK, AES-256-GCM) with key versioning.
- Append-only audit log + single `audit_service.write_event` entry point.

### Phase 1 — Secure Ingestion + Vector Search
- Upload → malware-scan → encrypt → extract → chunk → embed → store pipeline.
- Pluggable storage (local / S3-compatible) of envelope-encrypted bytes.
- Tenant-scoped vector search; OpenAI + deterministic Fake embedders.

### Phase 2 — Production Retrieval
- BM25 keyword search (Postgres FTS on a derived `content_tsv`), hybrid fusion, and
  cross-encoder re-ranking (optional `[reranker]` extra; Fake reranker offline).

### Phase 3 — Multi-Agent Workflow + Human Approval
- LangGraph Planner → Retriever → Verifier → (human-review gate) → Synthesizer → Source
  Attributor; cited answers; low-confidence answers held for review.
- `LLMClient` abstraction (Anthropic + offline Fake); every LLM call audited.

### Phase 4 — RAGAS Evaluation + CI Gate
- Ground-truth dataset + harness scoring faithfulness / context precision / answer
  relevancy; deterministic offline gate + key-gated real RAGAS job; results persisted.

### Phase 5 — Advanced Access Control + Audit
- Document-level ACLs, groups (department/matter/client), fine-grained permissions,
  retrieval-time deny-by-default enforcement, immutable audit (PG trigger + REVOKE).

### Phase 6 — Compliance, Observability & MCP
- Pluggable tracing (metadata-only Langfuse), SIEM audit export, per-tenant API keys,
  an MCP stdio server (4 ACL-enforced tools), GDPR DSRs, security middleware.

### Phase 7 — Self-hosted LLM + Deployment Modes
- OpenAI-compatible LLM backend (vLLM/Ollama), classification-aware model routing
  (fail-closed), local embeddings, four deployment modes with an air-gapped validator.

### Phase 8 — Polish, Documentation & Packaging
- Top-level README, DEPLOY / SELFHOSTED / SECURITY docs (SOC 2-style control summary).
- Production Dockerfiles (backend + frontend), prod compose, CI (build + gitleaks +
  Trivy) and a deploy workflow template.
- Minimal Next.js frontend (landing + login + query UI).
- OpenAPI metadata + examples, JSON structured logging, version/changelog tooling.

[Unreleased]: https://example.com/edip/compare/v0.1.0...HEAD
[0.1.0]: https://example.com/edip/releases/tag/v0.1.0
