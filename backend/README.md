# EDIP Backend — Phases 0–8

The Enterprise Document Intelligence Platform backend.

- **Phase 0 (Security Foundation)**: multi-tenant auth, envelope encryption, append-only audit.
- **Phase 1 (Core Foundation)**: secure document ingestion (upload → malware scan → encrypt →
  extract → chunk → embed → store) and tenant-isolated vector search.
- **Phase 2 (Production Retrieval)**: hybrid search (vector + BM25), deduped and cross-encoder
  re-ranked to a final top-6.
- **Phase 3 (Multi-Agent Workflow)**: a LangGraph workflow (Planner → Retriever → Verifier →
  human-approval gate → Synthesizer → Source Attributor) that answers questions with inline
  citations, holding low-confidence answers for human review.
- **Phase 4 (Evals + CI Gate)**: a RAGAS evaluation pipeline that runs the real workflow over a
  ground-truth dataset, scores faithfulness / context_precision / answer_relevancy, persists
  results, and gates deploys on quality thresholds.
- **Phase 5 (Access Control + Audit)**: document-level ACLs with fine-grained permissions,
  groups (department/matter/client), **retrieval-time enforcement** (a user only ever sees chunks
  they may QUERY), admin user/group/grant management, and immutable audit logging.
- **Phase 6 (Compliance & Observability + MCP)**: Langfuse tracing (metadata-only by default),
  SIEM audit export, GDPR Data Subject Requests, per-tenant API keys, an MCP server with four
  ACL-enforced tools, and security hardening (headers + rate limiting). See `../PROJECT_SPEC.md`.

## Stack

FastAPI · SQLAlchemy 2.x (async) · PostgreSQL 16 + pgvector · Alembic · JWT (python-jose)
· Argon2 (passlib) · AES-256-GCM envelope encryption (cryptography) · LlamaIndex SentenceSplitter
· OpenAI `text-embedding-3-large` (3072-dim) · Postgres FTS (BM25) · cross-encoder re-ranking
(sentence-transformers, optional) · pypdf / python-docx · managed with **uv**.

## Document ingestion & search

- `POST /documents` (multipart) — size/type/malware gated, returns **202** + `PENDING`; ingestion
  runs in the background (extract → chunk → embed → store). Bytes and every chunk are
  encrypted at rest.
- `GET /documents` / `GET /documents/{id}` — tenant-scoped; status + `error_message` track ingestion.
- `POST /search` — **hybrid retrieval**: dense (vector) + BM25 keyword candidates, deduped by chunk
  and **cross-encoder re-ranked** to the final top-6, **within your tenant only**. Each result carries
  `methods` (which retrievers surfaced it); each search audits the accessed document/chunk ids plus
  the method breakdown.

### Retrieval internals (Phase 2)

- **BM25** uses a derived `content_tsv` (`to_tsvector`) column on PostgreSQL via
  `plainto_tsquery` + `ts_rank_cd` (GIN-indexed). Full chunk text stays encrypted in
  `content_encrypted`; only stemmed lexemes are stored. Toggle with `ENABLE_BM25`.
- **Re-ranking** uses `cross-encoder/ms-marco-MiniLM-L-6-v2` via the optional `[reranker]` extra
  (`uv sync --extra reranker`). Without it (or in dev), a deterministic `FakeReranker` is used.
- Tunables: `HYBRID_VECTOR_CANDIDATES`, `HYBRID_BM25_CANDIDATES`, `FINAL_TOP_K`, `RERANK_WEIGHT`.

Embeddings use OpenAI by default; in development with no `OPENAI_API_KEY`, a deterministic `fake`
provider is used automatically so the app and tests run offline. Document bytes are stored via a
`StorageBackend` (local filesystem in dev, S3/MinIO in prod) selected by `STORAGE_BACKEND`.

> Exact (brute-force) cosine + Postgres GIN FTS are used now; a pgvector ANN index (HNSW/`halfvec`)
> is a future optimization. On non-Postgres dev/test databases, vector similarity and BM25 are
> computed in Python.

## Multi-agent Q&A (Phase 3)

A LangGraph workflow turns retrieval into cited answers:

`Planner → Retriever → Verifier →` *(conditional)* `→ {human_review | Synthesizer → Source Attributor}`

