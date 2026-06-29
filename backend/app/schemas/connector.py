"""Connector API schemas (Phase C)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.document import BatchItemResult


class NotionTokenRequest(BaseModel):
    token: str = Field(min_length=1, max_length=500)


class NotionStatus(BaseModel):
    """Connection status — deliberately never includes the token."""

    connected: bool
    enabled: bool = False
    last_synced_at: datetime | None = None


class NotionSyncResponse(BaseModel):
    # One result per synced page (filename = page title).
    results: list[BatchItemResult]
