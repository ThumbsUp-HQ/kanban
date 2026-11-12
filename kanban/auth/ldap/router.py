# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""LDAP and StartTLS authentication API endpoints (KB-P2-07)."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Annotated, Any, NoReturn, cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request  # noqa: TC002
from starlette.responses import JSONResponse, Response

from database.models.auth import AuthProviderCard
from database.session import RLSContext
from kanban.api.problems import ProblemException
from kanban.api.timing import timing_floor
from kanban.auth.ldap.client import LdapError, LdapTlsHardClient
from kanban.auth.ldap.config import LdapCardConfig
from kanban.auth.ldap.service import LdapAuthService
from kanban.security.envelope import SealedSecret, StaticKekProvider, open_card_secret
from kanban.security.keys import load_key_material
from kanban.security.ratelimit import AUTH_LOGIN_ACCOUNT, AUTH_LOGIN_IP
from kanban.security.ratelimit.base import make_key

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from database.session import RLSSessionFactory
    from kanban.security.envelope import KekProvider
    from kanban.security.ratelimit.base import RateLimiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

ANONYMOUS_RLS_CONTEXT = RLSContext(
    principal_id=uuid.UUID(int=0),
    workspace_id=uuid.UUID(int=0),
    aal_level=1,
)


class LdapLoginRequest(BaseModel):
    """LDAP username and password login request."""

    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=1024)


