# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Session lifecycle management, rotation, elevation, and timeouts (KB-P2-02)."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from database.models.auth import UserSession
from kanban.auth.sessions.cookies import (
    encode_session_cookie,
    generate_session_token,
    hash_session_token,
    parse_session_cookie,
)
from kanban.auth.sessions.csrf import generate_csrf_token

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "DEFAULT_AAL2_FRESH_SECONDS",
    "DEFAULT_ABSOLUTE_SECONDS",
    "DEFAULT_IDLE_SECONDS",
    "MAX_POLICY_SECONDS",
    "MIN_POLICY_SECONDS",
    "IssuedSession",
    "SessionPolicy",
    "SessionService",
]

DEFAULT_IDLE_SECONDS: Final[int] = 28800  # 8 hours
DEFAULT_ABSOLUTE_SECONDS: Final[int] = 604800  # 7 days
DEFAULT_AAL2_FRESH_SECONDS: Final[int] = 900  # 15 minutes

MIN_POLICY_SECONDS: Final[int] = 300  # 5 minutes
MAX_POLICY_SECONDS: Final[int] = 2592000  # 30 days


@dataclass(frozen=True)
class SessionPolicy:
    """Timeout configuration and policy enforcement for server-side sessions."""

    idle_seconds: int = DEFAULT_IDLE_SECONDS
    absolute_seconds: int = DEFAULT_ABSOLUTE_SECONDS
    aal2_fresh_seconds: int = DEFAULT_AAL2_FRESH_SECONDS

    def __post_init__(self) -> None:
        """Validate timeout parameters are within bounds [300, 2592000]."""
        for name, val in (
            ("idle_seconds", self.idle_seconds),
            ("absolute_seconds", self.absolute_seconds),
            ("aal2_fresh_seconds", self.aal2_fresh_seconds),
        ):
            if val < MIN_POLICY_SECONDS or val > MAX_POLICY_SECONDS:
                msg = (
                    f"Session policy {name} ({val}s) outside allowed bounds "
                    f"[{MIN_POLICY_SECONDS}, {MAX_POLICY_SECONDS}]"
                )
                raise ValueError(msg)

    @classmethod
    def from_env(cls) -> SessionPolicy:
        """Construct SessionPolicy from environment variables with defaults."""
        idle_raw = os.environ.get("KANBAN_SESSION_IDLE_SECONDS")
        abs_raw = os.environ.get("KANBAN_SESSION_ABSOLUTE_SECONDS")
        aal2_raw = os.environ.get("KANBAN_AAL2_FRESH_SECONDS")

        idle = int(idle_raw) if idle_raw is not None else DEFAULT_IDLE_SECONDS
        absolute = int(abs_raw) if abs_raw is not None else DEFAULT_ABSOLUTE_SECONDS
        aal2 = int(aal2_raw) if aal2_raw is not None else DEFAULT_AAL2_FRESH_SECONDS

        return cls(idle_seconds=idle, absolute_seconds=absolute, aal2_fresh_seconds=aal2)


@dataclass(frozen=True)
class IssuedSession:
    """Session credentials and metadata issued upon login or rotation."""

    session_id: uuid.UUID
    token: bytes
    cookie_val: str
    csrf_token: str
    aal_level: int
    mfa_pending: bool
    idle_expires_at: datetime
    absolute_expires_at: datetime


