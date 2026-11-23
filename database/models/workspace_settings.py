# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy model for workspace_settings table (KB-P4-09a / S11.4 / S4.1 / S10.2)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for SQLAlchemy Mapped[uuid.UUID]
from datetime import datetime  # noqa: TC003  # Runtime import required for SQLAlchemy Mapped[datetime]
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base

if TYPE_CHECKING:
    from database.models.spine import Workspace


class WorkspaceSettings(Base):
    """Authoritative workspace settings and security configuration."""

    __tablename__ = "workspace_settings"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    default_project_visibility: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="private",
    )
    session_idle_timeout_min: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="60",
    )
    session_absolute_timeout_min: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="720",
    )
    trash_retention_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="30",
    )
    mcp_key_max_ttl_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="90",
    )
    air_gap_mode: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    default_skip_loaded_sequence_numbers: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    report_export_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    report_export_allowed_roles: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default='["ADMIN", "MEMBER"]',
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
    )

    workspace: Mapped[Workspace] = relationship(
        "Workspace",
        foreign_keys=[workspace_id],
    )

    __table_args__ = (
        CheckConstraint(
            "char_length(display_name) BETWEEN 1 AND 80",
            name="workspace_settings_display_name_check",
        ),
        CheckConstraint(
            "default_project_visibility IN ('private','workspace')",
            name="workspace_settings_default_project_visibility_check",
        ),
        CheckConstraint(
            "session_idle_timeout_min BETWEEN 5 AND 720",
            name="workspace_settings_session_idle_timeout_min_check",
        ),
        CheckConstraint(
            "session_absolute_timeout_min BETWEEN 60 AND 10080",
            name="workspace_settings_session_absolute_timeout_min_check",
        ),
        CheckConstraint(
            "trash_retention_days BETWEEN 1 AND 365",
            name="workspace_settings_trash_retention_days_check",
        ),
        CheckConstraint(
            "mcp_key_max_ttl_days BETWEEN 1 AND 365",
            name="workspace_settings_mcp_key_max_ttl_days_check",
        ),
        CheckConstraint(
            "session_absolute_timeout_min >= session_idle_timeout_min",
            name="workspace_settings_session_timeouts_order_check",
        ),
    )
