"""Apply a starter template to a tenant.

Bulk-creates segments, ramp topics, and saved objections (tagged by segment) from an
in-repo :mod:`app.services.templates_data` definition. Idempotent: anything whose
name/title/label already exists for the tenant is skipped, so re-applying a template (or
applying one that overlaps existing content) never creates duplicates. Ordering matters —
segments are created first so objection tags can resolve against them in the same call.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.models.ramp_topic import RampTopic
from app.models.saved_objection import SavedObjection
from app.models.segment import Segment
from app.services import segment_service
from app.services.templates_data import TEMPLATES, Template


@dataclass
class _Bucket:
    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


@dataclass
class TemplateApplyResult:
    template_key: str
    segments: _Bucket
    ramp_topics: _Bucket
    objections: _Bucket


def get_template(template_key: str) -> Template:
    tpl = TEMPLATES.get(template_key)
    if tpl is None:
        raise NotFoundError(f"Unknown template '{template_key}'.")
    return tpl


async def apply_template(
    db: AsyncSession, *, tenant_id: uuid.UUID, template_key: str
) -> TemplateApplyResult:
    tpl = get_template(template_key)
    result = TemplateApplyResult(
        template_key=template_key, segments=_Bucket(), ramp_topics=_Bucket(), objections=_Bucket()
    )

    # 1) Segments first — keyed by name so objections can tag them below. Skip existing.
    seg_by_name: dict[str, uuid.UUID] = {
        name: sid
        for sid, name in (
            await db.execute(
                select(Segment.id, Segment.name).where(Segment.tenant_id == tenant_id)
            )
        ).all()
    }
    for order, name in enumerate(tpl.segments):
        if name in seg_by_name:
            result.segments.skipped.append(name)
            continue
        seg = Segment(tenant_id=tenant_id, name=name, sort_order=order)
        db.add(seg)
        await db.flush()
        seg_by_name[name] = seg.id
        result.segments.created.append(name)

    # 2) Ramp topics — skip by title (no unique constraint, so check explicitly).
    existing_titles = set(
        (
            await db.scalars(select(RampTopic.title).where(RampTopic.tenant_id == tenant_id))
        ).all()
    )
    for order, (title, question) in enumerate(tpl.ramp_topics):
        if title in existing_titles:
            result.ramp_topics.skipped.append(title)
            continue
        db.add(
            RampTopic(
                tenant_id=tenant_id, title=title, suggested_question=question, sort_order=order
            )
        )
        result.ramp_topics.created.append(title)

    # 3) Objections — skip by label; tag with segments resolved by name.
    existing_labels = set(
        (
            await db.scalars(
                select(SavedObjection.label).where(SavedObjection.tenant_id == tenant_id)
            )
        ).all()
    )
    for order, obj in enumerate(tpl.objections):
        if obj.label in existing_labels:
            result.objections.skipped.append(obj.label)
            continue
        row = SavedObjection(
            tenant_id=tenant_id, label=obj.label, prompt=obj.prompt, sort_order=order
        )
        db.add(row)
        await db.flush()
        seg_ids = [seg_by_name[s] for s in obj.segments if s in seg_by_name]
        if seg_ids:
            await segment_service.replace_objection_segments(
                db, tenant_id=tenant_id, objection_id=row.id, segment_ids=seg_ids
            )
        result.objections.created.append(obj.label)

    return result
