# Self-Hosted & Air-Gapped Deployment

EDIP can run with **no third-party model providers** — every inference dependency inside
the customer's network — for confidential workloads and offline / air-gapped environments.
For the general deployment guide and modes table see [DEPLOY.md](DEPLOY.md).

## Self-hosted LLM (vLLM recommended)

Any OpenAI-compatible endpoint works:

```env
LLM_PROVIDER=openai_compatible        # or keep `anthropic` as the SaaS baseline
LLM_BASE_URL=http://vllm:8000/v1
LLM_API_KEY=                          # optional; Ollama needs none
SELF_HOSTED_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
```

- **vLLM** (primary): `vllm/vllm-openai` serves `/v1` with high GPU throughput.
- **Ollama** (CPU-friendly alternative): set `LLM_BASE_URL=http://ollama:11434/v1`,
  `SELF_HOSTED_LLM_MODEL=llama3.1`.

**Structured outputs** (the Planner/Verifier nodes) use a portable JSON-mode + tolerant
parse, so they work across vLLM and Ollama. Smaller models occasionally emit invalid JSON;
the workflow **degrades gracefully** — the planner falls back to the raw question and the
verifier to low confidence (routing the answer to human review) rather than emitting
something ungrounded.

## Local / self-hosted embeddings

Two options:

1. **OpenAI-compatible embedding server** (keeps torch out of the backend image):
   ```env
   EMBEDDING_PROVIDER=openai_compatible
   EMBEDDING_BASE_URL=http://tei:80/v1     # HF text-embeddings-inference, vLLM, etc.
   EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
   EMBEDDING_DIMENSIONS=384
   ```
2. **In-process** (no embedding server; build the backend with `--extra local`):
   ```env
   EMBEDDING_PROVIDER=sentence_transformers
   LOCAL_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
   EMBEDDING_DIMENSIONS=384
   ```

> **Dimension caveat.** The pgvector column dimension is fixed when documents are
> ingested. A model whose output size differs from OpenAI's 3072 requires
> `EMBEDDING_DIMENSIONS` set to match **and a fresh database** (re-ingest). Mixing
> dimensions in one database corrupts vector search; the app logs a warning when a local
> provider is selected but `EMBEDDING_DIMENSIONS` is still 3072.

## Classification-aware routing & the fail-closed guarantee

Routing merges three inputs, most authoritative first:

1. **Deployment mode** — `private_cloud`/`air_gapped` force self-hosted for everything.
2. **Tenant policy** — `require_self_hosted_llm` (set via `PUT /admin/tenant/settings`)
   forces self-hosted for that tenant.
3. **Document classification** — documents at/above `sensitive_classification`
   (`confidential` by default, per-tenant overridable to `privileged`) route to
   self-hosted.

The planner runs *before* retrieval (no document yet) and uses the baseline profile; the
verifier and synthesizer carry the highest classification among the retrieved documents.

**Fail-closed:** if a route requires the self-hosted profile but `LLM_BASE_URL` is unset,
the request returns **503** and an `llm.route_denied` audit event is recorded — it is
never downgraded to the cloud. Inspect the live posture at `GET /compliance/config`
(`feature_flags`, `llm_routing`, `sub_processors` reflect the *effective* providers).

## Reference stack (Docker Compose)

[`deploy/`](deploy/) contains the self-hosted topology and per-mode env templates:

```bash
cd deploy
cp env.air-gapped.example .env        # fill JWT_SECRET_KEY + MASTER_KEK
docker compose -f docker-compose.selfhosted.yml --env-file .env up -d
```

Services: `postgres` (pgvector) + `vllm` (LLM) + `tei` (embeddings) + `backend` (runs
migrations then serves) + `frontend`. The backend boots only if no cloud provider is
configured (the air-gapped validator).

## Air-gapped notes

- **GPU**: the `vllm` service needs an NVIDIA GPU + the NVIDIA Container Toolkit. For a
  CPU-only smoke test, swap in an `ollama/ollama` service.
- **No egress at runtime**: pre-pull all images and model weights into the environment;
  nothing in the stack needs outbound internet once cached.
- **Disable cloud-only features**: `OBSERVABILITY_PROVIDER=fake` (or a self-hosted
  Langfuse), `EVALS_PROVIDER=fake`, `RERANKER_PROVIDER=fake` (or the local cross-encoder
  via `--extra reranker`). The startup validator enforces the cloud-free invariant.
