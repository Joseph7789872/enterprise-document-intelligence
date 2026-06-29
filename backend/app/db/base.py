"""SQLAlchemy declarative base with an explicit constraint naming convention.

A deterministic naming convention keeps Alembic autogenerate stable and makes
constraints/indexes addressable in migrations across databases.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# Import models here so that ``Base.metadata`` is fully populated for Alembic
# autogenerate and for ``create_all`` in tests. Kept at the bottom to avoid
# circular imports.
from app.models import (  # noqa: E402,F401
    api_key,
    audit_log,
    connector_credential,
    conversation,
    data_subject_request,
    document,
    document_access_control,
    document_chunk,
    document_segment,
    eval_result,
    eval_run,
    group,
    group_membership,
    invitation,
    objection_segment,
    password_reset_token,
    query,
    ramp_topic,
    retention,
    saved_objection,
    segment,
    subscription,
    tenant,
    user,
)
