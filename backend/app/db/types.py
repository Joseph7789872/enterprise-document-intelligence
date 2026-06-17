"""Portable SQLAlchemy column types.

The production database is PostgreSQL, but the test suite runs against SQLite
(via aiosqlite) for speed and isolation. These types compile to native Postgres
types (UUID, JSONB) where available and fall back to portable equivalents on other
backends, so the same models work in both places.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import CHAR, JSON, Float, Text, TypeDecorator


class GUID(TypeDecorator):
    """Platform-independent UUID type.

    Uses PostgreSQL's native UUID type; on other backends stores the value as a
    stringified 36-char UUID.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value) if isinstance(value, uuid.UUID) else str(uuid.UUID(str(value)))

    def process_result_value(self, value: Any, dialect: Any) -> uuid.UUID | None:
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class JSONBType(TypeDecorator):
    """JSONB on PostgreSQL, plain JSON elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class TSVector(TypeDecorator):
    """PostgreSQL ``tsvector`` for full-text search; ``Text`` (unused) elsewhere.

    On PostgreSQL this stores stemmed lexemes for BM25/FTS (see
    ``services.keyword_search``). On SQLite (tests) the column exists but is left
    NULL — the keyword-search service uses an in-process fallback there.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(TSVECTOR())
        return dialect.type_descriptor(Text())


class EmbeddingVector(TypeDecorator):
    """Embedding column: pgvector ``vector(dim)`` on PostgreSQL, JSON list elsewhere.

    On PostgreSQL this is a real ``vector`` type, enabling pgvector distance
    operators (``<=>`` cosine) for retrieval. On other backends (SQLite, used by the
    test suite) the embedding is stored as a JSON array of floats; similarity is then
    computed in Python by the retrieval service. Values round-trip as ``list[float]``.
    """

    impl = JSON
    cache_ok = True

    class comparator_factory(TypeDecorator.Comparator):  # noqa: N801 - SQLAlchemy hook name
        """Expose pgvector distance operators through the decorator.

        On PostgreSQL the column is a real ``vector``; ``<=>`` is pgvector's cosine
        distance. (On other backends these are unused — retrieval falls back to
        Python similarity — so they are only ever emitted against Postgres.)
        """

        def cosine_distance(self, other: Any) -> Any:
            return self.op("<=>", return_type=Float())(other)

        def l2_distance(self, other: Any) -> Any:
            return self.op("<->", return_type=Float())(other)

    def __init__(self, dim: int, *args: Any, **kwargs: Any) -> None:
        self.dim = dim
        super().__init__(*args, **kwargs)

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        seq = list(value)
        # pgvector accepts a list directly; JSON fallback also stores a list.
        return seq

    def process_result_value(self, value: Any, dialect: Any) -> list[float] | None:
        if value is None:
            return None
        return [float(x) for x in value]
