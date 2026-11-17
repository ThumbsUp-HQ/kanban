# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Authentication models: auth_provider_cards and sessions (KB-P2-03, KB-P2-02)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
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
    last_admin_handshake_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    is_persistent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

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


class LocalAdminCredential(Base):
    """Local administrator credential with Argon2id hash and pepper key id (KB-P2-04)."""

    __tablename__ = "local_admin_credentials"

    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), primary_key=True
    )
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    pepper_kid: Mapped[str] = mapped_column(
        Text, nullable=False, default="pepper-v1", server_default=text("'pepper-v1'")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    def __repr__(self) -> str:
        """Sanitized representation omitting password_hash."""
        return (
            f"<LocalAdminCredential principal_id={self.principal_id} "
            f"username={self.username!r} pepper_kid={self.pepper_kid!r}>"
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
    remember_me: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
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


class TotpFactor(Base):
    """RFC 6238 TOTP authentication factor (KB-P2-05a)."""

    __tablename__ = "totp_factors"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    encrypted_secret_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dek_kid: Mapped[str] = mapped_column(
        Text, nullable=False, default="kek-v1", server_default=text("'kek-v1'")
    )
    last_accepted_step: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    def __repr__(self) -> str:
        """Sanitized representation omitting encrypted secret bytes."""
        return (
            f"<TotpFactor id={self.id} principal_id={self.principal_id} "
            f"status={self.status!r} last_accepted_step={self.last_accepted_step}>"
        )

    def __str__(self) -> str:
        """Sanitized string representation matching repr."""
        return self.__repr__()


class RecoveryCode(Base):
    """Hashed one-time backup recovery code (KB-P2-05a)."""

    __tablename__ = "recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    code_hmac: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )

    def __repr__(self) -> str:
        """Sanitized representation omitting code HMAC."""
        return (
            f"<RecoveryCode id={self.id} principal_id={self.principal_id} "
            f"used={self.used_at is not None}>"
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


class WebauthnCredential(Base):
    """FIDO2 / WebAuthn passkey credential (KB-P2-05b)."""

    __tablename__ = "webauthn_credentials"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sign_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    aaguid: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    transports: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    suspect_clone_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        """Sanitized representation omitting public key and raw credential bytes."""
        return (
            f"<WebauthnCredential id={self.id} principal_id={self.principal_id} "
            f"sign_count={self.sign_count} nickname={self.nickname!r} "
            f"suspect_clone={self.suspect_clone_at is not None}>"
        )

    def __str__(self) -> str:
        """Sanitized string representation matching repr."""
        return self.__repr__()


class WebauthnChallenge(Base):
    """Server-side single-use WebAuthn challenge (KB-P2-05b)."""

    __tablename__ = "webauthn_challenges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    challenge: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        """Sanitized representation omitting raw challenge bytes."""
        return (
            f"<WebauthnChallenge id={self.id} session_id={self.session_id} "
            f"purpose={self.purpose!r} expires_at={self.expires_at} "
            f"consumed={self.consumed_at is not None}>"
        )

    def __str__(self) -> str:
        """Sanitized string representation matching repr."""
        return self.__repr__()


class UserIdentity(Base):
    """External IdP identity mapping strictly bound by (auth_card_id, immutable_subject_id)."""

    __tablename__ = "user_identities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    auth_card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_provider_cards.id", ondelete="RESTRICT"), nullable=False
    )
    immutable_subject_id: Mapped[str] = mapped_column(String(255), nullable=False)
    email_at_link: Mapped[str | None] = mapped_column(String, nullable=True)
    subject_email_at_link: Mapped[str | None] = mapped_column(String, nullable=True)
    display_name_at_link: Mapped[str | None] = mapped_column(String, nullable=True)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        """Sanitized representation showing non-secret identity binding metadata."""
        return (
            f"<UserIdentity id={self.id} principal_id={self.principal_id} "
            f"auth_card_id={self.auth_card_id} last_login_at={self.last_login_at}>"
        )

    def __str__(self) -> str:
        """Sanitized string representation matching repr."""
        return self.__repr__()


class IdentityLinkIntent(Base):
    """Ephemeral single-use intent for explicit AAL2 identity linking (KB-P2-08)."""

    __tablename__ = "identity_link_intents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("principals.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    target_card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_provider_cards.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        """Sanitized representation of linking intent."""
        return (
            f"<IdentityLinkIntent id={self.id} principal_id={self.principal_id} "
            f"target_card_id={self.target_card_id} expires_at={self.expires_at} "
            f"consumed={self.consumed_at is not None}>"
        )

    def __str__(self) -> str:
        """Sanitized string representation matching repr."""
        return self.__repr__()


class SetupClaimToken(Base):
    """Single-use 256-bit first-boot setup claim token hashed at rest (KB-P2-12)."""

    __tablename__ = "setup_claim_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    token_hmac: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_by_principal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("principals.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        """Sanitized representation omitting sensitive token HMAC bytes."""
        return (
            f"<SetupClaimToken id={self.id} expires_at={self.expires_at} "
            f"consumed={self.consumed_at is not None} revoked={self.revoked_at is not None}>"
        )

    def __str__(self) -> str:
        """Sanitized string representation matching repr."""
        return self.__repr__()
