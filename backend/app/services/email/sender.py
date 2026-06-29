"""Outbound email sender — a small Protocol + factory (mirrors ``get_fetcher()`` /
``get_storage()``).

The endpoint/service layer depends on the :class:`EmailSender` interface; the real
implementation uses ``aiosmtplib`` against any relay, and tests inject a
:class:`FakeEmailSender` via :func:`set_email_sender` so the whole suite stays offline.
The provider is resolved by ``settings.effective_email_provider`` (falls back to the Fake
in development when no SMTP host is configured).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


class EmailError(Exception):
    """An email could not be delivered (SMTP failure)."""


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None


class EmailSender(Protocol):
    async def send(self, msg: EmailMessage) -> None: ...


class FakeEmailSender:
    """Deterministic, offline sender for dev/test — records messages in ``outbox``."""

    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    async def send(self, msg: EmailMessage) -> None:
        self.outbox.append(msg)


class SmtpEmailSender:
    """Sends via ``aiosmtplib`` (lazy-imported) against the configured relay."""

    async def send(self, msg: EmailMessage) -> None:
        from email.message import EmailMessage as MimeMessage

        import aiosmtplib

        mime = MimeMessage()
        mime["From"] = settings.SMTP_FROM
        mime["To"] = msg.to
        mime["Subject"] = msg.subject
        mime.set_content(msg.text)
        if msg.html:
            mime.add_alternative(msg.html, subtype="html")

        try:
            await aiosmtplib.send(
                mime,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USERNAME or None,
                password=settings.SMTP_PASSWORD or None,
                start_tls=settings.SMTP_STARTTLS,
            )
        except Exception as exc:  # noqa: BLE001 - re-raised as a domain error
            raise EmailError(f"Failed to send email: {exc}") from exc


# Test-injectable override (an explicit hook, like the fetcher's — lru_cache would be
# brittle to monkeypatch). A single shared FakeEmailSender is reused so tests can read its
# ``outbox`` after the request that sent the mail.
_override: EmailSender | None = None


def set_email_sender(sender: EmailSender | None) -> None:
    """Install (or clear, with ``None``) an email sender — used by tests to inject a fake."""
    global _override
    _override = sender


def get_email_sender() -> EmailSender:
    if _override is not None:
        return _override
    if settings.effective_email_provider == "smtp":
        return SmtpEmailSender()
    return FakeEmailSender()
