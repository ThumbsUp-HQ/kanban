# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""OAuth 2.1 authorization server endpoints, token exchange & grant deauth (KB-P4-02b)."""

from __future__ import annotations

import contextlib
import logging
import os
import secrets
import time
import urllib.parse
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any, Final, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from database.models.oauth import (
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthGrant,
    OAuthRefreshToken,
    OAuthRevokedJti,
)
from database.models.projects import Project
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException, not_found
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.oauth.device import (
    activate_device_code,
    create_device_authorization,
    get_device_code_info,
    poll_device_code,
)
from kanban.oauth.jwt import (
    ACCESS_TOKEN_TTL_SECONDS,
    get_jwks,
    mint_access_token,
    verify_access_token,
)
from kanban.oauth.server import (
    CODE_TTL_SECONDS,
    REFRESH_TOKEN_TTL_DAYS,
    SURFACE_SCOPES,
    OAuth2Error,
    check_registration_rate_limit,
    hash_token,
    parse_surface_from_resource,
    render_consent_screen,
    revoke_grant_family,
    validate_redirect_uri,
    validate_registration_redirect_uris,
    verify_pkce_s256,
)


def _check_no_token_in_query(request: Request) -> None:
    """Verify that access_token is not present in URL query parameters."""
    if "access_token" in request.query_params:
        err = "invalid_request"
        desc = "access_token parameter in query string is strictly forbidden"
        raise OAuth2Error(err, desc, 400)


oauth_root_router = APIRouter(
    tags=["oauth-server"],
    dependencies=[Depends(_check_no_token_in_query)],
)
oauth_v1_router = APIRouter(
    tags=["oauth-grants"],
    dependencies=[Depends(_check_no_token_in_query)],
)

__all__ = [
    "OAuth2Error",
    "oauth_root_router",
    "oauth_v1_router",
]

_REQUIRED_AAL_LEVEL: Final[int] = 2
MIN_CODE_CHALLENGE_LEN: Final[int] = 43
MAX_CODE_CHALLENGE_LEN: Final[int] = 128
MAX_STATE_LEN: Final[int] = 512
_logger: Final[logging.Logger] = logging.getLogger(__name__)

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield database session for machine/unauthenticated OAuth endpoints."""
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory is not configured on app.state.session_factory"
        raise RuntimeError(msg)
    async with session_factory.sessionmaker() as session:
        session.info["rls_bound"] = True

        @event.listens_for(session.sync_session, "after_begin")
        def _keep_rls_bound(sess: Any, *args: Any) -> None:  # noqa: ANN401
            del args
            sess.info["rls_bound"] = True

        yield session


UnauthSession = Annotated[AsyncSession, Depends(get_db_session)]


async def _parse_request_payload(request: Request) -> dict[str, Any]:
    """Parse form data or JSON body without external multipart parser."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        with contextlib.suppress(Exception):
            body = await request.json()
            return dict(body) if isinstance(body, dict) else {}
        return {}

    body_bytes = await request.body()
    if not body_bytes:
        return {}

    body_str = body_bytes.decode("utf-8", errors="replace")
    parsed = urllib.parse.parse_qs(body_str, keep_blank_values=True)
    res: dict[str, Any] = {}
    for k, v in parsed.items():
        res[k] = v[0] if len(v) == 1 else v
    if "scopes" in parsed:
        res["scopes"] = parsed["scopes"]
    return res


async def _require_admin_aal2(caller: PrincipalContext, session: AsyncSession) -> None:
    """Enforce AAL2 authentication and workspace/server admin role."""
    if caller.aal_level < _REQUIRED_AAL_LEVEL:
        raise ProblemException(
            code="AAL2_REQUIRED",
            status=403,
            title="AAL2 Required",
            detail="Managing OAuth credentials requires AAL2 authentication.",
        )

    stmt = text("SELECT app_principal_has_role(NULL, CAST(:roles AS text[]))")
    roles = ["SERVER_ADMIN", "WORKSPACE_ADMIN"]
    is_admin = (await session.execute(stmt, {"roles": roles})).scalar_one()
    if not is_admin:
        raise ProblemException(
            code="FORBIDDEN",
            status=403,
            title="Forbidden",
            detail="Caller lacks required workspace admin role.",
        )


# =========================================================================
# Schemas
# =========================================================================


class OAuthClientRegisterRequest(BaseModel):
    """Payload for RFC 7591 dynamic client registration."""

    model_config = ConfigDict(extra="forbid")

    client_name: str = Field(min_length=1, max_length=200)
    redirect_uris: list[str] = Field(min_length=1)
    client_type: Literal["public"] = "public"


