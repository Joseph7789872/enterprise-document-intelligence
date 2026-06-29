"""Manager analytics API schemas (Phase E).

All metadata-only (counts, confidence, citation doc-ids/filenames) — no decrypted question
or answer text appears here. The single decryption path is ``LowConfidenceItem``, served by a
separate endpoint.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class RepActivity(BaseModel):
    user_id: uuid.UUID
    email: str
    role: str
    query_count: int
    answered_count: int
    avg_confidence: float | None
    last_active: datetime | None
    active: bool


class TrendPoint(BaseModel):
    date: str  # ISO calendar date (YYYY-MM-DD)
    count: int


class AnswerQuality(BaseModel):
    total: int
    avg_confidence: float | None
    low_confidence: int
    pending_approval: int
    rejected: int
    with_citations: int
    citation_coverage_pct: float


class CitedDocument(BaseModel):
    document_id: str
    filename: str
    citation_count: int


class UncitedDocument(BaseModel):
    document_id: str
    filename: str
    content_type: str


class UploadsByType(BaseModel):
    content_type: str
    count: int


class ContentInsights(BaseModel):
    most_cited: list[CitedDocument]
    uncited_documents: list[UncitedDocument]
    uploads_by_type: list[UploadsByType]


class AnalyticsOverview(BaseModel):
    days: int
    since: datetime
    total_queries: int
    active_reps: int
    rep_activity: list[RepActivity]
    query_trend: list[TrendPoint]
    answer_quality: AnswerQuality
    content_insights: ContentInsights


class LowConfidenceItem(BaseModel):
    query_id: uuid.UUID
    user_email: str
    confidence: float | None
    question: str
    created_at: datetime
