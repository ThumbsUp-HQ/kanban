# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Local Admin login service with constant-work verification and rate limiting (KB-P2-04)."""

from __future__ import annotations

import logging
import unicodedata
import uuid
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from kanban.api.problems import ProblemException
from kanban.api.request_id import format_log_actor, set_log_user
from kanban.auth.cards.repository import get_for_login, list_enabled_public
from kanban.auth.local.hashing import (
    DEFAULT_ARGON2_TIMEOUT_SECONDS,
    DUMMY_HASH,
    get_auth_pepper,
    hash_password,
    needs_rehash,
    verify_password,
)
from kanban.security.ratelimit import (
    AUTH_LOGIN_ACCOUNT,
    AUTH_LOGIN_IP,
    make_key,
)
from kanban.services.activity import ActivityEventType, record_activity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from database.models.auth import AuthProviderCard
    from kanban.auth.sessions.service import IssuedSession, SessionService
    from kanban.security.ratelimit.base import RateLimiter

logger = logging.getLogger(__name__)

__all__ = ["LocalAdminLoginService"]

MAX_USERNAME_LEN: Final[int] = 64
MAX_PASSWORD_LEN: Final[int] = 1024


class LocalAdminLoginService:
    """Authentication service for the break-glass Local Admin provider card."""

    def __init__(
        self,
        session_service: SessionService,
        rate_limiter: RateLimiter,
        session_hmac_key: bytes | None = None,
        auth_pepper: bytes | None = None,
        timeout_seconds: float = DEFAULT_ARGON2_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize service with session issuer, rate limiter, and cryptographic keys."""
        self._session_service = session_service
        self._rate_limiter = rate_limiter
        self._session_hmac_key = (
            session_hmac_key if session_hmac_key is not None else session_service.session_hmac_key
        )
        self._auth_pepper = auth_pepper
        self._timeout_seconds = timeout_seconds

    def _get_pepper(self) -> bytes:
        """Resolve active auth pepper key."""
        if self._auth_pepper is not None:
            return self._auth_pepper
        return get_auth_pepper()

    async def _check_rate_limits(self, client_ip: str, norm_username: str) -> tuple[bytes, bytes]:
        """Verify IP and account rate limits before performing credential verification."""
        ip_key = make_key(AUTH_LOGIN_IP, client_ip, session_hmac_key=self._session_hmac_key)
        ip_decision = await self._rate_limiter.hit(AUTH_LOGIN_IP, ip_key)
        if not ip_decision.allowed:
            raise ProblemException(
                code="RATE_LIMITED",
                status=429,
                title="Rate Limit Exceeded",
                detail="Rate limit exceeded for policy 'auth_login_ip'",
                headers={"Retry-After": str(ip_decision.retry_after_seconds)},
            )

        account_key = make_key(
            AUTH_LOGIN_ACCOUNT, norm_username, session_hmac_key=self._session_hmac_key
        )
        account_decision = await self._rate_limiter.hit(AUTH_LOGIN_ACCOUNT, account_key)
        if not account_decision.allowed:
            raise ProblemException(
                code="RATE_LIMITED",
                status=429,
                title="Rate Limit Exceeded",
                detail="Rate limit exceeded for policy 'auth_login_account'",
                headers={"Retry-After": str(account_decision.retry_after_seconds)},
            )
        return ip_key, account_key

    async def _find_local_admin_card(self, session: AsyncSession) -> AuthProviderCard | None:
        """Look up active LOCAL_ADMIN card if enabled."""
        enabled_cards = await list_enabled_public(session)
        local_cards = [c for c in enabled_cards if c.provider_kind == "LOCAL_ADMIN"]
        if not local_cards:
            return None
        return await get_for_login(session, local_cards[0].slug)

    async def _resolve_workspace_id(
        self,
        session: AsyncSession,
        explicit_ws_id: uuid.UUID | None,
        card: AuthProviderCard | None,
    ) -> uuid.UUID:
        """Determine effective workspace ID from explicit parameter, card, or system default."""
        if explicit_ws_id is not None:
            return explicit_ws_id
        if card is not None and card.workspace_id is not None:
            return card.workspace_id
        ws_stmt = text("SELECT id FROM workspaces ORDER BY created_at LIMIT 1")
        ws_res = (await session.execute(ws_stmt)).first()
        return ws_res[0] if ws_res is not None else uuid.UUID(int=0)

    async def login(  # noqa: PLR0913
        self,
        session: AsyncSession,
        *,
        username: str,
        password: str,
        client_ip: str,
        existing_cookie: str | None = None,
        workspace_id: uuid.UUID | None = None,
        remember_me: bool = True,
    ) -> IssuedSession:
        """Execute local admin login workflow with constant-work verification on all paths."""
        pepper = self._get_pepper()

        norm_username = unicodedata.normalize("NFKC", (username or "").strip()).lower()
        is_username_valid = 1 <= len(norm_username) <= MAX_USERNAME_LEN

        _, account_key = await self._check_rate_limits(client_ip, norm_username)

        card = await self._find_local_admin_card(session)
        card_ok = card is not None and card.is_enabled

        cred_row = None
        if is_username_valid:
            cred_stmt = text(
                "SELECT principal_id, password_hash, pepper_kid "
                "FROM kb_auth.local_get_credential(:username)"
            )
            cred_res = await session.execute(cred_stmt, {"username": norm_username})
            cred_row = cred_res.mappings().first()

        candidate_ok = cred_row is not None
        target_hash = cred_row["password_hash"] if cred_row is not None else DUMMY_HASH
        principal_id = cred_row["principal_id"] if cred_row is not None else None

        verify_hash = target_hash if (card_ok and candidate_ok) else DUMMY_HASH
        verified = await verify_password(
            verify_hash,
            password,
            pepper,
            timeout_seconds=self._timeout_seconds,
        )

        effective_ws_id = await self._resolve_workspace_id(session, workspace_id, card)
        hashed_ip = make_key(
            AUTH_LOGIN_IP, client_ip, session_hmac_key=self._session_hmac_key
        ).hex()

        if card_ok and candidate_ok and verified and principal_id is not None:
            if needs_rehash(target_hash):
                new_hash = await hash_password(
                    password, pepper, timeout_seconds=self._timeout_seconds
                )
                await session.execute(
                    text("SELECT kb_auth.local_set_password_hash(:pid, :hash)"),
                    {"pid": principal_id, "hash": new_hash},
                )

            await self._rate_limiter.reset(AUTH_LOGIN_ACCOUNT, account_key)

            # Check MFA enrollment status
            mfa_stmt = text("SELECT * FROM kb_auth.mfa_status(:p_id)")
            mfa_res = await session.execute(mfa_stmt, {"p_id": principal_id})
            mfa_row = mfa_res.mappings().first()
            has_active_totp = bool(mfa_row["has_active_totp"]) if mfa_row else False
            has_webauthn = (
                int(mfa_row["webauthn_credential_count"]) > 0
                if mfa_row and "webauthn_credential_count" in mfa_row
                else False
            )
            has_enrolled_mfa = has_active_totp or has_webauthn

            # Role check:
            admin_stmt = text(
                "SELECT 1 FROM role_bindings "
                "WHERE principal_id = :p_id AND role = 'SERVER_ADMIN' LIMIT 1"
            )
            admin_res = await session.execute(admin_stmt, {"p_id": principal_id})
            is_server_admin = admin_res.scalar_one_or_none() is not None

            require_mfa = has_enrolled_mfa or is_server_admin

            auth_card_id = card.id if card is not None else None
            issued = await self._session_service.create_after_login(
                session,
                principal_id=principal_id,
                workspace_id=effective_ws_id,
                auth_card_id=auth_card_id,
                aal_level=1,
                mfa_pending=require_mfa,
                existing_cookie=existing_cookie,
                remember_me=remember_me,
            )

            try:
                await record_activity(
                    session,
                    workspace_id=effective_ws_id,
                    actor_principal_id=principal_id,
                    event_type=ActivityEventType.LOCAL_ADMIN_LOGIN_SUCCEEDED,
                    payload={
                        "card_id": str(auth_card_id) if auth_card_id is not None else None,
                        "hashed_ip": hashed_ip,
                    },
                )
            except Exception:
                logger.debug("Failed to record login success activity", exc_info=True)

            set_log_user(format_log_actor(principal_id, mfa_pending=require_mfa))
            logger.info("Local admin login succeeded for principal %s", principal_id)
            return issued

        try:
            await record_activity(
                session,
                workspace_id=effective_ws_id,
                actor_principal_id=None,
                event_type=ActivityEventType.LOCAL_ADMIN_LOGIN_FAILED,
                payload={
                    "card_id": str(card.id) if card is not None else None,
                    "hashed_ip": hashed_ip,
                },
            )
        except Exception:
            logger.debug("Failed to record login failure activity", exc_info=True)

        logger.warning("Local admin login failed")
        raise ProblemException(
            code="INVALID_CREDENTIALS",
            status=401,
            title="Invalid Credentials",
            detail="Invalid username or password",
        )
