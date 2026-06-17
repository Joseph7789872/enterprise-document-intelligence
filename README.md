# Enterprise Document Intelligence Platform (EDIP)

Securely query your private company documents in natural language and get **cited,
grounded answers** — built security-first for law firms, financial services, and other
teams handling confidential and privileged material.

> Status: **Phases 0–8 implemented** (v0.1.0, pre-1.0). 175 backend tests passing,
> ruff/mypy clean. See [CHANGELOG.md](CHANGELOG.md).

## Why it's different

- **Encryption everywhere** — envelope encryption (AES-256-GCM) of document bytes *and*
  chunk text at rest; TLS in transit.
- **Document-level access control** — deny-by-default ACLs enforced at *retrieval time*,
  so users only ever see chunks they're permitted to read; groups for departments /
  matters / clients.
- **Grounded, cited answers** — a LangGraph multi-agent workflow (plan → retrieve →
  verify → synthesize → attribute) with **human approval** for low-confidence answers.
- **Full audit trail** — append-only, immutable audit log on every document access and
  query; SIEM-ready export; GDPR data-subject requests.
- **Deploy anywhere** — SaaS, single-tenant, private cloud, or fully **air-gapped** with
  self-hosted models. Confidential documents can be routed to self-hosted LLMs while
  ordinary documents use the cloud — and routing **fails closed**.
- **Quality gated** — a RAGAS evaluation gate (faithfulness / context precision / answer
  relevancy) blocks deploys that regress answer quality.

## Architecture

```
            ┌──────────────┐      ┌────────────────────────────────────────────┐
  Browser → │  Next.js UI  │ ───► │                FastAPI backend             │
            └──────────────┘      │                                            │
                                  │  Auth/JWT · Tenancy · ACLs · Audit         │
   Upload ──────────────────────►│  Ingestion: scan→encrypt→chunk→embed       │
                                  │  Retrieval: vector + BM25 + rerank (ACL)   │
   Ask ─────────────────────────►│  Agents: plan→retrieve→verify→synthesize   │
                                  │  Model router: cloud ⇄ self-hosted (vLLM)  │
                                  └───────┬─────────────┬──────────────┬───────┘
                                          │             │              │
                                   ┌──────▼─────┐ ┌─────▼──────┐ ┌─────▼──────┐
                                   │ Postgres + │ │  Object    │ │  LLM:      │
                                   │  pgvector  │ │  storage   │ │  Claude /  │
                                   │ (encrypted)│ │ (encrypted)│ │  vLLM/Ollama│
                                   └────────────┘ └────────────┘ └────────────┘
```

## Feature map (build phases)

| Phase | Capability |
|---|---|
| 0 | Security foundation: tenancy, JWT auth, envelope encryption, append-only audit |
| 1 | Secure ingestion pipeline + tenant-scoped vector search |
| 2 | Hybrid retrieval (vector + BM25) + cross-encoder re-ranking |
| 3 | Multi-agent workflow + human approval for low-confidence answers |
| 4 | RAGAS evaluation + CI quality gate |
| 5 | Document-level ACLs, groups, immutable enhanced audit |
| 6 | Compliance, Langfuse observability, MCP server, GDPR DSRs |
| 7 | Self-hosted LLM + classification-aware routing + deployment modes |
| 8 | Polish, docs, packaging, production hardening |

## Quickstart (local, ~3 steps)

Requires Docker + [uv](https://docs.astral.sh/uv/). Runs fully offline with deterministic
fakes (no API keys needed).

```bash
# 1. Start Postgres (pgvector) + Redis
docker compose up -d

# 2. Configure + migrate the backend
cd backend
cp .env.example .env          # dev defaults work out of the box
uv sync && uv run alembic upgrade head

# 3. Run it
uv run uvicorn app.main:app --reload
#   API docs:  http://localhost:8000/docs
```

Register a tenant, then ask a question:

```bash
curl -sX POST localhost:8000/auth/register -H 'content-type: application/json' \
  -d '{"tenant_name":"Acme","tenant_slug":"acme","email":"you@acme.com","password":"correct horse battery staple"}'
# → returns tokens; use the access_token as: Authorization: Bearer <token>
```

To run the **frontend** too: `cd frontend && npm ci && npm run dev` (→ http://localhost:3000),
or bring up the whole stack in containers with `docker compose --profile full up --build`.

## Documentation

- [DEPLOY.md](DEPLOY.md) — deployment modes, environment reference, CI/CD, monitoring.
- [SELFHOSTED.md](SELFHOSTED.md) — self-hosted LLM (vLLM/Ollama), local embeddings, air-gapped.
- [SECURITY.md](SECURITY.md) — security model + SOC 2-style control summary + disclosure.
- [backend/README.md](backend/README.md) — backend internals by phase.
- [frontend/README.md](frontend/README.md) — the reference UI.

## Tech stack

**Backend**: Python 3.11, FastAPI, SQLAlchemy 2 (async), Alembic, pgvector/PostgreSQL 16,
LangGraph, Anthropic + OpenAI-compatible LLMs. **Frontend**: Next.js 14 + TypeScript.
**Infra**: Docker, GitHub Actions, gitleaks + Trivy, optional Langfuse / vLLM.

## Project layout

```
backend/    FastAPI app, agents, services, migrations, tests
frontend/   Next.js reference UI
deploy/     Self-hosted compose stack + per-mode env templates
evals/      RAGAS ground-truth corpus + gate runner
scripts/    Secret generation + version bumping
```

## License

Proprietary. © the project authors. See [SECURITY.md](SECURITY.md) for the responsible
disclosure policy.
