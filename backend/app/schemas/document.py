"""Document API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import ContentVisibility, IngestionStatus, SalesContentType


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    owner_user_id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    content_type: SalesContentType
    visibility: ContentVisibility
    status: IngestionStatus
    error_message: str | None
    page_count: int | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime
    # ICP/segment tags (Phase B); empty when untagged. Populated by the router.
    segment_ids: list[uuid.UUID] = []


class UploadResponse(BaseModel):
    """Returned (202) immediately after upload; processing continues in the background."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "filename": "hr_policy.pdf",
                    "status": "pending",
                }
            ]
        }
    )

    id: uuid.UUID
    filename: str
    status: IngestionStatus
