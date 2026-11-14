# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy 2.0 ORM model for destructive confirmation tokens (KB-P4-12, S11.4)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base
from database.models.spine import ObjectKind, object_kind_pg_enum


class DestructiveConfirmationToken(Base):
    """Two-stage destructive confirmation token cryptographically bound to caller and blast hash."""

    __tablename__ = "destructive_confirmation_tokens"
    __table_args__ = (
        CheckConstraint(
            "octet_length(token_sha256) = 32",
            name="destructive_confirmation_tokens_token_sha256_check",
        ),
        CheckConstraint(
            "mode IN ('trash', 'permanent_purge', 'restore')",
            name="destructive_confirmation_tokens_mode_check",
        ),
        CheckConstraint(
            "char_length(blast_hash) = 64",
            name="destructive_confirmation_tokens_blast_hash_check",
        ),
        CheckConstraint(
            "expires_at <= created_at + interval '300 seconds'",
            name="destructive_confirmation_tokens_expires_check",
        ),
        ForeignKeyConstraint(
            ["target_object_id", "target_object_type"],
            ["objects.id", "objects.object_type"],
            ondelete="CASCADE",
            name="destructive_confirmation_tokens_target_fk",
        ),
        Index(
            "destructive_tokens_lookup_idx",
            "token_sha256",
            postgresql_where=text("consumed_at IS NULL"),
        ),
        Index(
            "destructive_tokens_ws_target_idx",
            "workspace_id",
            "target_object_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=text("uuidv7()"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_sha256: Mapped[bytes] = mapped_column(
        LargeBinary(32),
        unique=True,
        nullable=False,
    )
    caller_principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_object_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
    )
    target_object_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    blast_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    confirm_phrase: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    blast_summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("clock_timestamp()"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
