"""Query API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.query import QueryStatus


class QueryRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"question": "What is our remote-work policy?"}]
        }
    )

    question: str = Field(min_length=1, max_length=4000)


class CitationOut(BaseModel):
    marker: int
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    filename: str
    snippet: str


class AnswerResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "query_id": "3f1a8b2c-4d5e-6f70-8192-a3b4c5d6e7f8",
                    "status": "completed",
                    "requires_approval": False,
                    "answer": "Employees may work remotely up to three days per week. [1]",
                    "citations": [
                        {
                            "marker": 1,
                            "document_id": "11111111-1111-1111-1111-111111111111",
                            "chunk_id": "22222222-2222-2222-2222-222222222222",
                            "filename": "hr_policy.pdf",
                            "snippet": "Remote work is permitted up to three days per week...",
                        }
                    ],
                    "confidence": 0.93,
                }
            ]
        }
    )

    query_id: uuid.UUID
    status: QueryStatus
    requires_approval: bool
    answer: str | None
    citations: list[CitationOut]
    confidence: float | None


class QueryRead(BaseModel):
    id: uuid.UUID
    status: QueryStatus
    question: str
    answer: str | None
    citations: list[CitationOut]
    confidence: float | None
    created_at: datetime
