# Deployment configs

Reference compose stack + per-mode environment templates for running EDIP with a
**self-hosted LLM**. See [`../SELFHOSTED.md`](../SELFHOSTED.md) for the full guide
(modes, routing, the air-gapped guarantee) and [`../DEPLOY.md`](../DEPLOY.md) for general
deployment.

## Files

| File | Purpose |
|---|---|
| `docker-compose.selfhosted.yml` | Postgres + vLLM (LLM) + TEI (embeddings) + backend. |
| `env.saas.example` | Cloud baseline; confidential docs → self-hosted. |
| `env.single-tenant.example` | Self-hosted baseline for one customer. |
| `env.air-gapped.example` | Fully private; no cloud providers (also for `private_cloud`). |

## Quickstart (self-hosted)

```bash
cd deploy
cp env.air-gapped.example .env          # then fill JWT_SECRET_KEY + MASTER_KEK
docker compose -f docker-compose.selfhosted.yml --env-file .env up -d
# vLLM may take several minutes to load the model on first boot (healthcheck waits).
```

The `backend` service runs `alembic upgrade head` then serves on `:8000`. Register a
tenant (`POST /auth/register`), upload a `confidential` document, and `POST /query` — the
verifier/synthesizer `LLM_CALL` audit events will show `profile=self_hosted`.

## Notes

- **GPU**: the `vllm` service needs an NVIDIA GPU + the NVIDIA Container Toolkit. For a
  CPU-only smoke test, swap it for an `ollama/ollama` service and point `LLM_BASE_URL` at
  `http://ollama:11434/v1`.
- **Embeddings**: this stack uses TEI (an OpenAI-compatible embedding server) to keep
  torch out of the backend image. To embed in-process instead, build the backend with
  `uv sync --extra local` and set `EMBEDDING_PROVIDER=sentence_transformers`.
- **Embedding dimension**: a non-OpenAI model usually has a different vector size. Set
  `EMBEDDING_DIMENSIONS` to match the model and ingest into a **fresh** database — the
  pgvector column dimension is fixed at ingestion time.
- **Air-gapped**: pre-pull all images and model weights; nothing here needs outbound
  internet at runtime once cached.