async def get_auth_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide an unauthenticated database session bound to anonymous RLS context."""
    session_factory: RLSSessionFactory | None = getattr(request.app.state, "session_factory", None)
    if session_factory is not None:
        async with session_factory.session(ANONYMOUS_RLS_CONTEXT) as session:
            yield session
    else:
        msg = "No session_factory configured on application state"
        raise RuntimeError(msg)


def get_ldap_service(request: Request) -> LdapAuthService:
    """Retrieve or construct the LdapAuthService from application state."""
    service = getattr(request.app.state, "ldap_auth_service", None)
    if service is not None:
        return cast("LdapAuthService", service)

    kek_provider: KekProvider | None = getattr(request.app.state, "kek_provider", None)
    if kek_provider is None:
        key_material = getattr(request.app.state, "key_material", None)
        if key_material is None:
            key_material = load_key_material()
        kek_provider = StaticKekProvider(
            {key_material.master_kek_kid: key_material.master_kek},
            current=key_material.master_kek_kid,
        )

    service = LdapAuthService(
        kek_provider=kek_provider,
        identity_resolver=getattr(request.app.state, "identity_resolver", None),
        unix_socket_path=getattr(request.app.state, "ldap_unix_socket_path", None),
    )
    request.app.state.ldap_auth_service = service
    return service


AuthSession = Annotated[AsyncSession, Depends(get_auth_session)]
LdapServiceDep = Annotated[LdapAuthService, Depends(get_ldap_service)]


def _raise_invalid_credentials() -> NoReturn:
    """Raise uniform 401 INVALID_CREDENTIALS preventing user enumeration."""
    raise ProblemException(
        code="INVALID_CREDENTIALS",
        status=401,
        title="Authentication Failed",
        detail="Invalid credentials",
    )


async def _handle_ldap_login(
    slug: str,
    payload: LdapLoginRequest,
    request: Request,
    session: AsyncSession,
    service: LdapAuthService,
) -> Response:
    """Handle LDAP authentication with rate limiting and timing equalization."""
    clean_username = payload.username.strip()

    # Rate limiting enforcement
    rate_limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    client_ip = request.client.host if request.client else "127.0.0.1"

    key_mat = getattr(request.app.state, "key_material", None)
    session_hmac_key: bytes | None = key_mat.session_hmac_key if key_mat else None

    if rate_limiter is not None:
        ip_key = make_key(AUTH_LOGIN_IP, client_ip, session_hmac_key=session_hmac_key)
        ip_decision = await rate_limiter.hit(AUTH_LOGIN_IP, ip_key)
        if not ip_decision.allowed:
            raise ProblemException(
                code="RATE_LIMITED",
                status=429,
                title="Too Many Requests",
                detail=(
                    f"Rate limit exceeded. Retry after {ip_decision.retry_after_seconds} seconds."
                ),
            )
        acct_key = make_key(
            AUTH_LOGIN_ACCOUNT, slug, clean_username.lower(), session_hmac_key=session_hmac_key
        )
        acct_decision = await rate_limiter.hit(AUTH_LOGIN_ACCOUNT, acct_key)
        if not acct_decision.allowed:
            raise ProblemException(
                code="RATE_LIMITED",
                status=429,
                title="Too Many Requests",
                detail=(
                    f"Rate limit exceeded. Retry after {acct_decision.retry_after_seconds} seconds."
                ),
            )

    async with timing_floor(floor_ms=120.0):
        # Reject empty password prior to network I/O
        if not payload.password or not payload.password.strip():
            _raise_invalid_credentials()

        # Query card
        stmt = select(AuthProviderCard).where(AuthProviderCard.slug == slug)
        res = await session.execute(stmt)
        card = res.scalars().first()

        if card is None or not card.is_enabled or card.provider_kind != "LDAP":
            logger.debug("Card '%s' not found, disabled, or not LDAP", slug)
            _raise_invalid_credentials()

        try:
            assertion, resolved = await service.authenticate(
                session=session,
                card=card,
                username=payload.username,
                password=payload.password,
                request=request,
            )
        except (LdapError, OSError, TimeoutError, ValueError):
            logger.debug("LDAP authentication failed for card '%s'", slug, exc_info=True)
            _raise_invalid_credentials()

        response_data: dict[str, Any] = {
            "status": "authenticated",
            "card_id": str(assertion.card_id),
            "subject": assertion.subject,
            "email": assertion.email,
            "display_name": assertion.display_name,
            "groups": list(assertion.groups),
        }

        if resolved is not None:
            response_data["principal_id"] = str(resolved.principal_id)
            response_data["workspace_id"] = str(resolved.workspace_id)
            response_data["aal_level"] = resolved.aal_level

        return JSONResponse(status_code=200, content=response_data)


@router.post("/auth/ldap/{slug}/login", summary="Login with LDAP credentials")
async def ldap_login(
    slug: str,
    payload: LdapLoginRequest,
    request: Request,
    session: AuthSession,
    service: LdapServiceDep,
) -> Response:
    """Authenticate with LDAP credentials via /auth/ldap/{slug}/login."""
    return await _handle_ldap_login(slug, payload, request, session, service)


@router.post("/auth/cards/{slug}/ldap-login", summary="Login with LDAP card alias")
async def ldap_card_login_alias(
    slug: str,
    payload: LdapLoginRequest,
    request: Request,
    session: AuthSession,
    service: LdapServiceDep,
) -> Response:
    """Authenticate with LDAP credentials via alias /auth/cards/{slug}/ldap-login."""
    return await _handle_ldap_login(slug, payload, request, session, service)


@router.post("/admin/auth-cards/{card_id}/ldap-test", summary="Test LDAP card connection")
async def ldap_test_connection(
    card_id: uuid.UUID,
    request: Request,
    session: AuthSession,
) -> JSONResponse:
    """Test LDAP/StartTLS handshake, CA trust, SPKI pinning, and optional service bind."""
    stmt = select(AuthProviderCard).where(AuthProviderCard.id == card_id)
    res = await session.execute(stmt)
    card = res.scalars().first()

    if card is None or card.provider_kind != "LDAP":
        raise ProblemException(
            code="CARD_NOT_FOUND",
            status=404,
            title="Card Not Found",
            detail=f"LDAP card '{card_id}' not found",
        )

    config = LdapCardConfig(**card.public_config)
    unix_socket_path = getattr(request.app.state, "ldap_unix_socket_path", None)
    client = LdapTlsHardClient(config, unix_socket_path=unix_socket_path)

    start_time = time.perf_counter()
    try:
        await client.connect()
        # Test service bind if configured
        if config.service_bind_dn:
            kek_provider: KekProvider | None = getattr(request.app.state, "kek_provider", None)
            if (
                card.encrypted_secret_blob is not None
                and card.wrapped_dek is not None
                and kek_provider is not None
            ):
                sealed = SealedSecret(
                    encrypted_secret_blob=card.encrypted_secret_blob,
                    wrapped_dek=card.wrapped_dek,
                    dek_kid=card.dek_kid,
                )
                secret_buf = open_card_secret(card.id, "LDAP", sealed, kek_provider)
                try:
                    secret_data = json.loads(secret_buf.decode("utf-8"))
                    pwd_str = str(secret_data.get("bind_dn_password", ""))
                    await client.bind(config.service_bind_dn, pwd_str.encode("utf-8"))
                finally:
                    for i in range(len(secret_buf)):
                        secret_buf[i] = 0

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "transport_mode": config.transport_mode,
                "spki_sha256": client.verified_spki_sha256,
                "latency_ms": round(elapsed_ms, 2),
            },
        )
    except (LdapError, OSError, TimeoutError, ValueError) as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "latency_ms": round(elapsed_ms, 2),
            },
        )
    finally:
        await client.unbind()
