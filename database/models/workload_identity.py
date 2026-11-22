# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy models for workload identity policies and JTI replays.

KB-AUTH-OIDC-EXCHANGE-01 (KAN-74).
"""

from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003  # Runtime import required for SQLAlchemy Mapped[datetime]
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base


class WorkloadIdentityPolicy(Base):
    """Workload identity federation policy mapping external OIDC claims to MCP boundaries."""

    __tablename__ = "workload_identity_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuidv7(),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    issuer: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )
    client_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    subject_pattern: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    required_claims_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    surface: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    allowed_project_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
        server_default=text("'{}'::uuid[]"),
    )
    capability_mask: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="255",
    )
    allowed_cidrs: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text),
        nullable=True,
        server_default=text("'{}'::text[]"),
    )
    max_ttl_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="3600",
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )

    replays: Mapped[list[WorkloadJtiReplay]] = relationship(
        "WorkloadJtiReplay",
        back_populates="policy",
        cascade="all, delete-orphan",
    )


class WorkloadJtiReplay(Base):
    """Replay prevention record for external OIDC JWT IDs."""

    __tablename__ = "workload_jti_replays"
    __table_args__ = (
        UniqueConstraint("policy_id", "jti", name="uq_workload_jti_replays_policy_jti"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuidv7(),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workload_identity_policies.id", ondelete="CASCADE"),
        nullable=False,
    )
    jti: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )

    policy: Mapped[WorkloadIdentityPolicy] = relationship(
        "WorkloadIdentityPolicy",
        back_populates="replays",
    )
