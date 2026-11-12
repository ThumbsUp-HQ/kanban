"""Object embeddings model: object_embeddings with pgvector."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base, ObjectKind, object_kind_pg_enum


class ObjectEmbedding(Base):
    """Vector embeddings of canonical markdown chunks for universal objects."""

    __tablename__ = "object_embeddings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["object_id", "object_type"],
            ["objects.id", "objects.object_type"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "chunk_index BETWEEN 0 AND 63",
            name="object_embeddings_chunk_index_check",
        ),
        CheckConstraint(
            "octet_length(content_sha256) = 32",
            name="object_embeddings_content_sha256_check",
        ),
        Index(
            "object_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("object_embeddings_scope", "workspace_id", "project_id"),
    )

    object_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    object_type: Mapped[ObjectKind] = mapped_column(object_kind_pg_enum, nullable=False)
    chunk_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    content_sha256: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    model_id: Mapped[str] = mapped_column(String, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
