"""Chunking via LlamaIndex's SentenceSplitter.

Splits extracted text into ~512-token chunks with overlap, preserving sentence
boundaries where possible. Token counts use the splitter's tokenizer so they line up
with what the embedding model sees.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.core.config import settings


@dataclass(frozen=True)
class Chunk:
    text: str
    token_count: int
    metadata: dict


@lru_cache
def _token_counter():  # type: ignore[no-untyped-def]
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    return lambda s: len(enc.encode(s))


@lru_cache
def _splitter():  # type: ignore[no-untyped-def]
    from llama_index.core.node_parser import SentenceSplitter

    return SentenceSplitter(
        chunk_size=settings.CHUNK_SIZE_TOKENS,
        chunk_overlap=settings.CHUNK_OVERLAP_TOKENS,
        tokenizer=_token_counter_encode(),
    )


@lru_cache
def _token_counter_encode():  # type: ignore[no-untyped-def]
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    return enc.encode


def split(text: str) -> list[Chunk]:
    """Split ``text`` into chunks. Returns an empty list for blank input."""
    if not text.strip():
        return []
    pieces = _splitter().split_text(text)
    count_tokens = _token_counter()
    return [
        Chunk(text=piece, token_count=count_tokens(piece), metadata={"chunk_index": i})
        for i, piece in enumerate(pieces)
    ]
