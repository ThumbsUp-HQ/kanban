# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""SQLAlchemy models for OAuth 2.1 authorization server (KB-P4-02b / S11.1)."""

from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003  # Runtime import required for SQLAlchemy Mapped[datetime]
from typing import Literal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, UUID
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base

OAuthClientType = Literal["public", "confidential"]
OAuthClientStatus = Literal["active", "pending_admin_approval", "disabled", "suspended", "revoked"]
OAuthSurface = Literal["agent", "docs", "admin"]


class OAuthClient(Base):
    """Registered OAuth 2.1 client (RFC 7591 dynamic registration)."""

    __tablename__ = "oauth_clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuidv7(),
    )
    client_id: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
        index=True,
    )
    client_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    client_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="public",
        server_default="public",
    )
    client_secret_hash: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    client_secret_prefix: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    redirect_uris: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        server_default="active",
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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

    __table_args__ = (
        CheckConstraint(
            "client_type IN ('public', 'confidential')",
            name="oauth_clients_type_check",
        ),
        CheckConstraint(
            "status IN ('active', 'pending_admin_approval', 'disabled', 'suspended', 'revoked')",
            name="oauth_clients_status_check",
        ),
    )


class OAuthGrant(Base):
    """User-approved consent grant for an OAuth client and target surface."""

    __tablename__ = "oauth_grants"

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
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("oauth_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    surface: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
    )
    allowed_projects: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "surface IN ('agent', 'docs', 'admin')",
            name="oauth_grants_surface_check",
        ),
    )


class OAuthAuthorizationCode(Base):
    """Single-use authorization code with mandatory PKCE S256."""

    __tablename__ = "oauth_authorization_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuidv7(),
    )
    code_sha256: Mapped[bytes] = mapped_column(
        BYTEA,
        unique=True,
        nullable=False,
        index=True,
    )
    grant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("oauth_grants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("oauth_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_challenge: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    code_challenge_method: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="S256",
        server_default="S256",
    )
    resource: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    redirect_uri: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    surface: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
    )
    allowed_projects: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "octet_length(code_sha256) = 32",
            name="oauth_codes_sha256_len_check",
        ),
        CheckConstraint(
            "code_challenge_method = 'S256'",
            name="oauth_codes_challenge_method_check",
        ),
        CheckConstraint(
            "surface IN ('agent', 'docs', 'admin')",
            name="oauth_codes_surface_check",
        ),
    )


class OAuthRefreshToken(Base):
    """Single-use rotated refresh token stored as SHA-256 digest."""

    __tablename__ = "oauth_refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuidv7(),
    )
    token_sha256: Mapped[bytes] = mapped_column(
        BYTEA,
        unique=True,
        nullable=False,
        index=True,
    )
    grant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("oauth_grants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("oauth_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "octet_length(token_sha256) = 32",
            name="oauth_refresh_sha256_len_check",
        ),
    )


class OAuthRevokedJti(Base):
    """Deny-list of revoked JWT IDs (JTIs) until their natural expiration."""

    __tablename__ = "oauth_revoked_jtis"

    jti: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
    )
    grant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("oauth_grants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )


class OAuthDeviceCode(Base):
    """RFC 8628 Headless CLI device authorization code."""

    __tablename__ = "oauth_device_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.uuidv7(),
    )
    device_code_sha256: Mapped[bytes] = mapped_column(
        BYTEA,
        unique=True,
        nullable=False,
        index=True,
    )
    user_code: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("oauth_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    resource: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    surface: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
    )
    requested_scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
    )
    allowed_projects: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
    )
    approved_grant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("oauth_grants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("principals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approved_scopes: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    interval_sec: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default="5",
    )

    __table_args__ = (
        CheckConstraint(
            "octet_length(device_code_sha256) = 32",
            name="oauth_device_codes_sha256_len_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'denied', 'expired')",
            name="oauth_device_codes_status_check",
        ),
        CheckConstraint(
            "surface IN ('agent', 'docs', 'admin')",
            name="oauth_device_codes_surface_check",
        ),
        CheckConstraint(
            "interval_sec >= 1",
            name="oauth_device_codes_interval_check",
        ),
    )