- `POST /query` — runs the full workflow and returns a grounded, **cited** answer, or
  `pending_approval` when the Verifier's confidence is below `CONFIDENCE_THRESHOLD` (or it flags a
  confidentiality concern). The question and answer are **encrypted at rest** in the `queries` table.
- `POST /query/stream` — streams the final answer token-by-token over SSE (`token` events, then a
  `citations`/`done` event), or a single `pending` event when held for review.
- `GET /query/{id}` — tenant-scoped; decrypts for the response.
- `POST /query/{id}/approve` · `/reject` — reviewer-only (owner/admin/reviewer); approve synthesizes
  and completes the held query.

Models: Planner `claude-sonnet-4-6`, Verifier `claude-haiku-4-5`, Synthesizer `claude-opus-4-8`
(Source Attributor is deterministic). Every LLM call is audited with a trace id. In development with
no `ANTHROPIC_API_KEY`, a deterministic `FakeLLM` is used automatically so the graph and tests run
offline. Retrieval stays tenant-scoped; chunk text is decrypted only in memory and the graph is not
checkpointed to disk.

> Phase 3 ships a baseline grounding/prompt-injection guard (context is delimited and framed as
> untrusted data). A fuller injection-defense layer and classification-based self-hosted-LLM routing
> are later phases.

## Evaluation & CI gate (Phase 4)

A RAGAS pipeline measures answer quality and **blocks deploys on regressions**. It runs the real
LangGraph workflow over a ground-truth dataset (`../evals/ground_truth.json`, ingested from
`../evals/corpus/`), scoring three metrics: **faithfulness** (answer grounded in retrieved
context), **context_precision** (retrieved contexts on-topic), and **answer_relevancy** (answer
addresses the question). A run passes only if every mean metric ≥ its `EVAL_THRESHOLD_*`.

- **Two evaluators, one interface** (mirrors the embedder/reranker/LLM pattern). `RagasEvaluator`
  computes real metrics with a `claude-sonnet-4-6` judge (`EVAL_JUDGE_MODEL`) + OpenAI embeddings —
  the optional `[evals]` extra (`uv sync --extra evals`) and an `ANTHROPIC_API_KEY`. `FakeEvaluator`
  is a deterministic lexical scorer used offline; `EVALS_PROVIDER`/`effective_evals_provider` falls
  back to it when the extra is absent or (in dev) no key is set.
- **Dedicated eval tenant**: the corpus is ingested into the `eval-harness` tenant
  (`EVAL_TENANT_SLUG`), isolated from real tenants; the harness only ever retrieves within it.
- **Persistence**: each run writes an `eval_runs` row (means, thresholds, pass/fail, provider,
  git sha) and per-item `eval_results`. The eval corpus is **synthetic, non-confidential** data, so
  eval question/answer are stored in the clear (unlike `queries`, which stay encrypted).
- **Dashboard**: `GET /evals/runs` and `GET /evals/runs/{id}` (owner/admin, tenant-scoped, audited)
  expose runs + per-item results for a later frontend. Runs are created only by the harness/CLI.

Run it locally:

```bash
# Offline, deterministic (no key, no network) — what the PR gate runs:
uv run python ../evals/run_evals.py --provider fake     # exits non-zero if below thresholds

# Real RAGAS (needs the extra + keys):
uv sync --extra evals
EVALS_PROVIDER=ragas uv run python ../evals/run_evals.py --provider ragas
```

CI (`.github/workflows/eval-gate.yml`) has two gates: a **`tests`** job (always; runs the suite
including the deterministic eval gate, no secrets) and a key-gated **`ragas-eval`** job (real RAGAS
against Postgres on push to `main`). The `run_evals.py` non-zero exit fails the job → blocks deploy.

> Every node's LLM call plus `EVAL_RUN_STARTED`/`EVAL_RUN_COMPLETED`/`EVAL_RESULTS_VIEWED` are
> audited. Running RAGAS over real client data is out of scope — the harness is pinned to the
> synthetic eval tenant.

## Access control (Phase 5)

Within a tenant, access is **deny-by-default**: beyond the document owner and tenant OWNER/ADMIN,
nobody reaches a document until explicitly granted. Permissions are resolved in one place
(`app/services/authz.py`).

- **Permissions** (`Permission`): `VIEW`, `QUERY`, `DELETE`, `REVIEW`, `MANAGE` — granted per
  document to a **user** or a **group** via `document_access_control`. `UPLOAD` stays role-based.
