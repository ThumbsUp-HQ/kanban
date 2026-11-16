# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy 2.0 ORM models for remote_runners and enrollment tokens (KB-P5-22a, S14.2, S11.4)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class RemoteRunnerEnrollmentToken(Base):
    """Single-use enrollment tokens for remote runner mTLS registration."""

    __tablename__ = "remote_runner_enrollment_tokens"
    __table_args__ = (
        CheckConstraint(
            "pool_slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'",
            name="chk_runner_token_pool_slug",
        ),
        CheckConstraint(
            "octet_length(token_sha256) = 32",
            name="chk_runner_token_sha256_len",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    pool_slug: Mapped[str] = mapped_column(Text, nullable=False)
    token_sha256: Mapped[bytes] = mapped_column(BYTEA, nullable=False, unique=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_by_runner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class RemoteRunner(Base):
    """Registered remote execution host authenticated via mTLS client certificates."""

    __tablename__ = "remote_runners"
    __table_args__ = (
        CheckConstraint(
            "pool_slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'",
            name="chk_remote_runner_pool_slug",
        ),
        CheckConstraint(
            "char_length(btrim(hostname)) BETWEEN 1 AND 253",
            name="chk_remote_runner_hostname",
        ),
        CheckConstraint(
            "octet_length(client_cert_sha256) = 32",
            name="chk_remote_runner_cert_sha256_len",
        ),
        CheckConstraint(
            "status IN ('online', 'offline', 'revoked')",
            name="chk_remote_runner_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    pool_slug: Mapped[str] = mapped_column(Text, nullable=False)
    hostname: Mapped[str] = mapped_column(Text, nullable=False)
    client_cert_sha256: Mapped[bytes] = mapped_column(BYTEA, nullable=False, unique=True)
    cert_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capabilities_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="offline", server_default=text("'offline'")
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("principals.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
