"""Phase F: enterprise surfaces 404 when their flag is off, while core admin stays up.

The flags default ON (pinned in conftest), so the surfaces are reachable in the suite;
these tests monkeypatch a flag OFF and assert the gate engages without touching the core
v1 endpoints. This is the v1 "enterprise-off" product profile, proven surgically.
"""

from __future__ import annotations

import pytest
from app.core.config import settings


@pytest.mark.asyncio
async def test_surfaces_reachable_when_flags_on(client, acme) -> None:
    h = acme["headers"]
    assert (await client.get("/audit/logs", headers=h)).status_code == 200
    assert (await client.get("/admin/groups", headers=h)).status_code == 200
    assert (await client.get("/admin/api-keys", headers=h)).status_code == 200
    assert (await client.get("/admin/tenant/settings", headers=h)).status_code == 200


@pytest.mark.asyncio
async def test_audit_404_when_disabled(client, acme, monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENABLE_AUDIT", False)
    assert (await client.get("/audit/logs", headers=acme["headers"])).status_code == 404
    # Export is on the same router → also gated.
    assert (await client.get("/audit/export", headers=acme["headers"])).status_code == 404


@pytest.mark.asyncio
async def test_enterprise_admin_404_when_disabled(client, acme, monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENABLE_ENTERPRISE_ADMIN", False)
    h = acme["headers"]
    assert (await client.get("/admin/groups", headers=h)).status_code == 404
    assert (await client.get("/admin/api-keys", headers=h)).status_code == 404
    assert (await client.get("/admin/tenant/settings", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_core_admin_unaffected_when_enterprise_off(client, acme, monkeypatch) -> None:
    """The key assertion: gating is surgical — core v1 admin keeps working."""
    monkeypatch.setattr(settings, "ENABLE_ENTERPRISE_ADMIN", False)
    monkeypatch.setattr(settings, "ENABLE_AUDIT", False)
    h = acme["headers"]
    assert (await client.get("/admin/users", headers=h)).status_code == 200
    assert (await client.get("/admin/invitations", headers=h)).status_code == 200
    assert (await client.get("/admin/templates", headers=h)).status_code == 200
    # And the core product surfaces are untouched.
    assert (await client.get("/documents", headers=h)).status_code == 200
    assert (await client.get("/analytics/overview", headers=h)).status_code == 200
