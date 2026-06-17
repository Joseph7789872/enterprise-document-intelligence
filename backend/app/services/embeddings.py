"""Embedding providers.

``Embedder`` is the interface the rest of the app codes against. ``OpenAIEmbedder``
calls OpenAI's ``text-embedding-3-large`` (at the configured dimensionality);
``FakeEmbedder`` produces deterministic unit vectors from a hash of the text, so the
test suite and key-less development environments work without any network calls or
data egress. ``get_embedder()`` picks one based on settings.
"""

from __future__ import annotations

import hashlib
import logging
import math
from functools import lru_cache
from typing import Protocol

from app.core.config import settings


class Embedder(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class FakeEmbedder:
    """Deterministic, network-free embeddings for dev/test.

    Each text maps to a fixed pseudo-random unit vector seeded by its SHA-256, so
    identical text always yields identical vectors and cosine similarity is stable.
    """

    def __init__(self, dim: int) -> None:
        self._dim = dim

    def _vector(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode("utf-8")).digest()
        # Expand the 32-byte digest deterministically to `dim` floats.
        vals: list[float] = []
        counter = 0
        while len(vals) < self._dim:
            block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for b in block:
                vals.append((b / 255.0) * 2.0 - 1.0)  # in [-1, 1]
                if len(vals) == self._dim:
                    break
            counter += 1
        norm = math.sqrt(sum(v * v for v in vals)) or 1.0
        return [v / norm for v in vals]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class OpenAIEmbedder:
    """OpenAI (or any OpenAI-compatible) embeddings via the async SDK.

    Passing ``base_url`` points the client at a self-hosted endpoint (vLLM / Ollama /
    HuggingFace text-embeddings-inference), so the same code serves cloud and
    self-hosted embeddings (Phase 7). ``dimensions`` is forwarded only when set, since
    self-hosted servers may not accept the parameter.
    """

    _BATCH = 128

    def __init__(
        self,
        model: str,
        dimensions: int,
        api_key: str,
        *,
        base_url: str = "",
        send_dimensions: bool = True,
    ) -> None:
        from openai import AsyncOpenAI

        self._model = model
        self._dimensions = dimensions
        self._send_dimensions = send_dimensions
        self._client = AsyncOpenAI(
            api_key=api_key or "not-needed", base_url=base_url or None
        )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for start in range(0, len(texts), self._BATCH):
            batch = texts[start : start + self._BATCH]
            if self._send_dimensions:
                resp = await self._client.embeddings.create(
                    model=self._model, input=batch, dimensions=self._dimensions
                )
            else:
                resp = await self._client.embeddings.create(model=self._model, input=batch)
            out.extend(item.embedding for item in resp.data)
        return out

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]


class LocalEmbedder:
    """In-process embeddings via sentence-transformers (Phase 7, optional [local] extra).

    For fully air-gapped deployments with no embedding server: the model is loaded once
    and inference runs in a worker thread so the event loop is never blocked. Vectors are
    L2-normalized to match the cosine-similarity assumptions elsewhere.
    """

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import anyio

        def _encode() -> list[list[float]]:
            vecs = self._model.encode(texts, normalize_embeddings=True)
            return [list(map(float, v)) for v in vecs]

        return await anyio.to_thread.run_sync(_encode)

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_texts([text]))[0]


@lru_cache
def get_embedder() -> Embedder:
    """Return the configured embedder (cached per process)."""
    provider = settings.effective_embedding_provider
    if provider == "fake":
        return FakeEmbedder(dim=settings.EMBEDDING_DIMENSIONS)
    if provider == "sentence_transformers":
        _warn_dimension_mismatch()
        return LocalEmbedder(settings.LOCAL_EMBEDDING_MODEL)
    if provider == "openai_compatible":
        _warn_dimension_mismatch()
        # Self-hosted servers often reject the `dimensions` param — omit it.
        return OpenAIEmbedder(
            model=settings.EMBEDDING_MODEL,
            dimensions=settings.EMBEDDING_DIMENSIONS,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.EMBEDDING_BASE_URL,
            send_dimensions=False,
        )
    return OpenAIEmbedder(
        model=settings.EMBEDDING_MODEL,
        dimensions=settings.EMBEDDING_DIMENSIONS,
        api_key=settings.OPENAI_API_KEY,
    )


def _warn_dimension_mismatch() -> None:
    """Warn when a non-OpenAI embedder is selected but EMBEDDING_DIMENSIONS is still the
    OpenAI default (3072). The pgvector column dimension is fixed at ingestion, so a
    different-dimension model needs EMBEDDING_DIMENSIONS set to match AND a fresh DB."""
    if settings.EMBEDDING_DIMENSIONS == 3072:
        logging.getLogger("app.embeddings").warning(
            "EMBEDDING_PROVIDER=%s but EMBEDDING_DIMENSIONS is still 3072 (the OpenAI "
            "default). Set EMBEDDING_DIMENSIONS to the local model's output size and "
            "re-ingest into a fresh database; mixing dimensions corrupts vector search.",
            settings.EMBEDDING_PROVIDER,
        )
