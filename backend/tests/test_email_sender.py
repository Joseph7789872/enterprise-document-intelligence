"""Email sender + template unit tests: Fake captures messages; templates build links."""

from __future__ import annotations

import pytest
from app.services.email import templates
from app.services.email.sender import (
    EmailMessage,
    FakeEmailSender,
    SmtpEmailSender,
    get_email_sender,
    set_email_sender,
)


@pytest.mark.asyncio
async def test_fake_sender_captures_messages() -> None:
    sender = FakeEmailSender()
    await sender.send(EmailMessage(to="a@b.com", subject="Hi", text="Body"))
    assert len(sender.outbox) == 1
    assert sender.outbox[0].to == "a@b.com"


def test_invite_template_has_key_and_join_details() -> None:
    msg = templates.invite_email(
        "rep@acme.com",
        invite_key="ABCDE-FGHJK-LMNPQ-RSTUV",
        tenant_slug="acme",
        tenant_name="Acme",
        role="member",
    )
    assert "ABCDE-FGHJK-LMNPQ-RSTUV" in msg.text
    assert "acme" in msg.text  # workspace identifier
    assert "/accept-invite" in msg.text
    assert "Acme" in msg.text
    assert msg.html is not None and "ABCDE-FGHJK-LMNPQ-RSTUV" in msg.html


def test_reset_template_has_reset_link() -> None:
    msg = templates.reset_email("user@acme.com", token="xyz.123")
    assert "/reset-password?token=xyz.123" in msg.text


def test_override_hook_overrides_provider() -> None:
    fake = FakeEmailSender()
    set_email_sender(fake)
    try:
        assert get_email_sender() is fake
    finally:
        set_email_sender(None)
    # Cleared → default resolves to a concrete sender (Fake in dev, since EMAIL_PROVIDER=fake).
    assert isinstance(get_email_sender(), FakeEmailSender | SmtpEmailSender)
