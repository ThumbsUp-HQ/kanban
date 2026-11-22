# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""MCP session and credential read-taint model (KB-P4-07, S3.5, S11.2)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class McpReadTaint(Base):
    """Session and credential read-taint tracking for MCP exfiltration defense."""

    __tablename__ = "mcp_read_taint"
    __table_args__ = (
        CheckConstraint("octet_length(taint_key) = 32", name="mcp_read_taint_key_len_chk"),
        CheckConstraint("key_kind IN ('session', 'credential')", name="mcp_read_taint_kind_chk"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    taint_key: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    key_kind: Mapped[str] = mapped_column(String, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    first_read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    untrusted_source_object_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    contains_untrusted_content: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
