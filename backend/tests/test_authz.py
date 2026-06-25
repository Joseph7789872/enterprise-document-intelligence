"""Authorization service unit tests (deny-by-default, grants, groups, revoke)."""

from __future__ import annotations

import uuid

import pytest
from app.core.security import hash_password
from app.models.document_access_control import DocumentAccessControl, PrincipalType
from app.models.group import Group, GroupType
from app.models.group_membership import GroupMembership
from app.models.user import User, UserRole
from app.services import authz
from app.services.authz import Permission
from sqlalchemy import select


async def _upload(client, headers, name: str, text: str, visibility: str = "manager_only") -> uuid.UUID:
    # Default to manager-only so a member has no access without an explicit grant
    # (the grant path under test); pass visibility="rep_visible" to test the AE default.
    files = {"file": (name, text.encode("utf-8"), "text/plain")}
    r = await client.post(
        "/documents", files=files, data={"visibility": visibility}, headers=headers
    )
    assert r.status_code == 202, r.text
    return uuid.UUID(r.json()["id"])


async def _owner_id(db, tenant_id: uuid.UUID) -> uuid.UUID:
    owner = (
        await db.scalars(
            select(User).where(User.tenant_id == tenant_id, User.role == UserRole.OWNER)
        )
    ).first()
    return owner.id


async def _make_member(db, tenant_id: uuid.UUID, email: str = "member@acme.com") -> uuid.UUID:
    member = User(
        tenant_id=tenant_id,
        email=email,
        hashed_password=hash_password("password-memberx"),
        role=UserRole.MEMBER,
        is_active=True,
    )
    db.add(member)
    await db.commit()
    return member.id


@pytest.mark.asyncio
async def test_owner_is_unrestricted(client, acme, db_session) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    allowed = await authz.accessible_document_ids(
        db_session, tenant_id=tenant_id,
        user_id=await _owner_id(db_session, tenant_id),
        role=UserRole.OWNER, permission=Permission.QUERY,
    )
    assert allowed is None  # None == unrestricted


@pytest.mark.asyncio
async def test_member_deny_by_default_then_grant(client, acme, db_session) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    doc_a = await _upload(client, acme["headers"], "a.txt", "Alpha content here. " * 4)
    doc_b = await _upload(client, acme["headers"], "b.txt", "Beta content here. " * 4)
    member_id = await _make_member(db_session, tenant_id)

    # Deny-by-default: a member with no grants sees nothing.
    allowed = await authz.accessible_document_ids(
        db_session, tenant_id=tenant_id, user_id=member_id,
        role=UserRole.MEMBER, permission=Permission.QUERY,
    )
    assert allowed == set()

    # Direct user grant on doc A.
    db_session.add(
        DocumentAccessControl(
            tenant_id=tenant_id, document_id=doc_a, principal_type=PrincipalType.USER,
            principal_id=member_id, permissions=["query"], granted_by_user_id=member_id,
        )
    )
    await db_session.commit()
    allowed = await authz.accessible_document_ids(
        db_session, tenant_id=tenant_id, user_id=member_id,
        role=UserRole.MEMBER, permission=Permission.QUERY,
    )
    assert allowed == {doc_a}
    assert doc_b not in allowed


@pytest.mark.asyncio
async def test_group_grant_propagates_and_revokes(client, acme, db_session) -> None:
    tenant_id = uuid.UUID(acme["tenant_id"])
    doc = await _upload(client, acme["headers"], "matter.txt", "Matter content. " * 4)
    member_id = await _make_member(db_session, tenant_id)

    group = Group(tenant_id=tenant_id, name="Matter X", group_type=GroupType.MATTER)
    db_session.add(group)
    await db_session.flush()
    db_session.add(GroupMembership(tenant_id=tenant_id, group_id=group.id, user_id=member_id))
    grant = DocumentAccessControl(
        tenant_id=tenant_id, document_id=doc, principal_type=PrincipalType.GROUP,
        principal_id=group.id, permissions=["view", "query"], granted_by_user_id=member_id,
    )
    db_session.add(grant)
    await db_session.commit()

    assert await authz.can_access_document(
        db_session, tenant_id=tenant_id, user_id=member_id, role=UserRole.MEMBER,
        document_id=doc, permission=Permission.QUERY,
    )

    # Revoking the group grant removes access.
    await db_session.delete(grant)
    await db_session.commit()
    assert not await authz.can_access_document(
        db_session, tenant_id=tenant_id, user_id=member_id, role=UserRole.MEMBER,
        document_id=doc, permission=Permission.QUERY,
    )


@pytest.mark.asyncio
async def test_rep_visible_content_is_queryable_without_a_grant(client, acme, db_session) -> None:
    """An AE (MEMBER) sees all rep-visible content without an explicit grant, but
    manager-only content stays hidden, and visibility never confers DELETE."""
    tenant_id = uuid.UUID(acme["tenant_id"])
    rep_doc = await _upload(client, acme["headers"], "pitch.txt", "Product pitch. " * 4, "rep_visible")
    mgr_doc = await _upload(client, acme["headers"], "floor.txt", "Floor pricing. " * 4, "manager_only")
    member_id = await _make_member(db_session, tenant_id)

    allowed_query = await authz.accessible_document_ids(
        db_session, tenant_id=tenant_id, user_id=member_id,
        role=UserRole.MEMBER, permission=Permission.QUERY,
    )
    assert rep_doc in allowed_query
    assert mgr_doc not in allowed_query

    # Visibility grants VIEW/QUERY but never DELETE.
    assert await authz.can_access_document(
        db_session, tenant_id=tenant_id, user_id=member_id, role=UserRole.MEMBER,
        document_id=rep_doc, permission=Permission.VIEW,
    )
    assert not await authz.can_access_document(
        db_session, tenant_id=tenant_id, user_id=member_id, role=UserRole.MEMBER,
        document_id=rep_doc, permission=Permission.DELETE,
    )


@pytest.mark.asyncio
async def test_permission_is_specific(client, acme, db_session) -> None:
    """A VIEW grant does not confer DELETE."""
    tenant_id = uuid.UUID(acme["tenant_id"])
    doc = await _upload(client, acme["headers"], "c.txt", "Gamma content. " * 4)
    member_id = await _make_member(db_session, tenant_id)
    db_session.add(
        DocumentAccessControl(
            tenant_id=tenant_id, document_id=doc, principal_type=PrincipalType.USER,
            principal_id=member_id, permissions=["view"], granted_by_user_id=member_id,
        )
    )
    await db_session.commit()

    assert await authz.can_access_document(
        db_session, tenant_id=tenant_id, user_id=member_id, role=UserRole.MEMBER,
        document_id=doc, permission=Permission.VIEW,
    )
    assert not await authz.can_access_document(
        db_session, tenant_id=tenant_id, user_id=member_id, role=UserRole.MEMBER,
        document_id=doc, permission=Permission.DELETE,
    )
