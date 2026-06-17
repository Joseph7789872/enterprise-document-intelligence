"""Auth flow tests: registration, login, refresh, /me, and tenant isolation."""

from __future__ import annotations

import pytest
from app.core.security import (
    TokenError,
    TokenType,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from httpx import AsyncClient


def test_password_hash_and_verify() -> None:
    hashed = hash_password("super-secret-pw")
    assert hashed != "super-secret-pw"
    assert verify_password("super-secret-pw", hashed)
    assert not verify_password("wrong", hashed)


def test_access_token_carries_tenant_and_role() -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", role="owner")
    payload = decode_token(token, expected_type=TokenType.ACCESS)
    assert payload.sub == "u1"
    assert payload.tenant_id == "t1"
    assert payload.role == "owner"
    assert payload.type == TokenType.ACCESS


def test_wrong_token_type_rejected() -> None:
    token = create_access_token(user_id="u1", tenant_id="t1", role="owner")
    with pytest.raises(TokenError):
        decode_token(token, expected_type=TokenType.REFRESH)


@pytest.mark.asyncio
async def test_register_login_me_refresh(client: AsyncClient, register_payload: dict) -> None:
    # Register → 201 with tokens.
    r = await client.post("/auth/register", json=register_payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["tenant"]["slug"] == "acme-legal"
    assert body["user"]["role"] == "owner"
    access = body["tokens"]["access_token"]
    refresh = body["tokens"]["refresh_token"]

    # /me with access token returns the owner.
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["email"] == register_payload["email"]

    # Login returns a fresh pair.
    login = await client.post(
        "/auth/login",
        json={
            "tenant_slug": register_payload["tenant_slug"],
            "email": register_payload["email"],
            "password": register_payload["password"],
        },
    )
    assert login.status_code == 200
    assert "access_token" in login.json()

    # Refresh exchanges a refresh token for a new pair.
    refreshed = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert refreshed.status_code == 200
    assert "access_token" in refreshed.json()


@pytest.mark.asyncio
async def test_duplicate_tenant_slug_conflicts(client: AsyncClient, register_payload: dict) -> None:
    assert (await client.post("/auth/register", json=register_payload)).status_code == 201
    dup = await client.post("/auth/register", json=register_payload)
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_bad_password_rejected(client: AsyncClient, register_payload: dict) -> None:
    await client.post("/auth/register", json=register_payload)
    bad = await client.post(
        "/auth/login",
        json={
            "tenant_slug": register_payload["tenant_slug"],
            "email": register_payload["email"],
            "password": "wrong-password",
        },
    )
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_token(client: AsyncClient) -> None:
    assert (await client.get("/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_token_from_other_tenant_cannot_be_forged(client: AsyncClient, register_payload: dict) -> None:
    """A token whose tenant_id doesn't match the stored user is rejected."""
    r = await client.post("/auth/register", json=register_payload)
    user_id = r.json()["user"]["id"]

    # Forge an access token with a mismatched tenant id but a real user id.
    forged = create_access_token(
        user_id=user_id, tenant_id="00000000-0000-0000-0000-000000000000", role="owner"
    )
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401
