"""MCP tool tests — ACL enforcement under the key principal + audit."""

from __future__ import annotations

import uuid

import pytest
from app.core.deps import CurrentUser
from app.core.security import hash_password
from app.models.audit_log import AuditAction, AuditLog
from app.models.document_access_control import DocumentAccessControl, PrincipalType
from app.models.user import User, UserRole
from app.services import mcp_tools
from sqlalchemy import select


async def _upload(client, headers, name: str, text: str) -> uuid.UUID:
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    r = await client.post("/documents", files=files, headers=headers)
    assert r.status_code == 202, r.text
    return uuid.UUID(r.json()["id"])


async def _member_principal(db, tenant_id: uuid.UUID) -> CurrentUser:
    member = User(
        tenant_id=tenant_id, email="member@acme.com",
        hashed_password=hash_password("password-memberx"), role=UserRole.MEMBER, is_active=True,
    )
    db.add(member)
    await db.commit()
    return CurrentUser(id=member.id, tenant_id=tenant_id, role=UserRole.MEMBER, email=member.email)


async def _grant(db, tenant_id, document_id, user_id, perms) -> None:
    db.add(
        DocumentAccessControl(
            tenant_id=tenant_id, document_id=document_id, principal_type=PrincipalType.USER,
            principal_id=user_id, permissions=perms, granted_by_user_id=user_id,
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_search_and_list_respect_acls(client, acme, db_session) -> None:
    doc_a = await _upload(client, acme["headers"], "hr.txt", "Vacation policy twenty days. " * 5)
    doc_b = await _upload(client, acme["headers"], "ops.txt", "Logistics cold chain rules. " * 5)
    tenant_id = uuid.UUID(acme["tenant_id"])
    member = await _member_principal(db_session, tenant_id)
    await _grant(db_session, tenant_id, doc_a, member.id, ["view", "query"])

    search = await mcp_tools.search_chunks(db_session, member, query="logistics cold chain", top_k=6)
    docs = {r["document_id"] for r in search["results"]}
    assert str(doc_b) not in docs
    assert docs <= {str(doc_a)}

    listed = await mcp_tools.list_documents(db_session, member)
    assert [d["id"] for d in listed["documents"]] == [str(doc_a)]


@pytest.mark.asyncio
async def test_get_document_acl(client, acme, db_session) -> None:
    doc_a = await _upload(client, acme["headers"], "hr.txt", "Vacation policy. " * 5)
    doc_b = await _upload(client, acme["headers"], "ops.txt", "Logistics. " * 5)
    tenant_id = uuid.UUID(acme["tenant_id"])
    member = await _member_principal(db_session, tenant_id)
    await _grant(db_session, tenant_id, doc_a, member.id, ["view"])

    got = await mcp_tools.get_document(db_session, member, document_id=doc_a)
    assert got["id"] == str(doc_a)
    denied = await mcp_tools.get_document(db_session, member, document_id=doc_b)
    assert denied == {"error": "not_found"}


@pytest.mark.asyncio
async def test_owner_principal_unrestricted_and_audited(client, acme, db_session) -> None:
    await _upload(client, acme["headers"], "hr.txt", "Vacation policy twenty days. " * 5)
    tenant_id = uuid.UUID(acme["tenant_id"])
    owner = (
        await db_session.scalars(
            select(User).where(User.tenant_id == tenant_id, User.role == UserRole.OWNER)
        )
    ).first()
    principal = CurrentUser(id=owner.id, tenant_id=tenant_id, role=UserRole.OWNER, email=owner.email)

    result = await mcp_tools.search_chunks(db_session, principal, query="vacation", top_k=6)
    assert result["results"]  # owner sees everything

    actions = (await db_session.scalars(select(AuditLog.action))).all()
    assert AuditAction.MCP_TOOL_CALLED in actions
