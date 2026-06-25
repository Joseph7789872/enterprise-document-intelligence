# Sales Assistant

A **sales-enablement assistant for Account Executives** at small SaaS teams. Ask
natural-language questions of your company's sales knowledge — product, pricing/packaging,
ICP/personas, discovery & demo scripts, competitive positioning, objection-handling guides,
battlecards, and case studies — and get fast, **cited, grounded answers**.

> Status: **v1 in progress** — repurposed from the secure RAG platform below. Backend
> tests green (ruff/mypy clean); see [CHANGELOG.md](CHANGELOG.md).

## Two jobs it does

- **New-rep ramp** — a manager-curated starter checklist turns into cited answers so new
  AEs get productive fast.
- **Live objection prep** — a one-click saved-objection library answers "how do I handle
  *<objection>*?" from your battlecards and case studies, with sources and confidence.

Two roles: **managers** (upload & curate content, invite reps, set rep-visible vs.
manager-only visibility) and **AEs** (consume via chat).

## Built on a security-first RAG foundation

The product is a focused re-frame of an enterprise RAG platform; it reuses that engine
as-is:

- **Cited, streaming answers** — a LangGraph multi-agent workflow (plan → retrieve →
  verify → synthesize → attribute). Low-confidence answers are returned honestly ("not
  fully sure — here's what I found") rather than gated.
- **Visibility-aware retrieval** — rep-visible content is queryable by every AE;
  manager-only content (e.g. floor pricing) is enforced at *retrieval time*.
- **Multi-tenant + encrypted** — per-tenant isolation, envelope encryption (AES-256-GCM)
  of bytes and chunk text at rest, JWT auth, append-only audit log.
- **Hybrid retrieval** — vector + BM25 + cross-encoder re-ranking.

Enterprise-only surfaces from the original platform (GDPR/DSR compliance endpoints, the
evals run-history API, the human-approval gate, classification-based self-hosted routing,
the MCP server) are **kept in the codebase but switched off by feature flag** for v1
(`ENABLE_COMPLIANCE`, `ENABLE_EVALS`, `ENABLE_HUMAN_REVIEW` — see `backend/.env.example`).

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