class OAuthClientRegisterResponse(BaseModel):
    """Registered client details returned on HTTP 201."""

    model_config = ConfigDict(extra="ignore")

    client_id: str
    client_name: str
    client_type: str = "public"
    redirect_uris: list[str]
    status: str


class OAuthGrantResponse(BaseModel):
    """Details of an active or revoked OAuth grant."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    client_id: str
    client_name: str | None = None
    surface: str
    scopes: list[str]
    allowed_projects: list[uuid.UUID] | None = None
    created_at: datetime
    revoked_at: datetime | None = None


class OAuthClientPatchRequest(BaseModel):
    """Admin patch request for client approval."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "disabled"]


# =========================================================================
# RFC 8414 & RFC 7591 Root Server Endpoints
# =========================================================================


@oauth_root_router.get(
    "/.well-known/oauth-authorization-server",
    summary="OAuth 2.1 Authorization Server Metadata (RFC 8414)",
)
async def oauth_as_metadata(request: Request) -> JSONResponse:
    """Return RFC 8414 authorization server discovery metadata."""
    _check_no_token_in_query(request)
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(
        {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/oauth/authorize",
            "token_endpoint": f"{base_url}/oauth/token",
            "revocation_endpoint": f"{base_url}/oauth/revoke",
            "registration_endpoint": f"{base_url}/oauth/register",
            "device_authorization_endpoint": f"{base_url}/oauth/device/authorize",
            "jwks_uri": f"{base_url}/oauth/jwks.json",
            "code_challenge_methods_supported": ["S256"],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token",
                "urn:ietf:params:oauth:grant-type:device_code",
            ],
            "response_types_supported": ["code"],
            "token_endpoint_auth_methods_supported": ["none", "private_key_jwt"],
        },
        headers={"Cache-Control": "public, max-age=3600"},
    )


@oauth_root_router.get(
    "/oauth/jwks.json",
    summary="OAuth Public Key Set (JWKS)",
)
async def oauth_jwks(request: Request) -> JSONResponse:
    """Return RFC 7517 public JWKS for verifying ES256 access tokens."""
    _check_no_token_in_query(request)
    return JSONResponse(
        get_jwks(),
        headers={"Cache-Control": "public, max-age=3600"},
    )


@oauth_root_router.post(
    "/oauth/register",
    status_code=status.HTTP_201_CREATED,
    summary="Dynamic Client Registration (RFC 7591)",
)
async def oauth_register_client(
    request: Request,
    payload: OAuthClientRegisterRequest,
    session: UnauthSession,
) -> JSONResponse:
    """Register public OAuth 2.1 client with strict URI and rate limit validation."""
    _check_no_token_in_query(request)

    # 1. IP rate limiting (100/hr)
    client_ip = request.client.host if request.client else "127.0.0.1"
    check_registration_rate_limit(client_ip)

    # 2. Redirect URI validation
    validate_registration_redirect_uris(payload.redirect_uris)

    # 3. Check workspace policy for client approval
    require_approval = (
        os.environ.get("KANBAN_REQUIRE_ADMIN_OAUTH_CLIENT_APPROVAL", "").lower() in ("true", "1")
        or request.headers.get("x-require-admin-oauth-client-approval", "").lower() == "true"
    )
    initial_status = "pending_admin_approval" if require_approval else "active"

    client_id = f"client_{secrets.token_urlsafe(16)}"
    client_record = OAuthClient(
        client_id=client_id,
        client_name=payload.client_name,
        client_type="public",
        redirect_uris=payload.redirect_uris,
        status=initial_status,
        workspace_id=None,
        created_by_id=None,
    )
    session.add(client_record)
    await session.commit()

    return JSONResponse(
        {
            "client_id": client_record.client_id,
            "client_name": client_record.client_name,
            "client_type": client_record.client_type,
            "redirect_uris": client_record.redirect_uris,
            "status": client_record.status,
        },
        status_code=201,
    )


