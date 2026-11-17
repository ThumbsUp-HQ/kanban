# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy model for mcp_api_keys table (KB-P4-02a / KB-P4-14 / S11.1)."""

from __future__ import annotations

import uuid  # Runtime import required for Pydantic / SQLAlchemy mapped_column
from datetime import datetime  # noqa: TC003  # Runtime import required for SQLAlchemy Mapped[datetime]
from typing import TYPE_CHECKING, Literal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, CIDR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base

if TYPE_CHECKING:
    from database.models.principals import Principal
    from database.models.projects import Project
    from database.models.spine import Workspace

McpSurface = Literal["agent", "docs", "admin"]
McpKeyPrefix = Literal["kb_agt_", "kb_doc_", "kb_adm_"]
ScopeTier = Literal["global", "workspace", "project"]
OwnerKind = Literal["personal_user", "service_bot"]


class McpApiKey(Base):
    """Scoped, surface-bound API key stored as a SHA-256 digest."""

    __tablename__ = "mcp_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuidv7(),
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
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
    label: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
    )
    scope_tier: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="workspace",
        index=True,
    )
    owner_kind: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="service_bot",
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    allowed_workspace_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
    )
    allowed_project_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
    )
    capability_mask: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="7",
    )
    allowed_tools: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text),
        nullable=True,
    )
    disabled_tools: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::TEXT[]"),
    )
    allowed_cidrs: Mapped[list[str] | None] = mapped_column(
        ARRAY(CIDR),
        nullable=True,
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
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    workspace: Mapped[Workspace | None] = relationship(
        "Workspace",
        foreign_keys=[workspace_id],
    )
    principal: Mapped[Principal] = relationship(
        "Principal",
        foreign_keys=[principal_id],
    )
    project: Mapped[Project | None] = relationship(
        "Project",
        foreign_keys=[project_id],
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
            "expires_at IS NULL OR expires_at <= created_at + interval '365 days'",
            name="mcp_api_keys_expires_at_check",
        ),
        CheckConstraint(
            "(surface, key_prefix) IN (('agent','kb_agt_'),('docs','kb_doc_'),('admin','kb_adm_'))",
            name="mcp_api_keys_surface_prefix_pair_check",
        ),
        CheckConstraint(
            "scope_tier IN ('global', 'workspace', 'project')",
            name="mcp_api_keys_scope_tier_check",
        ),
        CheckConstraint(
            "owner_kind IN ('personal_user', 'service_bot')",
            name="mcp_api_keys_owner_kind_check",
        ),
        CheckConstraint(
            "capability_mask BETWEEN 1 AND 255",
            name="mcp_api_keys_capability_mask_check",
        ),
        CheckConstraint(
            "(scope_tier = 'global' AND workspace_id IS NULL AND project_id IS NULL) OR "
            "(scope_tier = 'workspace' AND workspace_id IS NOT NULL AND project_id IS NULL) OR "
            "(scope_tier = 'project' AND workspace_id IS NOT NULL AND project_id IS NOT NULL)",
            name="mcp_keys_tier_shape_chk",
        ),
    )