- **Groups** (`groups` + `group_memberships`) model departments / matters / clients / teams; a grant
  to a group applies to all its members (matter walls). Documents can be filed under a `matter_id`.
- **Retrieval-time enforcement**: `retrieval.hybrid_search` (and both legs) take
  `allowed_document_ids`; the workflow retriever and `/search` compute the caller's QUERY-accessible
  set (`None` = unrestricted for OWNER/ADMIN, empty = fail-closed). A user can never retrieve, cite,
  or stream a chunk from a document they can't QUERY.
- **Endpoints**: `GET /documents` / `GET /documents/{id}` are VIEW-gated (no access ⇒ 404, no
  existence leak); `DELETE /documents/{id}` needs CanDelete; `GET/POST/DELETE /documents/{id}/acl`
  manage grants (needs MANAGE). `/admin/users` and `/admin/groups` (+ membership) are OWNER/ADMIN
  only. Reviewers may approve a held query only if they hold `REVIEW` on every source document.
- **Audit**: expanded with an `outcome` (`allow`/`deny`) column; denied access is recorded
  (`ACCESS_DENIED`). On PostgreSQL, `audit_logs` is **append-only** — a migration revokes
  UPDATE/DELETE and installs a trigger that rejects any mutation (hash-chaining is a future
  enhancement).

## Compliance & observability + MCP (Phase 6)

- **Tracing**: the workflow's `trace_span`/`record_generation` seam now drives a pluggable
  tracer. `LangfuseTracer` (optional `[observability]` extra) emits a root trace per query with
  nested spans/generations; `FakeTracer` is the offline default. **Privacy-first**: spans carry
  only metadata (node/model/counts/ids) — prompt/answer/context text is sent **only** when
  `LANGFUSE_CAPTURE_IO=true`.
- **Audit export**: `GET /audit/logs` gains filters (action / actor / resource / outcome / time);
  `GET /audit/export?format=ndjson|csv|json` streams SIEM-ready rows (admin-only, audited).
- **MCP server** (`mcp_server/`, stdio, optional `[mcp]` extra) exposes four ACL-enforced tools —
  `query_documents`, `search_chunks`, `list_documents`, `get_document` — authenticated by a
  **per-tenant API key** that acts as a specific user. Issue keys via `POST /admin/api-keys`
  (returned once, argon2-hashed at rest, revocable/expiring). Every tool call is audited
  (`MCP_TOOL_CALLED`); tool logic lives in `app/services/mcp_tools.py` (tested without the SDK).
- **Compliance**: `GET /compliance/config` (region, encryption, sub-processors, append-only-audit,
  IO-capture flag), `GET/PUT /compliance/retention`, and GDPR **DSRs** —
  `POST /compliance/ds-request` + `/{id}/fulfill` produce an access/export bundle or perform
  erasure (deletes the subject's queries, anonymizes the user; **audit logs are retained** on a
  legal-obligation basis).
- **Hardening**: `SecurityHeadersMiddleware` (HSTS, `X-Frame-Options: DENY`, CSP, etc.) and an
  in-process `RateLimitMiddleware` (`RATE_LIMIT_PER_MINUTE` → 429); both config-gated. Redis-backed
  limiting is the documented next step for multi-instance deployments.

## Self-hosted LLM & deployment modes (Phase 7)

- **Multiple LLM backends**: `LLMClient` gains `OpenAICompatibleLLM` (vLLM / Ollama / any
  OpenAI-compatible endpoint) alongside `AnthropicLLM`/`FakeLLM`. Structured outputs use a
  portable JSON-mode + tolerant parse; on failure the planner/verifier degrade to human review.
- **Classification-aware routing**: `app/services/model_router.py` resolves each node's
  `(client, model)` from **deployment mode → tenant policy → document classification**.
  Confidential/privileged documents route to a **self-hosted** profile; ordinary docs use the
  cloud baseline. **Fail-closed** — if a self-hosted route is required but `LLM_BASE_URL` is unset,
  the query returns **503** + an `llm.route_denied` audit (never a silent cloud fallback).
- **Local embeddings**: `EMBEDDING_PROVIDER` gains `openai_compatible` (reuse `OpenAIEmbedder`
  with `EMBEDDING_BASE_URL` → vLLM/Ollama/TEI) and `sentence_transformers` (in-process, optional
  `[local]` extra). Note: a non-OpenAI model usually changes the vector dimension — set
  `EMBEDDING_DIMENSIONS` to match and re-ingest into a fresh DB.
