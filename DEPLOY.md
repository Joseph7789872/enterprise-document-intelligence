# Deployment Guide

How to deploy EDIP across its four modes, configure it, run migrations, wire CI/CD, and
operate it in production. For **self-hosted LLM / air-gapped** specifics see
[SELFHOSTED.md](SELFHOSTED.md); for the security model see [SECURITY.md](SECURITY.md).

## Deployment modes

`DEPLOYMENT_MODE` selects the posture; it drives model routing and a startup validator.

| Mode | LLM | Embeddings | Cloud egress | Notes |
|---|---|---|---|---|
| `saas` | Anthropic baseline + optional self-hosted | OpenAI (or self-hosted) | Yes (non-sensitive) | Confidential/privileged docs → self-hosted; rest → cloud. Per-tenant overridable. |
| `single_tenant` | Self-hosted baseline | Self-hosted or cloud | Optional | One customer, dedicated instance. |
| `private_cloud` | Self-hosted only | Self-hosted only | **None** | Customer's cloud; validator blocks cloud providers. |
| `air_gapped` | Self-hosted only | Self-hosted only | **None** | Offline networks; see [SELFHOSTED.md](SELFHOSTED.md). |

In `private_cloud` / `air_gapped` the app **fails to start** if any cloud provider
(`LLM_PROVIDER=anthropic`, `EMBEDDING_PROVIDER=openai`, Langfuse Cloud, or a cloud RAGAS
judge) is configured — the load-bearing "no data leaves customer infra" guarantee.

## Prerequisites

- Docker + Docker Compose, PostgreSQL 16 with the `pgvector` extension.
- [uv](https://docs.astral.sh/uv/) for backend dependency management (or use the images).
- Secrets: a strong `JWT_SECRET_KEY` and a base64 32-byte `MASTER_KEK`
  (`python scripts/generate_secrets.py`). The app refuses to start outside development
  without them.

## Environment configuration

Templates:

- `backend/.env.example` — the full backend reference (every setting documented).
- `.env.example` (repo root) — the compose-level vars for `docker-compose.prod.yml`.
- `deploy/env.saas.example`, `deploy/env.single-tenant.example`,
  `deploy/env.air-gapped.example` — ready-made per-mode shapes.

Key settings: `ENVIRONMENT`, `DEPLOYMENT_MODE`, `DATABASE_URL`, `JWT_SECRET_KEY`,
`MASTER_KEK`, `LLM_PROVIDER`/`ANTHROPIC_API_KEY`, `EMBEDDING_PROVIDER`/`OPENAI_API_KEY`,
`CORS_ALLOW_ORIGINS`, `LOG_FORMAT`, `RATE_LIMIT_PER_MINUTE`.

## Deploy: SaaS / single-tenant (cloud)

```bash
cp .env.example .env                 # fill secrets + provider keys
python scripts/generate_secrets.py   # → JWT_SECRET_KEY + MASTER_KEK
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

This brings up Postgres + backend (which runs `alembic upgrade head` on boot) + frontend.
Verify: `curl localhost:8000/health` and `/health/ready`.

For managed hosts (Fly.io / AWS / Azure), build + push the images (see
`.github/workflows/deploy.yml`) and run `alembic upgrade head` as a release step before
shifting traffic.

## Database migrations

```bash
cd backend
uv run alembic upgrade head      # apply
uv run alembic downgrade -1      # roll back one
```

Run migrations as a discrete release step in production (the compose files run them on
container start for convenience). Migrations are hand-written and validated up/down on
both SQLite and PostgreSQL.

## CI/CD

- `.github/workflows/ci.yml` — backend lint + mypy + tests, frontend build, **gitleaks**
  secret scan, and **Trivy** filesystem + image scans. Blocks PRs.
- `.github/workflows/eval-gate.yml` — the RAGAS quality gate (Phase 4).
- `.github/workflows/deploy.yml` — template: build/push images to GHCR + migrate + deploy.

> These run only when the project is its **own** git repository (Actions reads
> `.github/workflows/` at the repo root). If nested in another repo, move them to that root.

## Logging & monitoring

- **Structured logs**: set `LOG_FORMAT=json` for one JSON object per line (timestamp,
  level, logger, `trace_id`, message) — ship to your SIEM / log aggregator. Every request
  carries an `X-Request-ID` trace id echoed in responses and stamped on audit records.
- **Health probes**: `GET /health` (liveness) and `GET /health/ready` (DB reachable) —
  wire to your orchestrator's liveness/readiness checks.
- **Audit/observability**: SIEM export via `GET /audit/export` (ndjson/csv/json);
  optional Langfuse tracing (metadata-only by default — see [SECURITY.md](SECURITY.md)).
- **Metrics (recommended add-on)**: front the service with your platform's metrics (or add
  a Prometheus exporter) for request rate/latency/error dashboards + alerting.
- **Rate limiting**: in-process token bucket (`RATE_LIMIT_PER_MINUTE`); for multi-instance
  deployments move the counter to Redis (documented limitation).

## Backups & DR

- Back up PostgreSQL (it holds encrypted documents/chunks + audit) and the object store.
- Safeguard `MASTER_KEK` in a secrets manager / KMS — losing it makes encrypted data
  unrecoverable. Key rotation is supported via `encryption_key_version` columns.
- The append-only audit log is part of your compliance record — include it in retention
  and backup policy (`AUDIT_LOG_RETENTION_DAYS`).