class SessionService:
    """Service encapsulating database session operations and token issuance."""

    def __init__(
        self,
        session_hmac_key: bytes,
        policy: SessionPolicy | None = None,
    ) -> None:
        """Initialize service with HMAC key and timeout policy."""
        self._session_hmac_key = session_hmac_key
        self._policy = policy or SessionPolicy.from_env()

    @property
    def policy(self) -> SessionPolicy:
        """Return active session timeout policy."""
        return self._policy

    @property
    def session_hmac_key(self) -> bytes:
        """Return session HMAC key used for signing cookies and CSRF tokens."""
        return self._session_hmac_key

    async def create_after_login(  # noqa: PLR0913
        self,
        session: AsyncSession,
        *,
        principal_id: uuid.UUID,
        workspace_id: uuid.UUID,
        auth_card_id: uuid.UUID | None = None,
        aal_level: int = 1,
        mfa_pending: bool = False,
        existing_cookie: str | None = None,
        existing_cookie_val: str | None = None,
    ) -> IssuedSession:
        """Create new session upon login, revoking any pre-existing session (fixation defense)."""
        # Session fixation defense: revoke previous session presented in request
        cookie_to_revoke = existing_cookie or existing_cookie_val
        if cookie_to_revoke:
            old_token = parse_session_cookie(cookie_to_revoke, self._session_hmac_key)
            if old_token:
                old_sha = hash_session_token(old_token)
                resolved = await self.resolve_session(session, old_sha)
                if resolved:
                    await self.logout(session, resolved.id)

        session_id = uuid.uuid4()
        token = generate_session_token()
        token_sha256 = hash_session_token(token)

        now = datetime.now(UTC)
        idle_expires_at = now + timedelta(seconds=self._policy.idle_seconds)
        absolute_expires_at = now + timedelta(seconds=self._policy.absolute_seconds)

        aal2_verified_at = now if aal_level == 2 else None  # noqa: PLR2004

        stmt = text(
            "SELECT kb_auth.session_create("
            "  :p_id, :p_token_sha256, :p_principal_id, :p_workspace_id, "
            "  :p_auth_card_id, :p_aal_level, :p_aal2_verified_at, :p_mfa_pending, "
            "  :p_idle_expires_at, :p_absolute_expires_at, :p_rotated_from_id"
            ")"
        )
        await session.execute(
            stmt,
            {
                "p_id": session_id,
                "p_token_sha256": token_sha256,
                "p_principal_id": principal_id,
                "p_workspace_id": workspace_id,
                "p_auth_card_id": auth_card_id,
                "p_aal_level": aal_level,
                "p_aal2_verified_at": aal2_verified_at,
                "p_mfa_pending": mfa_pending,
                "p_idle_expires_at": idle_expires_at,
                "p_absolute_expires_at": absolute_expires_at,
                "p_rotated_from_id": None,
            },
        )

        cookie_val = encode_session_cookie(token, self._session_hmac_key)
        csrf_token = generate_csrf_token(session_id, self._session_hmac_key)

        return IssuedSession(
            session_id=session_id,
            token=token,
            cookie_val=cookie_val,
            csrf_token=csrf_token,
            aal_level=aal_level,
            mfa_pending=mfa_pending,
            idle_expires_at=idle_expires_at,
            absolute_expires_at=absolute_expires_at,
        )

    async def elevate_aal(
        self,
        session: AsyncSession,
        *,
        old_session_id: uuid.UUID,
        new_aal: int = 2,
    ) -> IssuedSession:
        """Elevate AAL level by rotating session token and updating credentials."""
        token = generate_session_token()
        token_sha256 = hash_session_token(token)

        stmt = text("SELECT kb_auth.session_rotate(:p_old_id, :p_new_token_sha256, :p_aal)")
        res = await session.execute(
            stmt,
            {
                "p_old_id": old_session_id,
                "p_new_token_sha256": token_sha256,
                "p_aal": new_aal,
            },
        )
        new_id = res.scalar_one()

        # Fetch newly rotated row to obtain preserved absolute expiration
        resolved = await self.resolve_session(session, token_sha256)
        if not resolved:
            msg = "Rotated session could not be resolved"
            raise RuntimeError(msg)

        cookie_val = encode_session_cookie(token, self._session_hmac_key)
        csrf_token = generate_csrf_token(new_id, self._session_hmac_key)

        return IssuedSession(
            session_id=new_id,
            token=token,
            cookie_val=cookie_val,
            csrf_token=csrf_token,
            aal_level=new_aal,
            mfa_pending=resolved.mfa_pending,
            idle_expires_at=resolved.idle_expires_at,
            absolute_expires_at=resolved.absolute_expires_at,
        )

    async def logout(self, session: AsyncSession, session_id: uuid.UUID) -> bool:
        """Revoke active session."""
        stmt = text("SELECT kb_auth.session_revoke(:p_id)")
        res = await session.execute(stmt, {"p_id": session_id})
        return bool(res.scalar_one())

    async def resolve_session(
        self, session: AsyncSession, token_sha256: bytes
    ) -> UserSession | None:
        """Resolve active non-revoked session by SHA-256 token digest."""
        stmt = text("SELECT * FROM kb_auth.session_resolve(:p_token_sha256)")
        res = await session.execute(stmt, {"p_token_sha256": token_sha256})
        row = res.mappings().first()
        if not row:
            return None

        # Reconstruct UserSession object (token_sha256 omitted from SELECT)
        data = dict(row)
        data["token_sha256"] = token_sha256
        return UserSession(**data)

    async def revoke_all_for_principal(self, session: AsyncSession, principal_id: uuid.UUID) -> int:
        """Revoke all active sessions for a principal."""
        stmt = text("SELECT kb_auth.session_revoke_all_for_principal(:p_id)")
        res = await session.execute(stmt, {"p_id": principal_id})
        return int(res.scalar_one())
