"""Attachment model: attachments table."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class Attachment(Base):
    """Media and file attachment associated with a project or issue."""

    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint(
            "char_length(btrim(original_filename)) BETWEEN 1 AND 255",
            name="attachments_original_filename_check",
        ),
        CheckConstraint(
            "content_type IN ("
            "'image/png','image/jpeg','image/webp','image/avif','image/gif','image/svg+xml','application/pdf'"
            ")",
            name="attachments_content_type_check",
        ),
        CheckConstraint(
            "byte_size BETWEEN 1 AND 26214400",
            name="attachments_byte_size_check",
        ),
        CheckConstraint(
            "pixel_width IS NULL OR pixel_width > 0",
            name="attachments_pixel_width_check",
        ),
        CheckConstraint(
            "pixel_height IS NULL OR pixel_height > 0",
            name="attachments_pixel_height_check",
        ),
        CheckConstraint(
            "page_count IS NULL OR page_count > 0",
            name="attachments_page_count_check",
        ),
        CheckConstraint(
            "octet_length(blob_sha256) = 32",
            name="attachments_blob_sha256_check",
        ),
        CheckConstraint(
            "storage_key ~ '^sha256/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}$'",
            name="attachments_storage_key_check",
        ),
        Index("attachments_workspace_project_idx", "workspace_id", "project_id"),
        Index("attachments_issue_id_idx", "issue_id"),
        Index("attachments_uploaded_by_idx", "uploaded_by_id"),
        Index("attachments_storage_key_idx", "storage_key"),
        Index("attachments_blob_sha256_idx", "blob_sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    issue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("issues.id", ondelete="SET NULL"),
        nullable=True,
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    content_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    byte_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    pixel_width: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    pixel_height: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    page_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    blob_sha256: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
