"""PasswordResetToken — a single-use, TTL'd reset token (Phase D).

Same pattern as invitations + API keys: only the hash of the token is stored; the plaintext
lives only in the emailed link. ``used_at`` makes the token strictly single-use.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID


class PasswordResetToken(Base, TimestampMixin, TenantMixin):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # hash_password(token) — the plaintext token only ever appears in the emailed link.
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<PasswordResetToken user={self.user_id} used={self.used_at is not None}>"
