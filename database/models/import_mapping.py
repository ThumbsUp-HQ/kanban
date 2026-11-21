# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy 2.0 ORM model for import entity idempotency ledger (KB-P6-01)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class ImportEntityMapping(Base):
    """Idempotency and entity mapping ledger for imported source objects."""

    __tablename__ = "import_entity_mappings"
    __table_args__ = (
        CheckConstraint(
            "source_system IN ('plane', 'jira', 'github', 'linear')",
            name="import_entity_mappings_source_system_check",
        ),
        CheckConstraint(
            "char_length(source_id) BETWEEN 1 AND 128",
            name="import_entity_mappings_source_id_check",
        ),
        CheckConstraint(
            "octet_length(source_sha256) = 32",
            name="import_entity_mappings_source_sha256_check",
        ),
        Index(
            "import_entity_mappings_target_idx",
            "workspace_id",
            "target_id",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_system: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )
    source_kind: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )
    source_id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )
    source_sha256: Mapped[bytes] = mapped_column(
        LargeBinary(32),
        nullable=False,
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
        default=lambda: datetime.now(UTC),
    )
