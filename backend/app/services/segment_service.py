"""Segment tagging helpers — shared by the documents and objections routers.

All operations are tenant-scoped. ``replace_*_segments`` validate that every supplied
segment belongs to the tenant before writing join rows, so a caller can never tag content
with another tenant's segment.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.models.document_segment import DocumentSegment
from app.models.objection_segment import ObjectionSegment
from app.models.segment import Segment


async def validate_segment_ids(
    db: AsyncSession, *, tenant_id: uuid.UUID, segment_ids: Iterable[uuid.UUID]
) -> list[uuid.UUID]:
    """Return the de-duplicated ids, raising NotFoundError if any is not this tenant's."""
    wanted = list(dict.fromkeys(segment_ids))  # de-dup, preserve order
    if not wanted:
        return []
    rows = await db.scalars(
        select(Segment.id).where(Segment.tenant_id == tenant_id, Segment.id.in_(wanted))
    )
    found = set(rows.all())
    missing = [sid for sid in wanted if sid not in found]
    if missing:
        raise NotFoundError(f"Unknown segment id(s): {', '.join(str(m) for m in missing)}.")
    return wanted


async def replace_document_segments(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_ids: Iterable[uuid.UUID],
) -> list[uuid.UUID]:
    valid = await validate_segment_ids(db, tenant_id=tenant_id, segment_ids=segment_ids)
    existing = await db.scalars(
        select(DocumentSegment).where(
            DocumentSegment.tenant_id == tenant_id, DocumentSegment.document_id == document_id
        )
    )
    for row in existing.all():
        await db.delete(row)
    for sid in valid:
        db.add(DocumentSegment(tenant_id=tenant_id, document_id=document_id, segment_id=sid))
    await db.flush()
    return valid


async def replace_objection_segments(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    objection_id: uuid.UUID,
    segment_ids: Iterable[uuid.UUID],
) -> list[uuid.UUID]:
    valid = await validate_segment_ids(db, tenant_id=tenant_id, segment_ids=segment_ids)
    existing = await db.scalars(
        select(ObjectionSegment).where(
            ObjectionSegment.tenant_id == tenant_id, ObjectionSegment.objection_id == objection_id
        )
    )
    for row in existing.all():
        await db.delete(row)
    for sid in valid:
        db.add(ObjectionSegment(tenant_id=tenant_id, objection_id=objection_id, segment_id=sid))
    await db.flush()
    return valid


async def segments_for_objections(
    db: AsyncSession, *, tenant_id: uuid.UUID, objection_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Batch-load segment ids per objection (avoids an N+1 on the list endpoint)."""
    out: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    if not objection_ids:
        return out
    rows = await db.execute(
        select(ObjectionSegment.objection_id, ObjectionSegment.segment_id).where(
            ObjectionSegment.tenant_id == tenant_id,
            ObjectionSegment.objection_id.in_(objection_ids),
        )
    )
    for objection_id, segment_id in rows.all():
        out[objection_id].append(segment_id)
    return out


async def segments_for_documents(
    db: AsyncSession, *, tenant_id: uuid.UUID, document_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    out: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    if not document_ids:
        return out
    rows = await db.execute(
        select(DocumentSegment.document_id, DocumentSegment.segment_id).where(
            DocumentSegment.tenant_id == tenant_id,
            DocumentSegment.document_id.in_(document_ids),
        )
    )
    for document_id, segment_id in rows.all():
        out[document_id].append(segment_id)
    return out
