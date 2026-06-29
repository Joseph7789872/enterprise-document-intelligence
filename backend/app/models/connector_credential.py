"""ConnectorCredential — a tenant's encrypted credential for an external content source.

Connector tokens are secrets, so they live here (encrypted via :func:`crypto.encrypt_str`)
rather than in ``tenants.settings`` (which is documented as never holding secrets). One row
per (tenant, provider); the plaintext token is never returned by the API.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID


class ConnectorProvider(str, enum.Enum):
    NOTION = "notion"


class ConnectorCredential(Base, TimestampMixin, TenantMixin):
    __tablename__ = "connector_credentials"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "provider", name="uq_connector_credentials_tenant_id_provider"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    provider: Mapped[ConnectorProvider] = mapped_column(
        Enum(ConnectorProvider, name="connector_provider", native_enum=False, length=32),
        nullable=False,
    )
    # crypto.encrypt_str() token — never returned by the API.
    token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ConnectorCredential tenant={self.tenant_id} provider={self.provider}>"
