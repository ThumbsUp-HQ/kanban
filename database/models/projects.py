"""Project and planning models: projects, states, priorities, labels, cycles, modules, views."""

import uuid
from datetime import date
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import (
    Base,
    ObjectKind,
    ViewLayout,
    object_kind_pg_enum,
    view_layout_pg_enum,
)


class Project(Base):
    """Project entity scoping workflow states, cycles, modules, and issues."""

    __tablename__ = "projects"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "object_type"],
            ["objects.id", "objects.object_type"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("workspace_id", "identifier", name="projects_workspace_id_identifier_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    object_type: Mapped[ObjectKind] = mapped_column(
        object_kind_pg_enum, nullable=False, server_default=text("'project'")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    identifier: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description_markdown: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("''")
    )
    modules_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    issue_seq_counter: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    auto_archive_days: Mapped[int | None] = mapped_column(Integer, nullable=True)


class WorkflowState(Base):
    """Configurable project lifecycle workflow state."""

    __tablename__ = "workflow_states"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="workflow_states_project_id_name_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    state_group: Mapped[str] = mapped_column(String, nullable=False)
    color_hex: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    wip_soft_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wip_hard_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ProjectPriority(Base):
    """Custom project priority level and ordering token."""

    __tablename__ = "project_priorities"
    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="project_priorities_project_id_slug_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    emoji: Mapped[str | None] = mapped_column(String, nullable=True)
    color_hex: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class ProjectLabel(Base):
    """Categorization label bound to a project."""

    __tablename__ = "project_labels"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="project_labels_project_id_name_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    color_hex: Mapped[str] = mapped_column(String, nullable=False)
    exclusive_group: Mapped[str | None] = mapped_column(String, nullable=True)


class Cycle(Base):
    """Timeboxed development sprint/iteration."""

    __tablename__ = "cycles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "object_type"],
            ["objects.id", "objects.object_type"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    object_type: Mapped[ObjectKind] = mapped_column(
        object_kind_pg_enum, nullable=False, server_default=text("'cycle'")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'upcoming'"))
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Module(Base):
    """Feature or initiative grouping within a project."""

    __tablename__ = "modules"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "object_type"],
            ["objects.id", "objects.object_type"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("project_id", "name", name="modules_project_id_name_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    object_type: Mapped[ObjectKind] = mapped_column(
        object_kind_pg_enum, nullable=False, server_default=text("'module'")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class ProjectModuleDefault(Base):
    """Default module assignments configured per project."""

    __tablename__ = "project_module_defaults"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), primary_key=True
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )


class View(Base):
    """Saved query layout view (board, list, calendar, timeline, table)."""

    __tablename__ = "views"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "object_type"],
            ["objects.id", "objects.object_type"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    object_type: Mapped[ObjectKind] = mapped_column(
        object_kind_pg_enum, nullable=False, server_default=text("'view'")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True
    )
    owner_principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="RESTRICT"), nullable=False
    )
    visibility: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'project'")
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    summary_markdown: Mapped[str] = mapped_column(String, nullable=False, server_default=text("''"))
    summary_sha256: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        Computed("digest(summary_markdown, 'sha256'::text)", persisted=True),
        nullable=True,
    )
    layout: Mapped[ViewLayout] = mapped_column(
        view_layout_pg_enum, nullable=False, server_default=text("'board'")
    )
    group_by: Mapped[str | None] = mapped_column(String, nullable=True)
    sub_group_by: Mapped[str | None] = mapped_column(String, nullable=True)
    filters_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    display_props_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    wip_limits_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'")
    )
    sort_rank: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'a0'"))
