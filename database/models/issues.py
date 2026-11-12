"""Issue models: issues, issue_modules, issue_assignees, labels, subscriptions, comments."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base, LtreeType, ObjectKind, object_kind_pg_enum


class Issue(Base):
    """Core kanban ticket/issue entity in the Universal Object Graph."""

    __tablename__ = "issues"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "object_type"],
            ["objects.id", "objects.object_type"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("project_id", "sequence_id", name="issues_project_id_sequence_id_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    object_type: Mapped[ObjectKind] = mapped_column(
        object_kind_pg_enum, nullable=False, server_default=text("'issue'")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    sequence_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    description_markdown: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("''")
    )
    description_sha256: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        Computed("digest(description_markdown, 'sha256'::text)", persisted=True),
        nullable=True,
    )
    state_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_states.id", ondelete="RESTRICT"), nullable=False
    )
    pending_transition_exec_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    priority_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_priorities.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    original_created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    creator_modified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    creator_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cycles.id", ondelete="SET NULL"), nullable=True
    )
    parent_issue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("issues.id", ondelete="SET NULL"), nullable=True
    )
    ancestry_path: Mapped[str] = mapped_column(LtreeType, nullable=False)
    board_rank: Mapped[str] = mapped_column(String, nullable=False)
    search_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "(setweight(to_tsvector('english'::regconfig, "
            "COALESCE(summary, ''::text)), 'A'::\"char\") "
            "|| setweight(build_markdown_tsvector(description_markdown), 'B'::\"char\"))",
            persisted=True,
        ),
        nullable=True,
    )


class IssueModule(Base):
    """Many-to-many join between issues and modules."""

    __tablename__ = "issue_modules"

    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("modules.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )


class IssueAssignee(Base):
    """Hybrid assignee join: principal reference or free-text assignee."""

    __tablename__ = "issue_assignees"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    principal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), nullable=True
    )
    free_text_assignee: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class IssueLabel(Base):
    """Many-to-many join between issues and project labels."""

    __tablename__ = "issue_labels"

    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
    label_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_labels.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )


class IssueSubscription(Base):
    """Principal subscription status and notification preferences for an issue."""

    __tablename__ = "issue_subscriptions"

    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), primary_key=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    source: Mapped[str] = mapped_column(String, nullable=False)
    is_muted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class IssueComment(Base):
    """Threaded issue comment storing canonical UTF-8 markdown and SHA-256 digest."""

    __tablename__ = "issue_comments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    parent_comment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("issue_comments.id", ondelete="CASCADE"), nullable=True
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="RESTRICT"), nullable=False
    )
    body_markdown: Mapped[str] = mapped_column(String, nullable=False)
    body_sha256: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        Computed("digest(body_markdown, 'sha256'::text)", persisted=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommentReaction(Base):
    """Emoji reaction on an issue comment (KB-P3-05)."""

    __tablename__ = "comment_reactions"

    comment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("issue_comments.id", ondelete="CASCADE"), primary_key=True
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), primary_key=True
    )
    emoji: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
