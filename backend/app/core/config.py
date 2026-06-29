"""Application configuration, sourced from environment variables.

All settings are env-driven (12-factor). In non-development environments the app
fails fast at import time if security-critical secrets are missing or weak, so a
misconfigured deployment never starts serving traffic.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "staging", "production"]

# Sentinel default that must never reach a non-development deployment.
_INSECURE_JWT_DEFAULT = "change-me-dev-only-not-for-production"


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    ENVIRONMENT: Environment = "development"

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://edip:edip_dev_password@localhost:5432/edip"

    # ── Redis (later phases) ────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── Auth (JWT) ──────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = _INSECURE_JWT_DEFAULT
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # ── Encryption (envelope) ─────────────────────────────────────────────────────
    # Base64-encoded 32-byte master KEK. Empty in development falls back to a
    # deterministic dev key (see master_kek_bytes) so tests/local runs work without
    # configuration; required to be a real 32-byte key outside development.
    MASTER_KEK: str = ""
    ENCRYPTION_KEY_VERSION: int = 1

    # ── CORS ──────────────────────────────────────────────────────────────────────
    CORS_ALLOW_ORIGINS: str = "http://localhost:3000"

    # ── Compliance ──────────────────────────────────────────────────────────────────
    AUDIT_LOG_RETENTION_DAYS: int = 2555

    # ── Document ingestion (Phase 1) ──────────────────────────────────────────────────
    MAX_UPLOAD_MB: int = 25
    # Allowed upload extensions (lowercase, no dot). HTML deferred to a later phase.
    ALLOWED_UPLOAD_EXTENSIONS: str = "pdf,docx,txt"

    # Blob storage: "local" (dev) or "s3" (MinIO / S3-compatible).
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    STORAGE_LOCAL_PATH: str = "./var/storage"
    S3_ENDPOINT_URL: str = ""  # e.g. http://localhost:9000 for MinIO; empty = AWS default
    S3_BUCKET: str = "edip-documents"
    S3_REGION: str = "us-east-1"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""

    # Embeddings provider (Phase 1 + Phase 7):
    #   "openai"               — OpenAI cloud (text-embedding-3-large), needs OPENAI_API_KEY.
    #   "openai_compatible"    — a self-hosted OpenAI-compatible endpoint (vLLM/Ollama/TEI)
    #                            at EMBEDDING_BASE_URL; reuses the OpenAI SDK.
    #   "sentence_transformers"— in-process local model (optional [local] extra); no server.
    #   "fake"                 — deterministic dev/test embeddings, no network.
    EMBEDDING_PROVIDER: Literal[
        "openai", "openai_compatible", "sentence_transformers", "fake"
    ] = "openai"
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    EMBEDDING_DIMENSIONS: int = 3072
    # Base URL for a self-hosted OpenAI-compatible embeddings server (Phase 7), e.g.
    # http://vllm:8000/v1 or http://tei:80/v1. Empty = OpenAI's default endpoint.
    EMBEDDING_BASE_URL: str = ""
    # In-process sentence-transformers model id (Phase 7). 384-dim by default — set
    # EMBEDDING_DIMENSIONS to match and re-ingest when switching away from OpenAI's 3072.
    LOCAL_EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # Chunking (LlamaIndex SentenceSplitter), in tokens.
    CHUNK_SIZE_TOKENS: int = 512
    CHUNK_OVERLAP_TOKENS: int = 50

    # ── Hybrid retrieval + re-ranking (Phase 2) ───────────────────────────────────────
    # Candidate counts pulled from each retrieval method before merge + re-rank.
    HYBRID_VECTOR_CANDIDATES: int = 20
    HYBRID_BM25_CANDIDATES: int = 20
    FINAL_TOP_K: int = 6
    ENABLE_BM25: bool = True
    FTS_LANGUAGE: str = "english"  # PostgreSQL text-search configuration

    # Re-ranker: "cross_encoder" (sentence-transformers) or "fake" (deterministic dev/test).
    RERANKER_PROVIDER: Literal["cross_encoder", "fake"] = "cross_encoder"
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # Blend factor: 1.0 = pure cross-encoder score; <1.0 mixes in the normalized
    # hybrid (vector/BM25) score.
    RERANK_WEIGHT: float = 1.0

    # ── Multi-agent workflow + LLM (Phase 3) ──────────────────────────────────────────
    # Baseline ("cloud") LLM provider. v1 default: "openai_compatible" pointed at OpenAI
    # (set LLM_BASE_URL=https://api.openai.com/v1 + LLM_API_KEY). The Claude path is kept
    # and fully supported — set LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY, and the
    # *_MODEL ids below to Claude models (e.g. "claude-opus-4-8").
    #   "openai_compatible" — OpenAI or any OpenAI-compatible endpoint (vLLM/Ollama/TGI).
    #   "anthropic"         — real Claude via the official SDK (needs ANTHROPIC_API_KEY).
    #   "fake"              — deterministic, offline dev/test.
    LLM_PROVIDER: Literal["anthropic", "openai_compatible", "fake"] = "openai_compatible"
    ANTHROPIC_API_KEY: str = ""
    # Per-node model ids for the baseline profile. Defaults target OpenAI; set Claude ids
    # here when LLM_PROVIDER="anthropic".
    PLANNER_MODEL: str = "gpt-4o"
    VERIFIER_MODEL: str = "gpt-4o"
    SYNTHESIZER_MODEL: str = "gpt-4o"
    SYNTHESIS_MAX_TOKENS: int = 4096
    # Below this verifier confidence (or on a confidentiality flag), answers route to
    # human review instead of being delivered autonomously — only when ENABLE_HUMAN_REVIEW
    # is on (see the v1 feature flags below).
    CONFIDENCE_THRESHOLD: float = 0.6
    MAX_SUBQUERIES: int = 4

    # ── V1 product feature flags (sales-enablement) ───────────────────────────────────
    # Enterprise-only surfaces are kept in the codebase but switched off in the v1 SaaS
    # product. These default ON so the dev environment and the full test suite still
    # exercise them; the production v1 deployment sets them OFF (via env) to hide the
    # enterprise/compliance surface. (The MCP server lives in services/mcp_tools.py and is
    # not mounted on the REST app, so it needs no router flag.)
    #
    # The full "v1 enterprise-off" profile (all set false in deploy/fly/backend.fly.toml):
    #   ENABLE_COMPLIANCE, ENABLE_EVALS, ENABLE_HUMAN_REVIEW, ENABLE_AUDIT,
    #   ENABLE_ENTERPRISE_ADMIN.
    ENABLE_COMPLIANCE: bool = True  # /compliance (GDPR/DSR) router + SIEM audit export
    ENABLE_EVALS: bool = True  # /evals run-history router
    # Low-confidence / confidentiality human-approval gate. When OFF, low-confidence
    # answers are still delivered (with their confidence surfaced) rather than held —
    # an honest "here's what I found, I'm not fully sure" instead of a human gate.
    ENABLE_HUMAN_REVIEW: bool = True
    # Audit-log read + SIEM-ready export surface (/audit). The app always WRITES audit
    # events regardless; this only gates the read/export endpoints. OFF in the v1 product.
    ENABLE_AUDIT: bool = True
    # Enterprise admin surfaces: org groups, programmatic API keys, and per-tenant LLM
    # routing policy (/admin/groups, /admin/api-keys, /admin/tenant/settings). OFF in v1.
    ENABLE_ENTERPRISE_ADMIN: bool = True

    # ── Phase C: content connectors (URL import + Notion) ─────────────────────────────
    # External egress: fetching arbitrary URLs and the Notion API. OFF by default in
    # production (a deliberate, reviewed surface); the test suite pins it ON in conftest.
    ENABLE_CONNECTORS: bool = False
    # Hard cap on bytes fetched for a URL import (defends against huge/streaming pages).
    URL_IMPORT_MAX_BYTES: int = 5 * 1024 * 1024
    NOTION_API_BASE: str = "https://api.notion.com/v1"

    # ── Phase D: outbound transactional email (invites + password reset) ──────────────
    # "smtp" (aiosmtplib against any relay) or "fake" (in-memory outbox; the offline
    # default for dev/CI). Resolved by effective_email_provider, which falls back to
    # "fake" in development when SMTP_HOST is unset.
    EMAIL_PROVIDER: Literal["smtp", "fake"] = "smtp"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "Sales Assistant <noreply@example.com>"
    SMTP_STARTTLS: bool = True
    # Public base URL of the frontend — used to build invite/reset links in emails.
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    INVITE_TOKEN_TTL_HOURS: int = 72
    RESET_TOKEN_TTL_HOURS: int = 2

    # ── Phase D: self-serve signup ────────────────────────────────────────────────────
    # Gates the public POST /auth/register endpoint + the signup page. ON for the SaaS
    # product; turn OFF for single-tenant / private / air-gapped builds.
    ENABLE_SIGNUP: bool = True

    # ── Phase D: billing + plan limits ────────────────────────────────────────────────
    # OFF by default (like ENABLE_CONNECTORS): plan-limit enforcement only *activates*
    # when this is on. The test suite pins it ON in conftest and drives a FakeBilling
    # provider — no Stripe, no network.
    ENABLE_BILLING: bool = False
    BILLING_PROVIDER: Literal["stripe", "fake"] = "stripe"
    STRIPE_API_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    # Stripe price ids per paid plan (from your Stripe dashboard). Referenced by
    # services/plans_data.py; empty until you wire real Stripe products.
    STRIPE_PRICE_PRO: str = ""
    STRIPE_PRICE_BUSINESS: str = ""
    # Plan assigned to a tenant at signup (see services/plans_data.py).
    DEFAULT_PLAN_KEY: str = "trial"

    # ── Self-hosted LLM + deployment modes (Phase 7) ──────────────────────────────────
    # The self-hosted "profile" used by the model router for sensitive documents (and as
    # the baseline when LLM_PROVIDER=openai_compatible / in private/air-gapped modes).
    # Configured iff LLM_BASE_URL is set — an OpenAI-compatible endpoint (vLLM, Ollama,
    # text-generation-inference). LLM_API_KEY is optional (Ollama needs none).
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""
    # One model id served by the self-hosted endpoint, used for every node on that
    # profile (e.g. "Qwen/Qwen2.5-7B-Instruct" for vLLM, "llama3.1" for Ollama).
    SELF_HOSTED_LLM_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"

    # Deployment mode shapes routing + the fail-fast validators below:
    #   "saas"          — multi-tenant cloud; classification/tenant routing is in play.
    #   "single_tenant" — one tenant, self-hosted profile is the baseline for everything.
    #   "private_cloud" — customer's cloud, self-hosted everything (no third-party egress).
    #   "air_gapped"    — fully offline; the app refuses to start with any cloud provider.
    DEPLOYMENT_MODE: Literal[
        "saas", "single_tenant", "private_cloud", "air_gapped"
    ] = "saas"
    # Documents at/above this classification route to the self-hosted profile (SaaS
    # default policy; per-tenant overridable via tenants.settings).
    SENSITIVE_CLASSIFICATION: Literal["confidential", "privileged"] = "confidential"

    # ── Observability (Langfuse) — Phase 6 ────────────────────────────────────────────
    # "langfuse" (real tracing via the optional [observability] extra + keys) or "fake"
    # (no-op + structured logs; the offline default). Falls back to fake when the extra
    # or keys are absent.
    OBSERVABILITY_PROVIDER: Literal["langfuse", "fake"] = "langfuse"
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = ""
    # Privacy: by default traces carry ONLY metadata (node/model/counts/ids), never
    # prompt/answer/context text. Opt in to full IO capture explicitly.
    LANGFUSE_CAPTURE_IO: bool = False

    # ── Compliance + API security (Phase 6) ───────────────────────────────────────────
    DATA_REGION: str = "us"  # informational data-residency label (e.g. "us", "eu")
    API_KEY_PREFIX: str = "edip"
    RATE_LIMIT_PER_MINUTE: int = 120
    ENABLE_SECURITY_HEADERS: bool = True
    # Content-Security-Policy for API responses. The default is strict (the API serves
    # only JSON); the interactive docs routes get a Swagger-compatible policy automatically.
    CSP_POLICY: str = "default-src 'none'; frame-ancestors 'none'"

    # ── Logging (Phase 8) ─────────────────────────────────────────────────────────────
    # "text" (human-readable, the dev default) or "json" (one structured object per line,
    # SIEM/log-shipper friendly). Both carry the request trace id.
    LOG_FORMAT: Literal["text", "json"] = "text"

    # ── RAGAS evaluation + CI gate (Phase 4) ──────────────────────────────────────────
    # "ragas" (real metrics via an LLM judge — needs the [evals] extra + ANTHROPIC_API_KEY)
    # or "fake" (deterministic lexical scorer for offline dev/test + the always-on gate).
    EVALS_PROVIDER: Literal["ragas", "fake"] = "ragas"
    # RAGAS judge (LLM-as-judge). Separate from the workflow models so eval cost is tunable.
    EVAL_JUDGE_MODEL: str = "claude-sonnet-4-6"
    # Dedicated tenant the eval corpus is ingested into (isolated from real tenants).
    EVAL_TENANT_SLUG: str = "eval-harness"
    EVAL_TENANT_OWNER_EMAIL: str = "owner@eval-harness.internal"
    # Path to the ground-truth dataset, relative to the backend working directory.
    EVAL_DATASET_PATH: str = "../evals/ground_truth.json"
    # Quality thresholds: a run passes only if every mean metric is >= its threshold.
    EVAL_THRESHOLD_FAITHFULNESS: float = 0.7
    EVAL_THRESHOLD_CONTEXT_PRECISION: float = 0.7
    EVAL_THRESHOLD_ANSWER_RELEVANCY: float = 0.7

    # ── Derived helpers ──────────────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOW_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_upload_extensions(self) -> set[str]:
        return {
            e.strip().lower().lstrip(".")
            for e in self.ALLOWED_UPLOAD_EXTENSIONS.split(",")
            if e.strip()
        }

    @property
    def max_upload_bytes(self) -> int:
        return int(self.MAX_UPLOAD_MB * 1024 * 1024)

    @property
    def effective_embedding_provider(self) -> str:
        """Resolve the embedding provider, falling back to 'fake' in development when a
        provider is selected but its prerequisites are missing (mirrors the dev-KEK
        fallback). Outside development this never silently downgrades.

        - openai                → fake when no OPENAI_API_KEY.
        - openai_compatible     → fake when no EMBEDDING_BASE_URL.
        - sentence_transformers → fake when the optional [local] extra isn't importable.
        """
        if self.ENVIRONMENT == "development":
            if self.EMBEDDING_PROVIDER == "openai" and not self.OPENAI_API_KEY:
                return "fake"
            if self.EMBEDDING_PROVIDER == "openai_compatible" and not self.EMBEDDING_BASE_URL:
                return "fake"
            if self.EMBEDDING_PROVIDER == "sentence_transformers":
                import importlib.util

                if importlib.util.find_spec("sentence_transformers") is None:
                    return "fake"
        return self.EMBEDDING_PROVIDER

    @property
    def effective_reranker_provider(self) -> str:
        """Resolve the re-ranker provider, falling back to 'fake' when the
        cross-encoder is selected but ``sentence-transformers`` is not installed
        (the optional [reranker] extra). Avoids hard-failing dev/CI that skip the
        heavy ML dependency."""
        if self.RERANKER_PROVIDER == "cross_encoder":
            import importlib.util

            if importlib.util.find_spec("sentence_transformers") is None:
                return "fake"
        return self.RERANKER_PROVIDER

    @property
    def effective_llm_provider(self) -> str:
        """Resolve the baseline LLM provider, falling back to 'fake' in development when
        the selected provider's prerequisites are missing (mirrors the embedding
        provider). Outside development this never silently downgrades.

        - anthropic         → fake when no ANTHROPIC_API_KEY.
        - openai_compatible → fake when no LLM_BASE_URL.
        """
        if self.ENVIRONMENT == "development":
            if self.LLM_PROVIDER == "anthropic" and not self.ANTHROPIC_API_KEY:
                return "fake"
            if self.LLM_PROVIDER == "openai_compatible" and not self.LLM_BASE_URL:
                return "fake"
        return self.LLM_PROVIDER

    @property
    def effective_email_provider(self) -> str:
        """Resolve the email provider, falling back to 'fake' in development when SMTP is
        selected but no SMTP_HOST is configured (mirrors the embedding/LLM fallbacks).
        Outside development this never silently downgrades — the production validator
        requires SMTP_HOST when EMAIL_PROVIDER=smtp."""
        dev = self.ENVIRONMENT == "development"
        if dev and self.EMAIL_PROVIDER == "smtp" and not self.SMTP_HOST:
            return "fake"
        return self.EMAIL_PROVIDER

    @property
    def effective_billing_provider(self) -> str:
        """Resolve the billing provider, falling back to 'fake' when Stripe is selected
        but the optional [billing] extra isn't importable, or (in development) when no
        STRIPE_API_KEY is configured. Keeps the default install + offline suite running
        on the deterministic FakeBillingProvider; the prod validator refuses the silent
        downgrade outside development."""
        if self.BILLING_PROVIDER == "stripe":
            import importlib.util

            if importlib.util.find_spec("stripe") is None:
                return "fake"
            if not self.STRIPE_API_KEY and self.ENVIRONMENT == "development":
                return "fake"
        return self.BILLING_PROVIDER

    @property
    def self_hosted_llm_configured(self) -> bool:
        """True when a self-hosted OpenAI-compatible LLM profile is available to the
        router (an endpoint URL is set). The router fails closed when a sensitive route
        needs this profile and it is not configured."""
        return bool(self.LLM_BASE_URL)

    @property
    def is_air_gapped(self) -> bool:
        return self.DEPLOYMENT_MODE == "air_gapped"

    @property
    def is_fully_private(self) -> bool:
        """Private cloud + air-gapped both keep all inference on the self-hosted profile."""
        return self.DEPLOYMENT_MODE in ("private_cloud", "air_gapped")

    @property
    def feature_flags(self) -> dict[str, bool]:
        """Deployment-posture feature flags surfaced to the compliance config snapshot.

        Each flag reports whether a *cloud / third-party* dependency is in play, so an
        operator (and the /compliance/config endpoint) can see at a glance what leaves
        the customer's infrastructure under the current configuration."""
        return {
            "cloud_llm": self.effective_llm_provider == "anthropic",
            "cloud_embeddings": self.effective_embedding_provider == "openai",
            "cloud_tracing": (
                self.effective_observability_provider == "langfuse"
                and "cloud.langfuse.com" in self.LANGFUSE_HOST
            ),
            "external_subprocessors": (
                self.effective_llm_provider == "anthropic"
                or self.effective_embedding_provider == "openai"
            ),
            "self_hosted_llm": self.self_hosted_llm_configured,
        }

    @property
    def eval_thresholds(self) -> dict[str, float]:
        """The metric → minimum-mean-score gate thresholds, as a dict."""
        return {
            "faithfulness": self.EVAL_THRESHOLD_FAITHFULNESS,
            "context_precision": self.EVAL_THRESHOLD_CONTEXT_PRECISION,
            "answer_relevancy": self.EVAL_THRESHOLD_ANSWER_RELEVANCY,
        }

    @property
    def effective_evals_provider(self) -> str:
        """Resolve the evals provider, falling back to 'fake' when RAGAS is selected
        but the optional [evals] extra isn't importable, or (in development) when no
        ANTHROPIC_API_KEY is configured. The deterministic FakeEvaluator keeps the
        default test suite + always-on PR gate fully offline; the production validator
        below refuses to silently downgrade outside development."""
        if self.EVALS_PROVIDER == "ragas":
            import importlib.util

            if importlib.util.find_spec("ragas") is None:
                return "fake"
            if not self.ANTHROPIC_API_KEY and self.ENVIRONMENT == "development":
                return "fake"
        return self.EVALS_PROVIDER

    @property
    def effective_observability_provider(self) -> str:
        """Resolve the tracing provider, falling back to 'fake' when Langfuse is selected
        but the optional [observability] extra isn't importable or its keys are not
        configured. Keeps the workflow + tests fully offline by default."""
        if self.OBSERVABILITY_PROVIDER == "langfuse":
            import importlib.util

            if importlib.util.find_spec("langfuse") is None:
                return "fake"
            if not (self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY):
                return "fake"
        return self.OBSERVABILITY_PROVIDER

    @property
    def sync_database_url(self) -> str:
        """Synchronous SQLAlchemy URL for Alembic.

        Swaps async drivers for their sync counterparts (asyncpg -> psycopg,
        aiosqlite -> plain sqlite) so migrations run on a synchronous engine.
        """
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg").replace("+aiosqlite", "")

    @property
    def master_kek_bytes(self) -> bytes:
        """The 32-byte master KEK used for envelope encryption.

        In development with no MASTER_KEK set, derive a stable dev key so local runs
        and tests work out of the box. Production validation (below) guarantees a real
        key is present before we reach here.
        """
        if not self.MASTER_KEK:
            # Deterministic, clearly-non-secret development key (32 bytes).
            return b"dev-only-insecure-master-kek-32b"
        raw = base64.b64decode(self.MASTER_KEK)
        if len(raw) != 32:
            raise ValueError("MASTER_KEK must decode to exactly 32 bytes (256 bits).")
        return raw

    # ── Validators ──────────────────────────────────────────────────────────────────
    @field_validator("MASTER_KEK")
    @classmethod
    def _validate_master_kek_format(cls, v: str) -> str:
        if v:
            try:
                decoded = base64.b64decode(v, validate=True)
            except Exception as exc:  # noqa: BLE001 - re-raised with clear message
                raise ValueError("MASTER_KEK must be valid base64.") from exc
            if len(decoded) != 32:
                raise ValueError("MASTER_KEK must decode to exactly 32 bytes (256 bits).")
        return v

    @model_validator(mode="after")
    def _enforce_production_secrets(self) -> Settings:
        """Refuse to run with insecure defaults outside development."""
        if self.ENVIRONMENT != "development":
            problems: list[str] = []
            if self.JWT_SECRET_KEY == _INSECURE_JWT_DEFAULT or len(self.JWT_SECRET_KEY) < 32:
                problems.append("JWT_SECRET_KEY must be set to a strong (>=32 char) secret.")
            if not self.MASTER_KEK:
                problems.append("MASTER_KEK must be set (base64-encoded 32-byte key).")
            if self.EMBEDDING_PROVIDER == "openai" and not self.OPENAI_API_KEY:
                problems.append("OPENAI_API_KEY must be set when EMBEDDING_PROVIDER=openai.")
            if self.LLM_PROVIDER == "anthropic" and not self.ANTHROPIC_API_KEY:
                problems.append("ANTHROPIC_API_KEY must be set when LLM_PROVIDER=anthropic.")
            if self.EVALS_PROVIDER == "ragas" and not self.ANTHROPIC_API_KEY:
                problems.append("ANTHROPIC_API_KEY must be set when EVALS_PROVIDER=ragas.")
            if self.EMAIL_PROVIDER == "smtp" and not self.SMTP_HOST:
                problems.append("SMTP_HOST must be set when EMAIL_PROVIDER=smtp.")
            if self.ENABLE_BILLING and self.BILLING_PROVIDER == "stripe":
                if not self.STRIPE_API_KEY:
                    problems.append("STRIPE_API_KEY must be set when ENABLE_BILLING and BILLING_PROVIDER=stripe.")  # noqa: E501
                if not self.STRIPE_WEBHOOK_SECRET:
                    problems.append("STRIPE_WEBHOOK_SECRET must be set when ENABLE_BILLING and BILLING_PROVIDER=stripe.")  # noqa: E501
            if problems:
                raise ValueError(
                    f"Insecure configuration for ENVIRONMENT={self.ENVIRONMENT}: "
                    + " ".join(problems)
                )
        return self

    @model_validator(mode="after")
    def _enforce_deployment_mode(self) -> Settings:
        """Air-gapped deployments must not select any cloud / third-party provider.

        This is the load-bearing guarantee behind "no data leaves customer infra": the
        app refuses to start if a cloud LLM, cloud embeddings, hosted Langfuse, or a
        cloud RAGAS judge is configured under DEPLOYMENT_MODE=air_gapped. private_cloud
        is treated identically for inference providers."""
        if self.DEPLOYMENT_MODE not in ("air_gapped", "private_cloud"):
            return self
        problems: list[str] = []
        if self.LLM_PROVIDER == "anthropic":
            problems.append("LLM_PROVIDER must be 'openai_compatible' (self-hosted), not 'anthropic'.")  # noqa: E501
        if self.LLM_PROVIDER == "openai_compatible" and not self.LLM_BASE_URL:
            problems.append("LLM_BASE_URL must point at the self-hosted endpoint.")
        if self.EMBEDDING_PROVIDER == "openai":
            problems.append(
                "EMBEDDING_PROVIDER must be 'openai_compatible' or 'sentence_transformers'."
            )
        if self.OBSERVABILITY_PROVIDER == "langfuse" and "cloud.langfuse.com" in self.LANGFUSE_HOST:
            problems.append("LANGFUSE_HOST must be a self-hosted instance, not Langfuse Cloud.")
        if self.EVALS_PROVIDER == "ragas":
            problems.append("EVALS_PROVIDER must be 'fake' (a cloud RAGAS judge sends data out).")
        if problems:
            raise ValueError(
                f"Cloud provider selected under DEPLOYMENT_MODE={self.DEPLOYMENT_MODE} "
                "(no data may leave customer infra): " + " ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (import-safe, single instance per process)."""
    return Settings()


settings = get_settings()
