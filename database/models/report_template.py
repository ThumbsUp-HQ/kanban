# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy model for report_templates table (KAN-317)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base

if TYPE_CHECKING:
    from database.models.principals import User
    from database.models.projects import Project
    from database.models.spine import Workspace


class ReportTemplate(Base):
    """Jinja2 report template definition with schema, CSV definitions, and format controls."""

    __tablename__ = "report_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuidv7(),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    slug: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="",
    )
    is_builtin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    template_markdown: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    parameters_schema_json: Mapped[list[dict[str, Any]] | dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    csv_columns_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
    )
    allowed_formats: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default='["pdf", "xlsx", "csv", "docx", "odt", "html", "md"]',
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.clock_timestamp(),
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
    project: Mapped[Project | None] = relationship(
        "Project",
        foreign_keys=[project_id],
    )
    created_by_user: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[created_by_user_id],
    )

    __table_args__ = (
        CheckConstraint(
            "char_length(slug) BETWEEN 1 AND 80 AND slug ~ '^[a-z0-9][a-z0-9_-]*$'",
            name="report_templates_slug_check",
        ),
        CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120",
            name="report_templates_name_check",
        ),
        CheckConstraint(
            "octet_length(template_markdown) <= 131072",
            name="report_templates_markdown_len_check",
        ),
        Index("idx_report_templates_ws_id", "workspace_id"),
        Index("idx_report_templates_proj_id", "project_id"),
    )