@oauth_root_router.post(
    "/oauth/device/authorize",
    summary="OAuth 2.0 Device Authorization (RFC 8628)",
)
async def oauth_device_authorize(
    request: Request,
    session: UnauthSession,
) -> JSONResponse:
    """Initiate RFC 8628 Device Authorization Flow for headless clients."""
    form = await _parse_request_payload(request)
    client_id = str(form.get("client_id", ""))
    resource = str(form.get("resource", ""))
    scope = form.get("scope")
    scope_str = str(scope) if scope is not None else None

    if not client_id or not resource:
        err = "invalid_request"
        desc = "client_id and resource required"
        raise OAuth2Error(err, desc, 400)

    base_url = str(request.base_url).rstrip("/")
    res = await create_device_authorization(
        session,
        client_id_str=client_id,
        resource=resource,
        scope_str=scope_str,
        base_url=base_url,
    )
    return JSONResponse(
        {
            "device_code": res.device_code,
            "user_code": res.user_code,
            "verification_uri": res.verification_uri,
            "verification_uri_complete": res.verification_uri_complete,
            "expires_in": res.expires_in,
            "interval": res.interval,
        }
    )


# =========================================================================
# Interactive Authorization & Consent Flow
# =========================================================================


@oauth_root_router.get(
    "/oauth/authorize",
    summary="OAuth 2.1 Interactive Authorization / Consent Screen",
)
async def oauth_authorize(  # noqa: C901, PLR0913, PLR0917
    request: Request,
    caller: Caller,
    session: Session,
    response_type: Annotated[str, Query()],
    client_id: Annotated[str, Query()],
    redirect_uri: Annotated[str, Query()],
    code_challenge: Annotated[str, Query()],
    code_challenge_method: Annotated[str, Query()],
    state: Annotated[str, Query()],
    resource: Annotated[str, Query()],
    scope: Annotated[str, Query()] = "",
) -> Response:
    """Render interactive consent screen for authorization code grant with PKCE S256."""
    _check_no_token_in_query(request)

    # 1. Validate response_type
    if response_type != "code":
        err = "unsupported_response_type"
        desc = "response_type must be 'code'"
        raise OAuth2Error(err, desc, 400)

    # 2. Validate PKCE code_challenge_method (plain or absent -> invalid_request)
    if code_challenge_method != "S256":
        err = "invalid_request"
        desc = "code_challenge_method must be S256"
        raise OAuth2Error(err, desc, 400)
    if not (MIN_CODE_CHALLENGE_LEN <= len(code_challenge) <= MAX_CODE_CHALLENGE_LEN):
        err = "invalid_request"
        desc = "code_challenge must be between 43 and 128 characters"
        raise OAuth2Error(err, desc, 400)

    # 3. Validate state parameter
    if not state or len(state) > MAX_STATE_LEN:
        err = "invalid_request"
        desc = "state parameter required and must be <= 512 chars"
        raise OAuth2Error(err, desc, 400)

    # 4. Lookup client
    stmt_client = select(OAuthClient).where(OAuthClient.client_id == client_id)
    client_record = (await session.execute(stmt_client)).scalar_one_or_none()
    if client_record is None:
        err = "invalid_client"
        desc = f"Unknown client_id {client_id!r}"
        raise OAuth2Error(err, desc, 400)

    # 5. Validate redirect_uri exact string match
    if not validate_redirect_uri(redirect_uri, client_record.redirect_uris):
        err = "invalid_request"
        desc = "redirect_uri does not match registered URIs"
        raise OAuth2Error(err, desc, 400)

    # 6. Check client approval status
    if client_record.status == "pending_admin_approval":
        params = {
            "error": "unauthorized_client",
            "error_description": "client_pending_admin_approval",
            "state": state,
        }
        return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=302)
    if client_record.status == "disabled":
        params = {
            "error": "unauthorized_client",
            "error_description": "client_disabled",
            "state": state,
        }
        return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=302)

    # 7. Validate resource & surface
    base_url = str(request.base_url).rstrip("/")
    surface = parse_surface_from_resource(resource, base_url)

    # 8. Admin surface requires AAL2
    if surface == "admin" and caller.aal_level < _REQUIRED_AAL_LEVEL:
        params = {
            "error": "access_denied",
            "error_description": "aal2_required",
            "state": state,
        }
        return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=302)

    # 9. Scopes validation
    allowed_surface_scopes = SURFACE_SCOPES[surface]
    requested_scopes = scope.split() if scope else list(allowed_surface_scopes)
    for sc in requested_scopes:
        if sc not in allowed_surface_scopes:
            params = {
                "error": "invalid_scope",
                "error_description": f"Scope {sc} invalid for {surface}",
                "state": state,
            }
            return RedirectResponse(f"{redirect_uri}?{urlencode(params)}")

    # 10. Load available projects for project scope selector
    stmt_projects = select(Project.id, Project.name).where(
        Project.workspace_id == caller.workspace_id
    )
    projects_rows = (await session.execute(stmt_projects)).all()
    available_projects = [(row[0], row[1]) for row in projects_rows]

    csrf_token = secrets.token_urlsafe(32)

    return render_consent_screen(
        client_name=client_record.client_name,
        redirect_uri=redirect_uri,
        surface=surface,
        requested_scopes=requested_scopes,
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        resource=resource,
        client_id=client_id,
        csrf_token=csrf_token,
        available_projects=available_projects,
    )


