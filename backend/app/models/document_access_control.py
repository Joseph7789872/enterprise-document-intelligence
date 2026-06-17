"""DocumentAccessControl model — a per-document permission grant.

Each row grants a permission set on one document to a principal: either a specific
``USER`` or a ``GROUP`` (whose members inherit the grant). Access is deny-by-default —
absent any grant, only the document owner and tenant OWNER/ADMIN can reach a document.
``permissions`` is a JSON list of :class:`app.services.authz.Permission` values
(VIEW/QUERY/DELETE/REVIEW/MANAGE), kept human-readable and auditable.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID, JSONBType


class PrincipalType(str, enum.Enum):
    USER = "user"
    GROUP = "group"


class DocumentAccessControl(Base, TimestampMixin, TenantMixin):
    __tablename__ = "document_access_control"
    __table_args__ = (
        Index("ix_document_access_control_tenant_id_document_id", "tenant_id", "document_id"),
        Index("ix_document_access_control_principal", "principal_type", "principal_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    principal_type: Mapped[PrincipalType] = mapped_column(
        Enum(PrincipalType, name="principal_type", native_enum=False, length=10),
        nullable=False,
    )
    # A user id or group id, depending on principal_type (not a hard FK so a single
    # column serves both; tenant scoping + app-level validation enforce integrity).
    principal_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    # JSON list of permission strings, e.g. ["view", "query"].
    permissions: Mapped[list] = mapped_column(JSONBType(), nullable=False)
    granted_by_user_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<DocumentAccessControl doc={self.document_id} "
            f"{self.principal_type}={self.principal_id} perms={self.permissions}>"
        )
