"""Conversation model — a multi-turn chat thread owned by one user.

Groups a sequence of ``Query`` rows (the turns) so follow-up questions can resolve
references against earlier turns. Tenant- and user-scoped; the thread carries no answer
content itself (each turn's Q/A lives encrypted on its ``Query`` row).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin
from app.db.types import GUID


class Conversation(Base, TimestampMixin, TenantMixin):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # The owner. RESTRICT (not CASCADE): a conversation must outlive nothing — deleting a
    # user with threads is a deliberate admin action, mirroring documents.owner_user_id.
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Optional human label (defaults to the first question client-side if unset).
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Conversation id={self.id} tenant={self.tenant_id} user={self.user_id}>"
