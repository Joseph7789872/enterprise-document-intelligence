"""Starter-template API schemas."""

from __future__ import annotations

from pydantic import BaseModel


class TemplateInfo(BaseModel):
    key: str
    name: str
    description: str
    segment_count: int
    ramp_count: int
    objection_count: int


class TemplateApplyRequest(BaseModel):
    template_key: str


class TemplateBucket(BaseModel):
    created: list[str]
    skipped: list[str]


class TemplateApplyResponse(BaseModel):
    template_key: str
    segments: TemplateBucket
    ramp_topics: TemplateBucket
    objections: TemplateBucket
