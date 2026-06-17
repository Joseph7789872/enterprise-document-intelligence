"""Group model — a named set of users for access control.

Groups model the org structures access is granted to: departments, matters, client
teams, ad-hoc teams. An ACL grant to a group applies to all its current members, so
matter walls and department-level access are expressed by granting groups, not
enumerating individuals.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID


class GroupType(str, enum.Enum):
    DEPARTMENT = "department"
    MATTER = "matter"  # a legal matter / case (law-firm matter walls)
    CLIENT = "client"
    TEAM = "team"
    CUSTOM = "custom"


class Group(Base, TimestampMixin, TenantMixin):
    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_groups_tenant_id_name"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    group_type: Mapped[GroupType] = mapped_column(
        Enum(GroupType, name="group_type", native_enum=False, length=20),
        nullable=False,
        default=GroupType.CUSTOM,
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Group id={self.id} tenant={self.tenant_id} name={self.name!r}>"
