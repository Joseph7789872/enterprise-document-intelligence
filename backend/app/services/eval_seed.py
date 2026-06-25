"""Seed the evaluation corpus + tenant.

Reusable helpers (imported by the CLI seed script, the harness, and tests) that:
- get-or-create the dedicated ``eval-harness`` tenant + owner user, and
- ingest the synthetic eval corpus through the **real** ingestion pipeline so chunks +
  embeddings exist exactly as they would for a customer document.

Everything is idempotent and tenant-scoped to the eval tenant — the eval corpus never
mixes with real tenant data.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import encrypt
from app.core.security import hash_password
from app.models.document import Document, IngestionStatus
from app.models.tenant import Tenant
from app.models.user import User, UserRole
from app.services.ingestion import process_document
from app.storage import document_storage_key, get_storage


def default_corpus_dir() -> Path:
    """The corpus directory, derived from the configured dataset path."""
    return Path(settings.EVAL_DATASET_PATH).resolve().parent / "corpus"


async def ensure_eval_tenant(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Get-or-create the eval tenant + owner; return ``(tenant_id, owner_user_id)``."""
    tenant = (
        await db.scalars(select(Tenant).where(Tenant.slug == settings.EVAL_TENANT_SLUG))
    ).first()
    if tenant is None:
        tenant = Tenant(name="Eval Harness", slug=settings.EVAL_TENANT_SLUG, is_active=True)
        db.add(tenant)
        await db.flush()

    owner = (
        await db.scalars(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == settings.EVAL_TENANT_OWNER_EMAIL,
            )
        )
    ).first()
    if owner is None:
        owner = User(
            tenant_id=tenant.id,
            email=settings.EVAL_TENANT_OWNER_EMAIL,
            # Random password: this account is for the harness, never an interactive login.
            hashed_password=hash_password(uuid.uuid4().hex + uuid.uuid4().hex),
            role=UserRole.OWNER,
            is_active=True,
        )
        db.add(owner)
        await db.flush()

    await db.commit()
    return tenant.id, owner.id


async def seed_corpus(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    corpus_dir: Path | None = None,
) -> list[uuid.UUID]:
    """Ingest every ``*.txt`` in ``corpus_dir`` into the eval tenant (idempotent).

    Returns the ids of documents that are present (newly ingested or already there).
    """
    corpus_dir = corpus_dir or default_corpus_dir()
    files = sorted(corpus_dir.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"No corpus documents found in {corpus_dir}")

    document_ids: list[uuid.UUID] = []
    for path in files:
        existing = (
            await db.scalars(
                select(Document).where(
                    Document.tenant_id == tenant_id,
                    Document.filename == path.name,
                    Document.deleted_at.is_(None),
                )
            )
        ).first()
        if existing is not None:
            document_ids.append(existing.id)
            continue

        data = path.read_bytes()
        document_id = uuid.uuid4()
        storage_key = document_storage_key(tenant_id, document_id)
        get_storage().put(storage_key, encrypt(data).to_token().encode("utf-8"))

        db.add(
            Document(
                id=document_id,
                tenant_id=tenant_id,
                owner_user_id=owner_user_id,
                filename=path.name,
                mime_type="text/plain",
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                storage_key=storage_key,
                encryption_key_version=settings.ENCRYPTION_KEY_VERSION,
                status=IngestionStatus.PENDING,
                chunk_count=0,
            )
        )
        await db.commit()  # commit so process_document's own session sees the row
        await process_document(document_id)
        document_ids.append(document_id)

    return document_ids
