"""Schemas for manager-curated content: ramp topics + the saved objection library."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ── Ramp topics (new-rep onboarding checklist) ──────────────────────────────────────
class RampTopicCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    suggested_question: str = Field(min_length=1, max_length=1000)
    sort_order: int = 0


class RampTopicUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    suggested_question: str | None = Field(default=None, min_length=1, max_length=1000)
    sort_order: int | None = None


class RampTopicRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    suggested_question: str
    sort_order: int
    created_at: datetime


# ── Saved objections (objection-lookup quick mode) ──────────────────────────────────
class SavedObjectionCreate(BaseModel):
    label: str = Field(min_length=1, max_length=255)
    prompt: str = Field(min_length=1, max_length=1000)
    sort_order: int = 0


class SavedObjectionUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    prompt: str | None = Field(default=None, min_length=1, max_length=1000)
    sort_order: int | None = None


class SavedObjectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    prompt: str
    sort_order: int
    created_at: datetime
