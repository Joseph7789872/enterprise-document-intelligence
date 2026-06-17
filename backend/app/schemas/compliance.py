"""Compliance + DSR schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.data_subject_request import DSRStatus, DSRType


class DSRCreate(BaseModel):
    subject_email: EmailStr
    subject_user_id: uuid.UUID | None = None
    request_type: DSRType


class DSRRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject_email: str
    subject_user_id: uuid.UUID | None
    request_type: DSRType
    status: DSRStatus
    result: dict | None
    created_at: datetime
    completed_at: datetime | None


class RetentionPolicyUpsert(BaseModel):
    resource_type: str = Field(min_length=1, max_length=100)
    retention_days: int = Field(ge=1)
    description: str | None = Field(default=None, max_length=500)


class RetentionPolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    resource_type: str
    retention_days: int
    description: str | None
