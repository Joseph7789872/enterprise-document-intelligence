# Changelog

All notable changes to the Enterprise Document Intelligence Platform are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
