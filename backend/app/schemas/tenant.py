"""Tenant API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime


class TenantSettings(BaseModel):
    """Per-tenant LLM routing policy (persisted as JSON on ``tenants.settings``).

    Unknown keys are ignored so the column can evolve; a null/absent value yields all
    defaults. Merged by the model router on top of the deployment-mode + classification
    defaults (Phase 7)."""

    model_config = ConfigDict(extra="ignore")

    # Force every LLM call for this tenant onto the self-hosted profile, regardless of
    # document classification (e.g. an enterprise tenant that bans third-party LLMs).
    require_self_hosted_llm: bool = False
    # Documents at/above this classification route to the self-hosted profile.
    sensitive_classification: Literal["confidential", "privileged"] = "confidential"

    @classmethod
    def from_raw(cls, raw: dict | None) -> TenantSettings:
        """Parse a stored settings dict (or None) into a validated TenantSettings."""
        return cls.model_validate(raw or {})


class TenantSettingsUpdate(BaseModel):
    """Body for PUT /admin/tenant/settings (full replacement of the policy)."""

    model_config = ConfigDict(extra="forbid")

    require_self_hosted_llm: bool = False
    sensitive_classification: Literal["confidential", "privileged"] = "confidential"
