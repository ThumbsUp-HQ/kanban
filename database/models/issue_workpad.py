# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy 2.0 ORM model for silent agent workpad slot (KB-AGENT-WORKPAD-01, KAN-71)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003

from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class IssueWorkpad(Base):
    """Silent per-issue, per-principal Agent Workpad state slot."""

    __tablename__ = "issue_workpads"
    __table_args__ = (
        UniqueConstraint("issue_id", "principal_id", name="uq_issue_workpads_issue_principal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    body_markdown: Mapped[str] = mapped_column(String, nullable=False)
    body_sha256: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        Computed("digest(body_markdown, 'sha256'::text)", persisted=True),
        nullable=True,
    )
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
