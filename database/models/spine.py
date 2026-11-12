"""Spine models: workspaces, objects, object_links, link_type_matrix, invalid_object_link_audits."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import (
    Base,
    InvalidLinkReason,
    LinkKind,
    ObjectKind,
    invalid_link_reason_pg_enum,
    link_kind_pg_enum,
    object_kind_pg_enum,
)


class Workspace(Base):
    """Authoritative workspace boundary entity."""

    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    trash_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("30")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ObjectRecord(Base):
    """Universal Object Graph spine registry for all first-class entities."""

    __tablename__ = "objects"
    __table_args__ = (
        UniqueConstraint("id", "object_type", name="objects_id_object_type_key"),
        UniqueConstraint(
            "workspace_id",
            "object_type",
            "canonical_key",
            name="objects_workspace_id_object_type_canonical_key_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    object_type: Mapped[ObjectKind] = mapped_column(object_kind_pg_enum, nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    canonical_key: Mapped[str] = mapped_column(String, nullable=False)
    display_title: Mapped[str] = mapped_column(String, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ObjectLink(Base):
    """First-class typed relationship edges connecting Universal Object Graph nodes."""

    __tablename__ = "object_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_id", "source_type"],
            ["objects.id", "objects.object_type"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["target_id", "target_type"],
            ["objects.id", "objects.object_type"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "source_id",
            "target_id",
            "link_type",
            name="object_links_source_id_target_id_link_type_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    source_type: Mapped[ObjectKind] = mapped_column(object_kind_pg_enum, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    target_type: Mapped[ObjectKind] = mapped_column(object_kind_pg_enum, nullable=False)
    link_type: Mapped[LinkKind] = mapped_column(link_kind_pg_enum, nullable=False)
    link_state: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'ACTIVE'"))
    source_key_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    target_key_snapshot: Mapped[str] = mapped_column(String, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class LinkTypeMatrix(Base):
    """Admissibility matrix defining valid directed link combinations between entity types."""

    __tablename__ = "link_type_matrix"

    source_type: Mapped[ObjectKind] = mapped_column(
        object_kind_pg_enum, primary_key=True, nullable=False
    )
    link_type: Mapped[LinkKind] = mapped_column(link_kind_pg_enum, primary_key=True, nullable=False)
    target_type: Mapped[ObjectKind] = mapped_column(
        object_kind_pg_enum, primary_key=True, nullable=False
    )
    is_bidirectional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    inverse_link_type: Mapped[LinkKind | None] = mapped_column(link_kind_pg_enum, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class InvalidObjectLinkAudit(Base):
    """Audit ledger capturing detected invalid or broken object links."""

    __tablename__ = "invalid_object_link_audits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    link_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    reason: Mapped[InvalidLinkReason] = mapped_column(invalid_link_reason_pg_enum, nullable=False)
    link_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    target_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purged_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("principals.id", ondelete="RESTRICT"), nullable=True
    )
    purge_reason: Mapped[str | None] = mapped_column(String, nullable=True)
