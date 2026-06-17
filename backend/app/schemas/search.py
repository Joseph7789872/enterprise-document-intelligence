"""Search API schemas."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResult(BaseModel):
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    chunk_index: int
    score: float  # final re-rank score; higher is more relevant
    methods: list[str]  # retrieval methods that surfaced this chunk, e.g. ["bm25","vector"]
    snippet: str
    filename: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
