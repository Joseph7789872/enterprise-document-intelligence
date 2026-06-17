# Enterprise Document Intelligence Platform — Production-Ready Specification

## What This Project Is

A secure, compliant, enterprise-grade AI platform that allows employees to ask natural language questions and receive accurate, cited answers from thousands of private company documents. It uses a multi-agent LangGraph workflow with hybrid retrieval, verification, human-in-the-loop approval for low-confidence answers, and automated quality gates.

**Target Customers**: Small law firms, logistics companies, professional services, financial services, and other organizations with sensitive unstructured data.

**Core Differentiators**:
- Strong security & privacy by design (zero-retention LLM options, encryption, audit logging)
- Production reliability with RAGAS evals + CI gate
- Multi-tenancy with document-level access control
- Flexible deployment (SaaS, private cloud, on-prem/air-gapped)

## Security & Compliance Goals (Non-Negotiable)

- SOC 2 Type II readiness
- GDPR / CCPA / data residency support
- Attorney-client privilege & confidentiality safeguards (critical for law firms)
- Full audit trail of every document access and query
- Option for fully private deployment (no data leaves customer infrastructure)

## Updated System Architecture

## Tech Stack (Production & Secure)

### Backend
- Python 3.11+
- FastAPI + FastAPI Users / Authlib
- LangGraph 0.2+
- LlamaIndex (ingestion & retrieval)
- SQLAlchemy 2.x + Alembic
- pgvector + PostgreSQL 16 (with pgcrypto)
- Celery + Redis (background ingestion & async tasks)
- Fernet + AES encryption for sensitive fields
- rate-limiter + slowapi

### Security & Privacy Additions
- **Document Storage**: AES-256 encrypted at rest (customer-managed keys optional)
- **Embedding & Inference Options**:
  - Default: Anthropic Claude (with strict DPA + zero retention)
  - Enterprise: Self-hosted models via vLLM (Llama 3.1 70B, Mixtral, etc.)
  - Air-gapped: Local models + local embeddings
- Virus/Malware scanning (ClamAV or commercial)
- Prompt injection & data poisoning detection layer

### Frontend
- Next.js 14+ App Router + TypeScript
- Tailwind + shadcn/ui
- TanStack Query + Zustand
- Role-Based UI + Document ACL views

### Infrastructure
- Docker + Docker Compose
- Kubernetes-ready manifests (optional)
- Fly.io / AWS / Azure / On-prem
- Supabase / Neon / RDS Postgres (with encryption)
- MinIO or S3-compatible storage
- GitHub Actions + Trivy security scanning

## Enhanced Database Schema (Key Additions)

- `documents` table now includes:
  - `encryption_key_version`
  - `classification_level` (public / internal / confidential / privileged)
  - `owner_user_id`, `department`
  - `deleted_at` (soft delete + retention policy)

- New tables:
  - `document_access_control` (fine-grained ACLs: user/group + permission)
  - `audit_logs` (who accessed what document/chunk, when, via which query)
  - `data_retention_policies`
  - `compliance_events`

- All sensitive columns encrypted using pgcrypto or application-level encryption.

## Component 1: Secure Document Ingestion Pipeline

- Virus/malware scan on upload
- Classification tagging (optional manual + auto)
- Client-side or server-side encryption before storage
- Chunking with metadata preservation
- Secure embedding (option to use private embedding models)
- Background task with retry + dead-letter queue

## Component 2: Hybrid Retrieval + Security

- Same strong hybrid (vector + BM25 + cross-encoder) retrieval
- **Retrieval-time ACL enforcement** — only return chunks user is allowed to see
- Query-time PII redaction option (for highly sensitive deployments)

## Component 3: LangGraph Multi-Agent Workflow

(Unchanged core flow, but with added security)

- Planner, Retriever, Verifier, Synthesizer, Source Attributor
- **Verifier** now also checks for potential confidentiality violations or hallucinations
- All LLM calls logged with trace ID + user context
- Optional routing to self-hosted LLM based on document classification

## Component 4: RAGAS Evaluation + CI Gate (Unchanged but Critical)

- Remains a core quality gate before any deployment

## Component 5: Advanced Access Control & Multi-Tenancy

- Tenant isolation (RLS) + **Document-level ACLs**
- Groups / Departments / Matter / Client folders (especially important for law firms)
- Granular permissions: CanView, CanQuery, CanUpload, CanDelete, CanReview
- Full audit logging on every read/query

## Component 6: MCP Server + API Security

- Rate limiting, API key scoping per tenant
- Optional IP allow-listing and mTLS for enterprise customers

## Component 7: Observability & Compliance

- Langfuse + OpenTelemetry traces
- Comprehensive audit log export (SIEM ready)
- Data subject request (DSR) tools for GDPR
- Usage & cost reporting per customer / department

## Component 8: FastAPI Backend Endpoints

(Existing endpoints + new ones)
- `/documents/classify`
- `/audit/logs`
- `/compliance/ds-request`
- Enhanced admin & tenant management

## Deployment Options (Critical for Sales)

1. **SaaS (Multi-tenant)** – Shared cluster with strong isolation
2. **Single-Tenant Cloud** – Dedicated instance per customer
3. **Private Cloud / VPC** – Customer AWS/Azure account
4. **On-Prem / Air-Gapped** – Full self-hosted stack with local LLMs

## Key Security & Compliance Features

- Encryption at rest & in transit (TLS 1.3)
- Customer-managed encryption keys (CMEK) support
- Comprehensive audit logging (immutable)
- Data residency options (EU, US, etc.)
- Regular penetration testing recommendation
- SOC 2, ISO 27001 readiness documentation
- DPA + BAA templates for legal/financial customers
- Prompt & output guardrails (NVIDIA NeMo Guardrails or similar)

## Build Phases (Updated)

**Phase 0: Security Foundation** (New)
- Threat modeling
- Encryption strategy
- Authentication & authorization design
- Audit logging skeleton

**Phase 1: Core Foundation** (Secure ingestion + basic RAG)
**Phase 2: Production Retrieval**
**Phase 3: Multi-Agent Workflow + Human Approval**
**Phase 4: Evals + CI Gate**
**Phase 5: Advanced Access Control + Audit**
**Phase 6: Compliance & Observability**
**Phase 7: Multi-Deployment Support + Self-hosted LLM**
**Phase 8: Polish, Documentation & Packaging for Sales**

## Success Criteria for Production Release

- Passes internal red-team security review
- No PII leakage in LLM calls (verified)
- Audit logs cover all sensitive actions
- Evals consistently above thresholds
- Successful deployment in all four modes (SaaS, single-tenant, private, on-prem)
- GDPR data subject request can be fulfilled in <72h

## Environment Variables (Extended)

(Add encryption keys, KMS settings, self-hosted LLM endpoints, audit log retention, classification rules, etc.)