"""Authorization service — the single place document permissions are resolved.

Access is **deny-by-default**: within a tenant, a user reaches a document only if they
own it, are a tenant OWNER/ADMIN, or hold a matching ACL grant (directly or via a group
they belong to). Every retrieval leg and document-scoped endpoint routes its permission
decision through here so the policy lives in one auditable place.

``accessible_document_ids`` returns ``None`` to mean *unrestricted* (OWNER/ADMIN, or a
trusted internal caller) — callers pass that straight through to retrieval, which then
applies no document filter. A non-``None`` empty set means *deny-all* (fail closed).
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AuthorizationError
from app.models.audit_log import AuditAction
from app.models.document import ContentVisibility, Document
from app.models.document_access_control import DocumentAccessControl, PrincipalType
from app.models.group_membership import GroupMembership
from app.models.user import UserRole
from app.services import audit_service


class Permission(str, enum.Enum):
    """Document-scoped permissions (CanView/CanQuery/CanDelete/CanReview + manage)."""

    VIEW = "view"
    QUERY = "query"
    DELETE = "delete"
    REVIEW = "review"
    MANAGE = "manage"  # grant/revoke ACLs on the document


# Roles that implicitly hold every permission on every document in their tenant.
# In the sales product these are the manager/admin roles (OWNER/ADMIN); MEMBER is an AE.
_PRIVILEGED_ROLES = frozenset({UserRole.OWNER, UserRole.ADMIN})

# Permissions an AE (non-privileged) gets on any rep-visible content without an explicit
# grant. Mutating/managing permissions (DELETE/REVIEW/MANAGE) still require ownership or a
# grant, so visibility never lets a rep delete or re-share content.
_VISIBILITY_PERMISSIONS = frozenset({Permission.VIEW, Permission.QUERY})


def is_privileged(role: UserRole) -> bool:
    return role in _PRIVILEGED_ROLES


async def user_group_ids(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> set[uuid.UUID]:
    """The ids of every group the user belongs to (tenant-scoped)."""
    rows = await db.scalars(
        select(GroupMembership.group_id).where(
            GroupMembership.tenant_id == tenant_id,
            GroupMembership.user_id == user_id,
        )
    )
    return set(rows.all())


def _grant_matches(
    acl: DocumentAccessControl,
    *,
    user_id: uuid.UUID,
    group_ids: set[uuid.UUID],
    permission: Permission,
) -> bool:
    if permission.value not in (acl.permissions or []):
        return False
    if acl.principal_type == PrincipalType.USER:
        return acl.principal_id == user_id
    return acl.principal_id in group_ids


async def accessible_document_ids(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: UserRole,
    permission: Permission,
) -> set[uuid.UUID] | None:
    """Document ids the user may act on with ``permission``.

    Returns ``None`` (unrestricted) for managers (OWNER/ADMIN). Otherwise the set of
    owned docs + all rep-visible content (for VIEW/QUERY) + docs granted the permission
    directly or via a group. An empty set means no access.
    """
    if is_privileged(role):
        return None

    # Owned documents (owner always has full access to their own docs).
    owned = await db.scalars(
        select(Document.id).where(
            Document.tenant_id == tenant_id,
            Document.owner_user_id == user_id,
            Document.deleted_at.is_(None),
        )
    )
    allowed: set[uuid.UUID] = set(owned.all())

    # Rep-visible content is readable/queryable by every AE without an explicit grant.
    if permission in _VISIBILITY_PERMISSIONS:
        rep_visible = await db.scalars(
            select(Document.id).where(
                Document.tenant_id == tenant_id,
                Document.visibility == ContentVisibility.REP_VISIBLE,
                Document.deleted_at.is_(None),
            )
        )
        allowed |= set(rep_visible.all())

    group_ids = await user_group_ids(db, tenant_id=tenant_id, user_id=user_id)
    acls = await db.scalars(
        select(DocumentAccessControl).where(DocumentAccessControl.tenant_id == tenant_id)
    )
    for acl in acls.all():
        if _grant_matches(acl, user_id=user_id, group_ids=group_ids, permission=permission):
            allowed.add(acl.document_id)
    return allowed


async def can_access_document(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: UserRole,
    document_id: uuid.UUID,
    permission: Permission,
) -> bool:
    """Whether the user holds ``permission`` on one specific document."""
    if is_privileged(role):
        return True

    document = await db.get(Document, document_id)
    if document is None or document.tenant_id != tenant_id or document.deleted_at is not None:
        return False
    if document.owner_user_id == user_id:
        return True
    # Rep-visible content is readable/queryable by every AE without an explicit grant.
    if (
        permission in _VISIBILITY_PERMISSIONS
        and document.visibility == ContentVisibility.REP_VISIBLE
    ):
        return True

    group_ids = await user_group_ids(db, tenant_id=tenant_id, user_id=user_id)
    acls = await db.scalars(
        select(DocumentAccessControl).where(
            DocumentAccessControl.tenant_id == tenant_id,
            DocumentAccessControl.document_id == document_id,
        )
    )
    return any(
        _grant_matches(acl, user_id=user_id, group_ids=group_ids, permission=permission)
        for acl in acls.all()
    )


async def assert_can(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: UserRole,
    document_id: uuid.UUID,
    permission: Permission,
    ip_address: str | None = None,
) -> None:
    """Raise :class:`AuthorizationError` (and audit the denial) if access is not allowed."""
    if await can_access_document(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        role=role,
        document_id=document_id,
        permission=permission,
    ):
        return
    await audit_service.write_event(
        db,
        tenant_id=tenant_id,
        action=AuditAction.ACCESS_DENIED,
        actor_user_id=user_id,
        resource_type="document",
        resource_id=str(document_id),
        metadata={"permission": permission.value},
        ip_address=ip_address,
        outcome="deny",
    )
    raise AuthorizationError("You do not have permission to perform this action.")
