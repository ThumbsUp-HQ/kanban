# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy 2.0 ORM model for project_repo_bindings (KB-P5-19b, S14.2)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003
from pathlib import Path

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class ProjectRepoBinding(Base):
    """Git repository binding for a project (KB-P5-19b, S14.2)."""

    __tablename__ = "project_repo_bindings"
    __table_args__ = (
        CheckConstraint(
            "slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'",
            name="ck_project_repo_bindings_slug",
        ),
        CheckConstraint(
            "char_length(remote_url) <= 2048",
            name="ck_project_repo_bindings_remote_url",
        ),
        CheckConstraint(
            "default_ref ~ '^[A-Za-z0-9._/-]{1,200}$' AND default_ref !~ '\\.\\.'",
            name="ck_project_repo_bindings_default_ref",
        ),
        CheckConstraint(
            "access_mode IN ('bare_git_tools', 'ro_vfs_mount')",
            name="ck_project_repo_bindings_access_mode",
        ),
        CheckConstraint(
            "last_fetched_commit IS NULL OR last_fetched_commit ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'",
            name="ck_project_repo_bindings_commit",
        ),
        UniqueConstraint("project_id", "slug", name="uq_project_repo_bindings_proj_slug"),
        Index("idx_project_repo_bindings_ws", "workspace_id"),
        Index("idx_project_repo_bindings_proj", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(63), nullable=False)
    remote_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    default_ref: Mapped[str] = mapped_column(
        String(200), nullable=False, server_default=text("'main'")
    )
    access_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    credential_dek_kid: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_fetched_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fetch_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("principals.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )

    @property
    def mirror_path(self) -> Path:
        """Derived filesystem path for the bare mirror repository."""
        return Path(f"/var/lib/kanban/git-mirrors/{self.workspace_id}/{self.id}.git")