@oauth_root_router.post(
    "/oauth/authorize/decision",
    summary="Process OAuth 2.1 Consent Decision",
)
async def oauth_authorize_decision(
    request: Request,
    caller: Caller,
    session: Session,
) -> RedirectResponse:
    """Process user consent decision, minting authorization code or returning access_denied."""
    _check_no_token_in_query(request)
    form = await _parse_request_payload(request)
    client_id = str(form.get("client_id", ""))
    redirect_uri = str(form.get("redirect_uri", ""))
    resource = str(form.get("resource", ""))
    code_challenge = str(form.get("code_challenge", ""))
    code_challenge_method = str(form.get("code_challenge_method", ""))
    state = str(form.get("state", ""))
    action = str(form.get("action", ""))
    scopes_val = form.get("scopes")
    if isinstance(scopes_val, list):
        selected_scopes = [str(s) for s in scopes_val]
    elif isinstance(scopes_val, str) and scopes_val:
        selected_scopes = [scopes_val]
    else:
        selected_scopes = []
    allowed_project_id = str(form.get("allowed_project_id", "__ALL__"))

    # 1. Lookup client
    stmt_client = select(OAuthClient).where(OAuthClient.client_id == client_id)
    client_record = (await session.execute(stmt_client)).scalar_one_or_none()
    if client_record is None or not validate_redirect_uri(
        redirect_uri, client_record.redirect_uris
    ):
        err = "invalid_request"
        desc = "Invalid client or redirect URI"
        raise OAuth2Error(err, desc, 400)

    # 2. Handle User Deny
    if action.lower() != "approve":
        params = {
            "error": "access_denied",
            "error_description": "User denied consent",
            "state": state,
        }
        return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=302)

    # 3. Surface & scopes validation
    base_url = str(request.base_url).rstrip("/")
    surface = parse_surface_from_resource(resource, base_url)
    allowed_surface_scopes = SURFACE_SCOPES[surface]
    approved_scopes = [s for s in selected_scopes if s in allowed_surface_scopes]
    if not approved_scopes:
        approved_scopes = [allowed_surface_scopes[0]]

    # 4. Project narrowing
    allowed_projects: list[uuid.UUID] | None = None
    if allowed_project_id and allowed_project_id != "__ALL__":
        with contextlib.suppress(ValueError):
            allowed_projects = [uuid.UUID(allowed_project_id)]

    # 5. Create or lookup OAuthGrant
    grant = OAuthGrant(
        workspace_id=caller.workspace_id,
        principal_id=caller.principal_id,
        client_id=client_record.id,
        surface=surface,
        scopes=approved_scopes,
        allowed_projects=allowed_projects,
    )
    session.add(grant)
    await session.flush()

    # 6. Generate single-use authorization code (256-bit URL-safe)
    code = secrets.token_urlsafe(32)
    code_sha = hash_token(code)
    now = datetime.now(UTC)

    auth_code_record = OAuthAuthorizationCode(
        code_sha256=code_sha,
        grant_id=grant.id,
        client_id=client_record.id,
        principal_id=caller.principal_id,
        workspace_id=caller.workspace_id,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        resource=resource,
        redirect_uri=redirect_uri,
        surface=surface,
        scopes=approved_scopes,
        allowed_projects=allowed_projects,
        created_at=now,
        expires_at=now + timedelta(seconds=CODE_TTL_SECONDS),
        consumed_at=None,
    )
    session.add(auth_code_record)
    await session.commit()

    params = {"code": code, "state": state}
    return RedirectResponse(f"{redirect_uri}?{urlencode(params)}", status_code=302)


# =========================================================================
# Token Exchange & RFC 7009 Revocation
# =========================================================================


