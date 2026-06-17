# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Project Rules (Highest Priority)

This is a production-grade Enterprise Document Intelligence Platform intended for real clients with confidential/sensitive data (law firms, logistics, etc.).

NON-NEGOTIABLE PRINCIPLES:
- Security and privacy first: encryption at rest, audit logging, access control, prompt injection defense
- Follow the latest PROJECT_SPEC.md exactly
- Multi-tenancy + document-level ACLs from the beginning
- Support for self-hosted LLMs / air-gapped deployment
- Build incrementally following the updated phases (Phase 0 first)
- Always consider compliance (SOC 2 readiness, GDPR, attorney-client privilege)

## Project Status

**Phases 0–8 are implemented** (v0.1.0, pre-1.0). The backend (`backend/`) is feature-complete across all eight build phases with 175 passing tests (ruff/mypy clean); a minimal Next.js reference UI lives in `frontend/`. `PROJECT_SPEC.md` remains the source of truth for intended architecture; see `README.md`, `CHANGELOG.md`, and the per-phase notes in `backend/README.md`.

## What This Is

An enterprise-grade AI platform for querying private company documents via natural language. Target customers: law firms, logistics, financial services. Key differentiators: security-first design (encryption, audit logs, ACLs), RAGAS evals CI gate, multi-tenancy with document-level access control, and flexible deployment (SaaS → air-gapped on-prem).

## Planned Tech Stack

**Backend**: Python 3.11+, FastAPI, LangGraph 0.2+, LlamaIndex, SQLAlchemy 2.x + Alembic, pgvector + PostgreSQL 16, Celery + Redis, Fernet/AES encryption.

**Frontend**: Next.js 14 App Router, TypeScript, Tailwind + shadcn/ui, TanStack Query + Zustand.

**Infrastructure**: Docker + Docker Compose, Fly.io/AWS/Azure/on-prem, MinIO or S3-compatible storage, GitHub Actions + Trivy.

**LLM**: Anthropic Claude (default, zero-retention DPA), self-hosted vLLM for enterprise, local models for air-gapped.

## Core Architecture (From Spec)

The system has eight major components:

1. **Secure Ingestion Pipeline** — virus scan → classify → encrypt → chunk → embed → store (background Celery task)
2. **Hybrid Retrieval** — vector + BM25 + cross-encoder reranking, with **retrieval-time ACL enforcement** (users only see chunks they're permitted to access)
3. **LangGraph Multi-Agent Workflow** — Planner → Retriever → Verifier → Synthesizer → Source Attributor; Verifier also checks for confidentiality violations; all LLM calls logged with trace ID + user context
4. **RAGAS Evaluation CI Gate** — automated quality threshold before every deploy
5. **Access Control & Multi-Tenancy** — Row-Level Security (RLS) per tenant + document-level ACLs; roles: CanView/CanQuery/CanUpload/CanDelete/CanReview; groups/departments/matters
6. **MCP Server + API Security** — rate limiting, per-tenant API key scoping, optional mTLS
7. **Observability & Compliance** — Langfuse + OpenTelemetry, SIEM-ready audit log export, GDPR DSR tools
8. **FastAPI Endpoints** — includes `/documents/classify`, `/audit/logs`, `/compliance/ds-request`

## Database Schema (Key Tables)

- `documents` — includes `encryption_key_version`, `classification_level` (public/internal/confidential/privileged), `owner_user_id`, `department`, `deleted_at`
- `document_access_control` — fine-grained ACLs (user/group + permission)
- `audit_logs` — immutable log of every document access and query
- `data_retention_policies`, `compliance_events`
- All sensitive columns encrypted via pgcrypto or application-level encryption

## Build Phases

Phase 0 (Security Foundation) → Phase 1 (Secure ingestion + basic RAG) → Phase 2 (Production retrieval) → Phase 3 (Multi-agent + human approval) → Phase 4 (Evals + CI gate) → Phase 5 (Advanced ACL + audit) → Phase 6 (Compliance + observability) → Phase 7 (Multi-deployment + self-hosted LLM) → Phase 8 (Polish + packaging)

## Security Non-Negotiables

- SOC 2 Type II readiness; GDPR/CCPA compliance
- Attorney-client privilege safeguards (law firm segment)
- Full audit trail on every document access and query
- Fully private deployment option (no data leaves customer infra)
- Encryption at rest (AES-256, CMEK optional) and in transit (TLS 1.3)
