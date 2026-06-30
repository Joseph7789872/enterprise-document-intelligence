"""Plain-text + minimal-HTML builders for the Phase D transactional emails.

Kept deliberately tiny (no template engine): each builder returns a ready-to-send
:class:`EmailMessage`. Links are absolute, rooted at ``settings.FRONTEND_BASE_URL``.
"""

from __future__ import annotations

from urllib.parse import quote

from app.core.config import settings

from .sender import EmailMessage


def _link(path: str, token: str) -> str:
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}{path}?token={quote(token, safe='')}"


def invite_email(
    to: str, *, invite_key: str, tenant_slug: str, tenant_name: str, role: str
) -> EmailMessage:
    join_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/accept-invite"
    ttl = settings.INVITE_TOKEN_TTL_HOURS
    text = (
        f"You've been invited to join {tenant_name} on Sales Assistant as a {role}.\n\n"
        f"To join, go to:\n{join_url}\n\n"
        f"and enter:\n"
        f"  Workspace identifier: {tenant_slug}\n"
        f"  Email: {to}\n"
        f"  Invite key: {invite_key}\n"
        f"  (and choose a password)\n\n"
        f"This invite key expires in {ttl} hours.\n"
        "If you weren't expecting this, you can ignore this email."
    )
    html = (
        f"<p>You've been invited to join <strong>{tenant_name}</strong> on Sales "
        f"Assistant as a <strong>{role}</strong>.</p>"
        f'<p>To join, go to <a href="{join_url}">{join_url}</a> and enter:</p>'
        f"<ul><li>Workspace identifier: <strong>{tenant_slug}</strong></li>"
        f"<li>Email: <strong>{to}</strong></li>"
        f"<li>Invite key: <strong>{invite_key}</strong></li>"
        f"<li>(and choose a password)</li></ul>"
        f"<p>This invite key expires in {ttl} hours. "
        "If you weren't expecting this, you can ignore this email.</p>"
    )
    return EmailMessage(to=to, subject=f"You're invited to {tenant_name}", text=text, html=html)


def reset_email(to: str, *, token: str) -> EmailMessage:
    link = _link("/reset-password", token)
    text = (
        "We received a request to reset your Sales Assistant password.\n\n"
        f"Choose a new password:\n{link}\n\n"
        f"This link expires in {settings.RESET_TOKEN_TTL_HOURS} hours. "
        "If you didn't request this, you can safely ignore this email — your password "
        "will not change."
    )
    html = (
        "<p>We received a request to reset your Sales Assistant password.</p>"
        f'<p><a href="{link}">Choose a new password</a></p>'
        f"<p>This link expires in {settings.RESET_TOKEN_TTL_HOURS} hours. If you didn't "
        "request this, you can safely ignore this email — your password will not change.</p>"
    )
    return EmailMessage(to=to, subject="Reset your Sales Assistant password", text=text, html=html)
