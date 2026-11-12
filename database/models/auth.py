# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Authentication models: auth_provider_cards and sessions (KB-P2-03, KB-P2-02)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from database.models.base import Base


class AuthProviderCard(Base):
    """Multi-Card Auth Studio provider configuration and envelope-encrypted secrets."""

    __tablename__ = "auth_provider_cards"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    provider_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    slug: Mapped[str] = mapped_column(String(48), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    button_subtext: Mapped[str | None] = mapped_column(String(255), nullable=True)
    icon_preset: Mapped[str] = mapped_column(
        String(64), nullable=False, default="key", server_default=text("'key'")
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    sort_rank: Mapped[str] = mapped_column(Text(collation="C"), nullable=False)
    auto_provision_users: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    allowed_email_domains: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default=text("'{}'")
    )
    public_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    encrypted_secret_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    wrapped_dek: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    dek_kid: Mapped[str] = mapped_column(
        String(64), nullable=False, default="kek-v1", server_default=text("'kek-v1'")
    )
    last_health_status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UNVERIFIED", server_default=text("'UNVERIFIED'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    def __repr__(self) -> str:
        """Sanitized representation omitting encrypted_secret_blob and wrapped_dek bytes."""
        return (
            f"<AuthProviderCard id={self.id} slug={self.slug!r} "
            f"provider_kind={self.provider_kind!r} is_enabled={self.is_enabled} "
            f"sort_rank={self.sort_rank!r} dek_kid={self.dek_kid!r}>"
        )

    def __str__(self) -> str:
        """Sanitized string representation matching repr."""
        return self.__repr__()


class UserSession(Base):
    """Server-side authenticated user session (KB-P2-02)."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    token_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    auth_card_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("auth_provider_cards.id", ondelete="CASCADE"), nullable=True
    )
    aal_level: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    aal2_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mfa_pending: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_from_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        """Sanitized representation omitting token_sha256."""
        return (
            f"<UserSession id={self.id} principal_id={self.principal_id} "
            f"workspace_id={self.workspace_id} aal_level={self.aal_level} "
            f"mfa_pending={self.mfa_pending} idle_expires_at={self.idle_expires_at} "
            f"revoked_at={self.revoked_at}>"
        )

    def __str__(self) -> str:
        """Sanitized string representation matching repr."""
        return self.__repr__()


class OidcAuthRequest(Base):
    """Temporary OIDC and OAuth2 authentication request and state tracking (KB-P2-06)."""

    __tablename__ = "oidc_auth_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_provider_cards.id", ondelete="CASCADE"), nullable=False
    )
    state_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    code_verifier_sealed: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    browser_binding_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    return_to: Mapped[str] = mapped_column(
        Text, nullable=False, default="/", server_default=text("'/'")
    )
    link_intent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("principals.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    def __repr__(self) -> str:
        """Sanitized representation omitting sensitive cryptographic hashes."""
        return (
            f"<OidcAuthRequest id={self.id} card_id={self.card_id} "
            f"expires_at={self.expires_at} consumed_at={self.consumed_at}>"
        )

    def __str__(self) -> str:
        """Sanitized string representation matching repr."""
        return self.__repr__()


class LdapGroupMapping(Base):
    """LDAP group DN to workspace group mapping (KB-P2-07)."""

    __tablename__ = "ldap_group_mappings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_provider_cards.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    ldap_dn: Mapped[str] = mapped_column(Text, nullable=False)
    group_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    def __repr__(self) -> str:
        """Sanitized representation of LDAP group mapping."""
        return (
            f"<LdapGroupMapping id={self.id} card_id={self.card_id} "
            f"ldap_dn={self.ldap_dn!r} group_name={self.group_name!r}>"
        )

    def __str__(self) -> str:
        """Sanitized string representation matching repr."""
        return self.__repr__()
