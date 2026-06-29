"""Schemas for ICP / segments: the managed list + tagging payloads."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SegmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sort_order: int = 0


class SegmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    sort_order: int | None = None


class SegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sort_order: int
    created_at: datetime


class SegmentTagUpdate(BaseModel):
    """Replace the full set of segments tagged on a resource (document/objection)."""

    segment_ids: list[uuid.UUID] = Field(default_factory=list)
