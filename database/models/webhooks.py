# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy 2.0 ORM models for SCM webhooks and outbound bus (KB-DEVSECOPS-BUS-01)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class ScmArtifact(Base):
    """Git and SCM provenance artifact linked to Universal Object Graph."""

    __tablename__ = "scm_artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_kind IN ('branch', 'commit', 'pull_request', 'ci_run')",
            name="ck_scm_artifacts_kind",
        ),
        UniqueConstraint(
            "repo_binding_id",
            "artifact_kind",
            "external_id",
            name="uq_scm_artifacts_repo_kind_ext",
        ),
        Index("idx_scm_artifacts_ws_proj", "workspace_id", "project_id"),
        Index("idx_scm_artifacts_repo", "repo_binding_id"),
        Index("idx_scm_artifacts_obj", "object_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    object_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE"), unique=True, nullable=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    repo_binding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_repo_bindings.id", ondelete="CASCADE"), nullable=False
    )
    artifact_kind: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    head_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class ScmWebhookDelivery(Base):
    """Inbound SCM webhook delivery record for idempotency and replay deduplication."""

    __tablename__ = "scm_webhook_deliveries"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('github', 'gitlab', 'forgejo')",
            name="ck_scm_webhook_deliveries_provider",
        ),
        UniqueConstraint(
            "repo_binding_id",
            "delivery_id",
            name="uq_scm_webhook_deliveries_repo_delivery",
        ),
        Index("idx_scm_webhook_deliveries_ws", "workspace_id"),
        Index("idx_scm_webhook_deliveries_repo", "repo_binding_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    repo_binding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_repo_bindings.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class WebhookSubscription(Base):
    """Outbound event webhook subscription configured by workspace/project admin."""

    __tablename__ = "webhook_subscriptions"
    __table_args__ = (
        CheckConstraint("char_length(target_url) <= 2048", name="ck_webhook_subscriptions_url"),
        Index("idx_webhook_subscriptions_ws", "workspace_id"),
        Index("idx_webhook_subscriptions_proj", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    secret_dek_kid: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("principals.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )


class WebhookDelivery(Base):
    """Audit log and retry tracker for outbound webhook dispatches."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'delivered', 'failed', 'dead_letter')",
            name="ck_webhook_deliveries_status",
        ),
        Index("idx_webhook_deliveries_ws", "workspace_id"),
        Index("idx_webhook_deliveries_sub", "subscription_id"),
        Index("idx_webhook_deliveries_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    event_topic: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
