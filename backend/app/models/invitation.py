"""Invitation — a pending email invite for a new tenant member (Phase D).

A manager invites a rep by email; we store only the SHA/argon2 hash of a single-use token
(the plaintext lives only in the emailed link), plus the role to grant on acceptance. "One
live invite per email" is enforced in the service (querying PENDING by tenant+email) since a
partial unique index isn't portable to SQLite.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID
from app.models.user import UserRole


class InvitationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class Invitation(Base, TimestampMixin, TenantMixin):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False, length=20),
        nullable=False,
        default=UserRole.MEMBER,
    )
    # hash_password(token) — the plaintext token only ever appears in the emailed link.
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[InvitationStatus] = mapped_column(
        Enum(InvitationStatus, name="invitation_status", native_enum=False, length=20),
        nullable=False,
        default=InvitationStatus.PENDING,
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Invitation tenant={self.tenant_id} email={self.email!r} status={self.status}>"
