"""User model — tenant-scoped, role-based."""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin
from app.db.types import GUID

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class UserRole(str, enum.Enum):
    """Coarse roles for Phase 0. Fine-grained document ACLs arrive in Phase 5."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    REVIEWER = "reviewer"


class User(Base, TimestampMixin, SoftDeleteMixin, TenantMixin):
    __tablename__ = "users"
    __table_args__ = (
        # Email is unique *within* a tenant, not globally — two tenants may both
        # have an "admin@firm.com".
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False, length=20),
        nullable=False,
        default=UserRole.MEMBER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tenant: Mapped[Tenant] = relationship(back_populates="users")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} tenant={self.tenant_id} email={self.email!r}>"
