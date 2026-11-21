# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy 2.0 ORM model for legacy issue key aliases (KB-P6-03)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class IssueKeyAlias(Base):
    """Legacy issue key aliases mapping former foreign keys to canonical issues."""

    __tablename__ = "issue_key_aliases"
    __table_args__ = (
        CheckConstraint(
            "legacy_key ~ '^[A-Z][A-Z0-9_-]{1,24}-[0-9]{1,18}$'",
            name="issue_key_aliases_legacy_key_check",
        ),
        CheckConstraint(
            "source_system IN ('plane', 'jira', 'github', 'linear')",
            name="issue_key_aliases_source_system_check",
        ),
        Index(
            "idx_issue_key_aliases_workspace_issue",
            "workspace_id",
            "issue_id",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    legacy_key: Mapped[str] = mapped_column(
        String,
        primary_key=True,
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_system: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
        default=lambda: datetime.now(UTC),
    )