@oauth_root_router.post(
    "/oauth/token",
    summary="OAuth 2.1 Token Exchange (Authorization Code & Refresh Token)",
)
async def oauth_token_endpoint(  # noqa: C901, PLR0912, PLR0915
    request: Request,
    session: UnauthSession,
) -> JSONResponse:
    """Exchange authorization code or refresh token for ES256 JWT access token."""
    _check_no_token_in_query(request)

    form = await _parse_request_payload(request)
    eff_grant_type = str(form.get("grant_type", ""))
    eff_client_id = str(form.get("client_id", ""))
    eff_code_val = form.get("code")
    eff_code = str(eff_code_val) if eff_code_val is not None else None
    eff_cv_val = form.get("code_verifier")
    eff_code_verifier = str(eff_cv_val) if eff_cv_val is not None else None
    eff_uri_val = form.get("redirect_uri")
    eff_redirect_uri = str(eff_uri_val) if eff_uri_val is not None else None
    eff_res_val = form.get("resource")
    eff_resource = str(eff_res_val) if eff_res_val is not None else None
    eff_rt_val = form.get("refresh_token")
    eff_refresh_token = str(eff_rt_val) if eff_rt_val is not None else None

    base_url = str(request.base_url).rstrip("/")
    now = datetime.now(UTC)

    # 1. Authorization Code Grant
    if eff_grant_type == "authorization_code":
        if not eff_code or not eff_code_verifier or not eff_redirect_uri:
            err = "invalid_request"
            desc = "code, code_verifier, and redirect_uri required"
            raise OAuth2Error(err, desc, 400)

        code_sha = hash_token(eff_code)
        stmt = select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code_sha256 == code_sha)
        code_record = (await session.execute(stmt)).scalar_one_or_none()

        if code_record is None:
            err = "invalid_grant"
            desc = "Invalid authorization code"
            raise OAuth2Error(err, desc, 400)

        # Expiry check
        if code_record.expires_at <= now:
            err = "invalid_grant"
            desc = "Authorization code expired"
            raise OAuth2Error(err, desc, 400)

        # Code reuse check (Action 2: second redemption revokes entire oauth_grants family)
        if code_record.consumed_at is not None:
            _logger.warning("OAuth authorization code reuse detected! Revoking grant family.")
            if code_record.grant_id:
                await revoke_grant_family(session, code_record.grant_id, code_record.workspace_id)
                await session.commit()
            err = "invalid_grant"
            desc = "Authorization code already consumed; entire grant family revoked"
            raise OAuth2Error(err, desc, 400)

        # Validate redirect_uri exact match
        if code_record.redirect_uri != eff_redirect_uri:
            err = "invalid_grant"
            desc = "redirect_uri mismatch"
            raise OAuth2Error(err, desc, 400)

        # Validate resource match if provided
        if eff_resource and code_record.resource != eff_resource:
            err = "invalid_grant"
            desc = "resource mismatch"
            raise OAuth2Error(err, desc, 400)

        # Validate PKCE S256
        if not verify_pkce_s256(eff_code_verifier, code_record.code_challenge):
            err = "invalid_grant"
            desc = "PKCE code_verifier validation failed"
            raise OAuth2Error(err, desc, 400)

        # Mark code consumed
        code_record.consumed_at = now

        # Mint Access Token JWT
        access_token = mint_access_token(
            issuer=base_url,
            subject=code_record.principal_id,
            audience=code_record.resource,
            surface=code_record.surface,
            scopes=code_record.scopes,
            client_id=eff_client_id,
            grant_id=code_record.grant_id or uuid.uuid4(),
            workspace_id=code_record.workspace_id,
            allowed_projects=code_record.allowed_projects,
            ttl_seconds=ACCESS_TOKEN_TTL_SECONDS,
        )

        # Generate Refresh Token
        rt_raw = secrets.token_urlsafe(32)
        rt_sha = hash_token(rt_raw)
        rt_record = OAuthRefreshToken(
            token_sha256=rt_sha,
            grant_id=code_record.grant_id or uuid.uuid4(),
            workspace_id=code_record.workspace_id,
            client_id=code_record.client_id,
            principal_id=code_record.principal_id,
            created_at=now,
            expires_at=now + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
            revoked_at=None,
        )
        session.add(rt_record)
        await session.commit()

        return JSONResponse(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": ACCESS_TOKEN_TTL_SECONDS,
                "refresh_token": rt_raw,
                "scope": " ".join(code_record.scopes),
            },
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    # 2. Refresh Token Grant (single-use rotation)
    if eff_grant_type == "refresh_token":
        if not eff_refresh_token:
            err = "invalid_request"
            desc = "refresh_token parameter required"
            raise OAuth2Error(err, desc, 400)

        rt_sha = hash_token(eff_refresh_token)
        stmt_rt = select(OAuthRefreshToken).where(OAuthRefreshToken.token_sha256 == rt_sha)
        existing_rt = (await session.execute(stmt_rt)).scalar_one_or_none()

        if existing_rt is None or existing_rt.expires_at <= now:
            err = "invalid_grant"
            desc = "Invalid or expired refresh token"
            raise OAuth2Error(err, desc, 400)

        # Refresh token reuse detection
        if existing_rt.revoked_at is not None:
            _logger.warning("OAuth refresh token reuse detected! Revoking grant family.")
            await revoke_grant_family(session, existing_rt.grant_id, existing_rt.workspace_id)
            await session.commit()
            err = "invalid_grant"
            desc = "Refresh token reuse detected; entire grant family revoked"
            raise OAuth2Error(err, desc, 400)

        # Rotate: revoke current refresh token
        existing_rt.revoked_at = now

        # Fetch parent grant
        stmt_grant = select(OAuthGrant).where(OAuthGrant.id == existing_rt.grant_id)
        grant = (await session.execute(stmt_grant)).scalar_one_or_none()
        if grant is None or grant.revoked_at is not None:
            await session.commit()
            err = "invalid_grant"
            desc = "Parent grant is revoked"
            raise OAuth2Error(err, desc, 400)

        surface_url = f"{base_url}/mcp/{grant.surface}"

        # Mint new access token
        new_access_token = mint_access_token(
            issuer=base_url,
            subject=grant.principal_id,
            audience=surface_url,
            surface=grant.surface,
            scopes=grant.scopes,
            client_id=eff_client_id,
            grant_id=grant.id,
            workspace_id=grant.workspace_id,
            allowed_projects=grant.allowed_projects,
            ttl_seconds=ACCESS_TOKEN_TTL_SECONDS,
        )

        # Mint rotated refresh token
        new_rt_raw = secrets.token_urlsafe(32)
        new_rt_sha = hash_token(new_rt_raw)
        new_rt_record = OAuthRefreshToken(
            token_sha256=new_rt_sha,
            grant_id=grant.id,
            workspace_id=grant.workspace_id,
            client_id=existing_rt.client_id,
            principal_id=grant.principal_id,
            created_at=now,
            expires_at=now + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
            revoked_at=None,
        )
        session.add(new_rt_record)
        await session.commit()

        return JSONResponse(
            {
                "access_token": new_access_token,
                "token_type": "Bearer",
                "expires_in": ACCESS_TOKEN_TTL_SECONDS,
                "refresh_token": new_rt_raw,
                "scope": " ".join(grant.scopes),
            },
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    # 3. Device Code Grant (RFC 8628)
    if eff_grant_type == "urn:ietf:params:oauth:grant-type:device_code":
        eff_dev_val = form.get("device_code")
        eff_dev_code = str(eff_dev_val) if eff_dev_val is not None else ""
        if not eff_dev_code:
            err = "invalid_request"
            desc = "device_code parameter required"
            raise OAuth2Error(err, desc, 400)

        grant = await poll_device_code(
            session,
            device_code=eff_dev_code,
            client_id_str=eff_client_id,
        )

        surface_url = f"{base_url}/mcp/{grant.surface}"

        access_token = mint_access_token(
            issuer=base_url,
            subject=grant.principal_id,
            audience=surface_url,
            surface=grant.surface,
            scopes=grant.scopes,
            client_id=eff_client_id,
            grant_id=grant.id,
            workspace_id=grant.workspace_id,
            allowed_projects=grant.allowed_projects,
            ttl_seconds=ACCESS_TOKEN_TTL_SECONDS,
        )

        rt_raw = secrets.token_urlsafe(32)
        rt_sha = hash_token(rt_raw)
        rt_record = OAuthRefreshToken(
            token_sha256=rt_sha,
            grant_id=grant.id,
            workspace_id=grant.workspace_id,
            client_id=grant.client_id,
            principal_id=grant.principal_id,
            created_at=now,
            expires_at=now + timedelta(days=REFRESH_TOKEN_TTL_DAYS),
            revoked_at=None,
        )
        session.add(rt_record)
        await session.commit()

        return JSONResponse(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": ACCESS_TOKEN_TTL_SECONDS,
                "refresh_token": rt_raw,
                "scope": " ".join(grant.scopes),
            },
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    err = "unsupported_grant_type"
    desc = f"Unsupported grant_type {eff_grant_type!r}"
    raise OAuth2Error(err, desc, 400)


@oauth_root_router.post(
    "/oauth/revoke",
    summary="OAuth Token Revocation (RFC 7009)",
)
async def oauth_revoke_endpoint(
    request: Request,
    session: UnauthSession,
) -> JSONResponse:
    """Revoke an access token or refresh token per RFC 7009."""
    _check_no_token_in_query(request)

    form = await _parse_request_payload(request)
    eff_token = str(form.get("token", ""))

    if not eff_token:
        return JSONResponse({}, status_code=200)

    now = datetime.now(UTC)

    # 1. Access token JWT revocation
    if eff_token.startswith("eyJ"):
        with contextlib.suppress(Exception):
            claims = verify_access_token(eff_token, now=0)
            jti_str = claims.get("jti")
            grant_id_str = claims.get("grant_id")
            ws_id_str = claims.get("ws")
            exp_ts = float(claims.get("exp", time.time() + 900))

            if jti_str and grant_id_str and ws_id_str:
                jti_uuid = uuid.UUID(jti_str)
                grant_uuid = uuid.UUID(grant_id_str)
                ws_uuid = uuid.UUID(ws_id_str)

                revoked_jti = OAuthRevokedJti(
                    jti=jti_uuid,
                    grant_id=grant_uuid,
                    workspace_id=ws_uuid,
                    expires_at=datetime.fromtimestamp(exp_ts, tz=UTC),
                    revoked_at=now,
                )
                session.add(revoked_jti)
                await revoke_grant_family(session, grant_uuid, ws_uuid)
                await session.commit()
        return JSONResponse({}, status_code=200)

    # 2. Refresh token revocation
    rt_sha = hash_token(eff_token)
    stmt_rt = select(OAuthRefreshToken).where(OAuthRefreshToken.token_sha256 == rt_sha)
    rt_record = (await session.execute(stmt_rt)).scalar_one_or_none()
    if rt_record:
        await revoke_grant_family(session, rt_record.grant_id, rt_record.workspace_id)
        await session.commit()

    return JSONResponse({}, status_code=200)


# =========================================================================
# Self-Service & Admin Grant Management Endpoints (/api/v1/...)
# =========================================================================


@oauth_v1_router.get(
    "/auth/oauth-grants",
    response_model=list[OAuthGrantResponse],
    summary="List caller's connected OAuth grants",
)
async def list_user_oauth_grants(
    caller: Caller,
    session: Session,
) -> list[OAuthGrantResponse]:
    """List all active and recent OAuth grants for the authenticated principal."""
    stmt = (
        select(OAuthGrant, OAuthClient.client_id, OAuthClient.client_name)
        .join(OAuthClient, OAuthGrant.client_id == OAuthClient.id)
        .where(
            OAuthGrant.principal_id == caller.principal_id,
            OAuthGrant.workspace_id == caller.workspace_id,
            OAuthGrant.revoked_at.is_(None),
        )
        .order_by(OAuthGrant.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        OAuthGrantResponse(
            id=grant.id,
            client_id=client_id,
            client_name=client_name,
            surface=grant.surface,
            scopes=grant.scopes,
            allowed_projects=grant.allowed_projects,
            created_at=grant.created_at,
            revoked_at=grant.revoked_at,
        )
        for grant, client_id, client_name in rows
    ]


@oauth_v1_router.delete(
    "/auth/oauth-grants/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Self-service deauthorize connected OAuth grant",
)
async def revoke_user_oauth_grant(
    grant_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> Response:
    """Revoke caller's own OAuth grant and invalidate all active tokens."""
    stmt = select(OAuthGrant).where(
        OAuthGrant.id == grant_id,
        OAuthGrant.principal_id == caller.principal_id,
        OAuthGrant.workspace_id == caller.workspace_id,
    )
    grant = (await session.execute(stmt)).scalar_one_or_none()
    if grant is None:
        not_found()

    await revoke_grant_family(
        session,
        grant.id,
        caller.workspace_id,
        actor_principal_id=caller.principal_id,
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@oauth_v1_router.delete(
    "/admin/oauth-grants/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Admin revoke connected OAuth grant (AAL2)",
    dependencies=[Depends(require_admin_aal2)],
)
async def admin_revoke_oauth_grant(
    grant_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> Response:
    """Workspace Admin revocation of any workspace OAuth grant requiring AAL2."""
    await _require_admin_aal2(caller, session)

    stmt = select(OAuthGrant).where(
        OAuthGrant.id == grant_id,
        OAuthGrant.workspace_id == caller.workspace_id,
    )
    grant = (await session.execute(stmt)).scalar_one_or_none()
    if grant is None:
        not_found()

    await revoke_grant_family(
        session,
        grant.id,
        caller.workspace_id,
        actor_principal_id=caller.principal_id,
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@oauth_v1_router.patch(
    "/admin/oauth-clients/{client_id}",
    summary="Admin approve or disable OAuth client (AAL2)",
    dependencies=[Depends(require_admin_aal2)],
)
async def admin_patch_oauth_client(
    client_id: str,
    payload: OAuthClientPatchRequest,
    caller: Caller,
    session: Session,
) -> JSONResponse:
    """Workspace Admin approval for dynamically registered clients requiring AAL2."""
    await _require_admin_aal2(caller, session)

    stmt = select(OAuthClient).where(OAuthClient.client_id == client_id)
    client_record = (await session.execute(stmt)).scalar_one_or_none()
    if client_record is None:
        not_found()

    client_record.status = payload.status
    client_record.updated_at = datetime.now(UTC)
    await session.commit()

    return JSONResponse(
        {
            "client_id": client_record.client_id,
            "client_name": client_record.client_name,
            "status": client_record.status,
            "updated_at": client_record.updated_at.isoformat(),
        }
    )


# =========================================================================
# RFC 8628 Device Flow Activation & Personal MCP Keys
# =========================================================================


class DeviceActivateRequest(BaseModel):
    """Payload for RFC 8628 OAuth 2.0 device authorization activation."""

    user_code: str = Field(
        description="Normalized 8-character device verification user code (e.g. WDFG-BTRJ)"
    )
    approved: bool = Field(
        description="Whether the authenticating user approves or denies authorization"
    )
    scopes: list[str] | None = Field(
        default=None, description="Optional narrowed scopes granted to the device session"
    )
    allowed_projects: list[uuid.UUID] | None = Field(
        default=None, description="Optional list of project UUIDs granted to the device session"
    )


class PersonalMcpKeyMintRequest(BaseModel):
    """Payload for minting a personal Model Context Protocol (MCP) API access key."""

    surface: Literal["agent", "docs", "admin"] = Field(
        description="Target MCP surface tier: agent, docs, or admin"
    )
    scopes: list[str] = Field(description="List of capability scope tokens granted to this key")
    expires_in_days: int | None = Field(
        default=30, ge=1, le=365, description="Token validity duration in days"
    )
    unlimited: bool = Field(
        default=False, description="Whether to request an unlimited lifetime key"
    )
    confirm_unlimited: bool = Field(
        default=False, description="Explicit confirmation for minting an unlimited lifetime key"
    )
    disabled_tools: list[str] = Field(
        default_factory=list, description="Tool names explicitly narrowed and disabled on this key"
    )


@oauth_v1_router.get(
    "/oauth/device/info",
    summary="Get pending device authorization info",
)
async def get_device_info(
    request: Request,
    session: Session,
    user_code: Annotated[str, Query(description="User code in format XXXX-XXXX")],
) -> JSONResponse:
    """Retrieve metadata for a pending device authorization request."""
    client_ip = request.client.host if request.client else "unknown"
    info = await get_device_code_info(session, user_code, rate_limit_key=client_ip)
    return JSONResponse(
        {
            "user_code": info.user_code,
            "client_name": info.client_name,
            "client_id": info.client_id,
            "resource": info.resource,
            "surface": info.surface,
            "requested_scopes": info.requested_scopes,
            "allowed_projects": (
                [str(p) for p in info.allowed_projects] if info.allowed_projects else None
            ),
            "expires_at": info.expires_at.isoformat(),
        }
    )


@oauth_v1_router.post(
    "/oauth/device/activate",
    summary="Activate or deny RFC 8628 device code",
)
async def activate_device(
    request: Request,
    body: DeviceActivateRequest,
    caller: Caller,
    session: Session,
) -> JSONResponse:
    """Approve or deny a device authorization request with optional scope and project narrowing."""
    client_ip = request.client.host if request.client else "unknown"
    is_aal2 = caller.aal_level == _REQUIRED_AAL_LEVEL
    grant = await activate_device_code(
        session,
        raw_user_code=body.user_code,
        principal_id=caller.principal_id,
        workspace_id=caller.workspace_id,
        approved=body.approved,
        allowed_scopes=body.scopes,
        allowed_projects=body.allowed_projects,
        rate_limit_key=client_ip,
        is_aal2=is_aal2,
    )
    return JSONResponse({"status": "approved" if grant is not None else "denied"})
