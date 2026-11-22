"""Knowledge base models: docs, pages, page_versions, stickies."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base, LtreeType, ObjectKind, object_kind_pg_enum


class Doc(Base):
    """Top-level document entity anchoring hierarchical pages."""

    __tablename__ = "docs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "object_type"],
            ["objects.id", "objects.object_type"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    object_type: Mapped[ObjectKind] = mapped_column(
        object_kind_pg_enum, nullable=False, server_default=text("'doc'")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    body_markdown: Mapped[str] = mapped_column(String, nullable=False, server_default=text("''"))
    body_sha256: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        Computed("digest(body_markdown, 'sha256'::text)", persisted=True),
        nullable=True,
    )
    hierarchy_path: Mapped[str] = mapped_column(LtreeType, nullable=False)
    version_seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    provenance_tier: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'trusted_member'")
    )
    is_untrusted_content: Mapped[bool | None] = mapped_column(
        Boolean,
        Computed(
            "provenance_tier IN ("
            "'imported', 'external_webhook', 'public_reporter', 'untrusted_intake'"
            ")",
            persisted=True,
        ),
        nullable=True,
    )
    search_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "(setweight(to_tsvector('english'::regconfig, "
            "COALESCE(title, ''::text)), 'A'::\"char\") "
            "|| setweight(build_markdown_tsvector(body_markdown), 'B'::\"char\"))",
            persisted=True,
        ),
        nullable=True,
    )


class Page(Base):
    """Hierarchical documentation page belonging to a Doc."""

    __tablename__ = "pages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "object_type"],
            ["objects.id", "objects.object_type"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    object_type: Mapped[ObjectKind] = mapped_column(
        object_kind_pg_enum, nullable=False, server_default=text("'page'")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    doc_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("docs.id", ondelete="CASCADE"), nullable=False
    )
    parent_page_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    body_markdown: Mapped[str] = mapped_column(String, nullable=False, server_default=text("''"))
    body_sha256: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        Computed("digest(body_markdown, 'sha256'::text)", persisted=True),
        nullable=True,
    )
    hierarchy_path: Mapped[str] = mapped_column(LtreeType, nullable=False)
    version_seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    provenance_tier: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'trusted_member'")
    )
    is_untrusted_content: Mapped[bool | None] = mapped_column(
        Boolean,
        Computed(
            "provenance_tier IN ("
            "'imported', 'external_webhook', 'public_reporter', 'untrusted_intake'"
            ")",
            persisted=True,
        ),
        nullable=True,
    )
    search_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "(setweight(to_tsvector('english'::regconfig, "
            "COALESCE(title, ''::text)), 'A'::\"char\") "
            "|| setweight(build_markdown_tsvector(body_markdown), 'B'::\"char\"))",
            persisted=True,
        ),
        nullable=True,
    )
    sort_rank: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'a0'"))


class PageVersion(Base):
    """Immutable version snapshot of a documentation page."""

    __tablename__ = "page_versions"

    page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), primary_key=True
    )
    version_seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    body_markdown: Mapped[str] = mapped_column(String, nullable=False)
    body_sha256: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        Computed("digest(body_markdown, 'sha256'::text)", persisted=True),
        nullable=True,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("principals.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class Sticky(Base):
    """Lightweight project sticky note with auto-detected promotion heuristics."""

    __tablename__ = "stickies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "object_type"],
            ["objects.id", "objects.object_type"],
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    object_type: Mapped[ObjectKind] = mapped_column(
        object_kind_pg_enum, nullable=False, server_default=text("'sticky'")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True
    )
    body_markdown: Mapped[str] = mapped_column(String, nullable=False, server_default=text("''"))
    body_sha256: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        Computed("digest(body_markdown, 'sha256'::text)", persisted=True),
        nullable=True,
    )
    color_token: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'amber'"))
    promotion_recommended: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    promotion_snoozed_at_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    promoted_to_doc_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("docs.id", ondelete="SET NULL"), nullable=True
    )
    sort_rank: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'a0'"))
    provenance_tier: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'trusted_member'")
    )
    is_untrusted_content: Mapped[bool | None] = mapped_column(
        Boolean,
        Computed(
            "provenance_tier IN ("
            "'imported', 'external_webhook', 'public_reporter', 'untrusted_intake'"
            ")",
            persisted=True,
        ),
        nullable=True,
    )
    search_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "build_markdown_tsvector(body_markdown)",
            persisted=True,
        ),
        nullable=True,
    )
