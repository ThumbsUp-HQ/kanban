# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy model for mcp_ephemeral_tokens table (KB-P4-13 / S14.3)."""

from __future__ import annotations

import uuid  # Runtime import required for SQLAlchemy mapped_column
from datetime import datetime  # noqa: TC003  # Runtime import required for SQLAlchemy Mapped[datetime]
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base

if TYPE_CHECKING:
    from database.models.principals import Principal
    from database.models.projects import Project
    from database.models.spine import Workspace


class McpEphemeralToken(Base):
    """Short-lived, read-only MCP token bound to execution_id and Invoker ∩ Agent ∩ Project."""

    __tablename__ = "mcp_ephemeral_tokens"

    __table_args__ = (
        CheckConstraint(
            "cardinality(allowed_tools) BETWEEN 1 AND 4 "
            "AND allowed_tools <@ "
            "ARRAY['search_tickets','read_ticket','search_knowledge','read_doc']::text[]",
            name="mcp_ephemeral_tokens_allowed_tools_check",
        ),
        CheckConstraint(
            "max_calls BETWEEN 1 AND 25",
            name="mcp_ephemeral_tokens_max_calls_check",
        ),
        CheckConstraint(
            "calls_used >= 0 AND calls_used <= max_calls",
            name="mcp_ephemeral_tokens_calls_used_check",
        ),
        CheckConstraint(
            "expires_at > created_at AND expires_at <= created_at + interval '120 seconds'",
            name="mcp_ephemeral_tokens_ttl_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuidv7(),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    invoking_principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_sha256: Mapped[bytes] = mapped_column(
        BYTEA,
        unique=True,
        nullable=False,
        index=True,
    )
    allowed_tools: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
    )
    max_calls: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=25,
    )
    calls_used: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    workspace: Mapped[Workspace] = relationship(
        "Workspace",
        foreign_keys=[workspace_id],
    )
    invoking_principal: Mapped[Principal] = relationship(
        "Principal",
        foreign_keys=[invoking_principal_id],
    )
    agent_principal: Mapped[Principal] = relationship(
        "Principal",
        foreign_keys=[agent_principal_id],
    )
    project: Mapped[Project] = relationship(
        "Project",
        foreign_keys=[project_id],
    )
