# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy model for mcp_api_keys table (KB-P4-02a / S11.1)."""

from __future__ import annotations

import uuid  # Runtime import required for Pydantic / SQLAlchemy mapped_column
from datetime import datetime  # noqa: TC003  # Runtime import required for SQLAlchemy Mapped[datetime]
from typing import TYPE_CHECKING, Literal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base

if TYPE_CHECKING:
    from database.models.principals import Principal
    from database.models.spine import Workspace

McpSurface = Literal["agent", "docs", "admin"]
McpKeyPrefix = Literal["kb_agt_", "kb_doc_", "kb_adm_"]


class McpApiKey(Base):
    """Scoped, surface-bound API key stored as a SHA-256 digest."""

    __tablename__ = "mcp_api_keys"

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
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    surface: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    key_prefix: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    key_sha256: Mapped[bytes] = mapped_column(
        BYTEA,
        unique=True,
        nullable=False,
        index=True,
    )
    display_hint: Mapped[str] = mapped_column(
        String(4),
        nullable=False,
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id"),
        nullable=False,
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
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    workspace: Mapped[Workspace] = relationship(
        "Workspace",
        foreign_keys=[workspace_id],
    )
    principal: Mapped[Principal] = relationship(
        "Principal",
        foreign_keys=[principal_id],
    )
    created_by: Mapped[Principal] = relationship(
        "Principal",
        foreign_keys=[created_by_id],
    )

    __table_args__ = (
        CheckConstraint(
            "surface IN ('agent', 'docs', 'admin')",
            name="mcp_api_keys_surface_check",
        ),
        CheckConstraint(
            "key_prefix IN ('kb_agt_', 'kb_doc_', 'kb_adm_')",
            name="mcp_api_keys_key_prefix_check",
        ),
        CheckConstraint(
            "octet_length(key_sha256) = 32",
            name="mcp_api_keys_key_sha256_check",
        ),
        CheckConstraint(
            "char_length(display_hint) = 4",
            name="mcp_api_keys_display_hint_check",
        ),
        CheckConstraint(
            "expires_at <= created_at + interval '365 days'",
            name="mcp_api_keys_expires_at_check",
        ),
        CheckConstraint(
            "(surface, key_prefix) IN (('agent','kb_agt_'),('docs','kb_doc_'),('admin','kb_adm_'))",
            name="mcp_api_keys_surface_prefix_pair_check",
        ),
    )
