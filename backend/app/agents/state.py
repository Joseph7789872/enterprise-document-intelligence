"""Agent workflow state.

``AgentState`` is the LangGraph state dict threaded through the nodes. The Pydantic
models are the typed values it carries and the structured-output schemas the Planner
and Verifier return.

Security: ``RetrievedChunk.text`` holds decrypted chunk content and exists only in
memory for the duration of a request — it is never persisted in the clear and the
graph is not checkpointed to disk.
"""

from __future__ import annotations

import uuid
from typing import TypedDict

from pydantic import BaseModel, Field

QueryStatus = str  # one of QueryState values below (kept loose for the TypedDict)


class QueryState:
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    FAILED = "failed"


# ── Structured-output schemas (Planner / Verifier) ──────────────────────────────

class SubQueryPlan(BaseModel):
    """Planner output: the question decomposed into focused sub-queries."""

    subqueries: list[str] = Field(default_factory=list)


class Verification(BaseModel):
    """Verifier output: confidence + grounding + confidentiality assessment."""

    confidence: float = Field(ge=0.0, le=1.0)
    is_grounded: bool
    confidentiality_concern: bool = False
    issues: list[str] = Field(default_factory=list)


# ── In-flight value types ────────────────────────────────────────────────────────

class RetrievedChunk(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    text: str  # decrypted, in-memory only
    score: float
    filename: str


class Citation(BaseModel):
    marker: int  # the [n] used in the answer
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    filename: str
    snippet: str


# ── LangGraph state ────────────────────────────────────────────────────────────────

class AgentState(TypedDict, total=False):
    # Request context (set by the runner before invocation).
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    trace_id: str | None
    question: str
    # Produced by nodes.
    subqueries: list[str]
    chunks: list[RetrievedChunk]
    verification: Verification
    requires_approval: bool
    answer: str
    citations: list[Citation]
    status: QueryStatus
    error: str | None