- **Deployment modes**: `DEPLOYMENT_MODE` ∈ `saas | single_tenant | private_cloud | air_gapped`.
  `private_cloud`/`air_gapped` **refuse to start** with any cloud provider configured
  (`_enforce_deployment_mode`). `GET /compliance/config` surfaces `feature_flags` + `llm_routing`.
- **Per-tenant policy**: `GET/PUT /admin/tenant/settings` (`require_self_hosted_llm`,
  `sensitive_classification`), persisted on `tenants.settings` (migration 0008), audited.
- **Deploying**: see [`../DEPLOY.md`](../DEPLOY.md) + [`../SELFHOSTED.md`](../SELFHOSTED.md) + [`../deploy/`](../deploy/) for the
  self-hosted compose stack (Postgres + vLLM + TEI + backend) and per-mode env templates.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (`pip install uv`)
- Docker (for local Postgres + Redis) — optional for running tests

## Setup

```bash
cd backend
uv sync                      # resolve + install deps into .venv

cp .env.example .env         # then fill in secrets:
#   JWT_SECRET_KEY:  python -c "import secrets; print(secrets.token_urlsafe(64))"
#   MASTER_KEK:      python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

In `development`, `JWT_SECRET_KEY` and `MASTER_KEK` have working defaults; in
`staging`/`production` the app refuses to start without strong values.

## Run local infrastructure

```bash
# from the repo root
docker compose up -d         # postgres (pgvector) + redis
```

## Migrate & serve

```bash
cd backend
uv run alembic upgrade head                       # create the schema
uv run uvicorn app.main:app --reload              # http://localhost:8000
# OpenAPI docs at http://localhost:8000/docs
```

> **Windows: `--reload` can crash or hang** (the `watchfiles` notifier conflicts with
> OneDrive-synced paths). Scope the watch to the source tree, or drop `--reload`:
>
> ```bash
> uv run uvicorn app.main:app --reload --reload-dir app   # narrower watch, usually stable
> uv run uvicorn app.main:app                             # no autoreload (always works)
> ```

> **No Docker? Run on SQLite.** The app and migrations run on a local SQLite file with no
> Postgres/Redis — fine for a quick spin (hybrid retrieval uses Python fallbacks; not for
> production). Point `DATABASE_URL` at a file before migrating/serving:
>
> ```bash
> export DATABASE_URL=sqlite+aiosqlite:///./var/dev.db   # PowerShell: $env:DATABASE_URL="sqlite+aiosqlite:///./var/dev.db"
> uv run alembic upgrade head
> ```

## Quick end-to-end check

```bash
# Register a tenant + owner
curl -X POST localhost:8000/auth/register -H 'content-type: application/json' -d '{
  "tenant_name":"Acme Legal","tenant_slug":"acme-legal",
  "email":"owner@acme.test","password":"correct horse battery staple"}'

# Login, call /auth/me with the access token, then read the audit trail:
curl localhost:8000/audit/logs -H "Authorization: Bearer <ACCESS_TOKEN>"
```

## Tests, lint, types

```bash
uv run pytest                # tests run on in-memory SQLite — no DB needed
uv run ruff check .
uv run mypy app
```

## Layout

```
app/
  core/      config, security (JWT/argon2), crypto (envelope), deps, logging
  db/        declarative base, async session, mixins, portable types
  models/    Tenant, User, AuditLog, retention/compliance skeletons
  schemas/   request/response models
  services/  auth_service, audit_service (the single audit write path)
  api/v1/    auth, audit, health routers
alembic/     migration environment + 0001_security_foundation
tests/       crypto, auth, audit
```

## Security notes (Phase 0)

- **Tenant isolation** is enforced from the JWT, never from client-supplied ids.
- **Audit logs are append-only** — no update/delete path in code; a DB-level
  append-only constraint is a recommended follow-up.
- **Envelope encryption**: the master KEK is never persisted; only wrapped DEKs are.
  `MASTER_KEK` is swappable for a KMS/CMEK provider without schema changes.
- Deferred to later phases: document ingestion, retrieval, prompt-injection defense,
  rate limiting, KMS integration, RAGAS evals.
