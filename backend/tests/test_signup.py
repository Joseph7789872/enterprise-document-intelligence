"""Self-serve signup: register seeds a trial subscription; signup gate 404s when disabled."""

from __future__ import annotations

import pytest
from app.core.config import settings


@pytest.mark.asyncio
async def test_register_creates_trial_subscription(client) -> None:
    r = await client.post(
        "/auth/register",
        json={
            "tenant_name": "Newco",
            "tenant_slug": "newco",
            "email": "owner@newco.com",
            "password": "correct horse battery staple",
        },
    )
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    billing = await client.get("/billing", headers=headers)
    assert billing.status_code == 200
    assert billing.json()["subscription"]["plan_key"] == "trial"
    assert billing.json()["subscription"]["status"] == "trialing"


@pytest.mark.asyncio
async def test_signup_disabled_returns_404(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENABLE_SIGNUP", False)
    r = await client.post(
        "/auth/register",
        json={
            "tenant_name": "Nope",
            "tenant_slug": "nope",
            "email": "owner@nope.com",
            "password": "correct horse battery staple",
        },
    )
    assert r.status_code == 404
