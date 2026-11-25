# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""OAuth 2.1 authorization server endpoints, token exchange & grant deauth (KB-P4-02b)."""

from __future__ import annotations

import base64
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
from sqlalchemy import ColumnElement, delete, event, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from database.models.oauth import (
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthDeviceCode,
    OAuthGrant,
    OAuthRefreshToken,
    OAuthRevokedJti,
)
from database.models.projects import Project
from kanban.api.deps import DenyAllResolver, PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException, not_found
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.auth.sessions.csrf import verify_same_origin_request
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
    generate_client_secret,
    generate_consent_csrf_token,
    hash_client_secret,
    hash_token,
    mask_client_secret_prefix,
    parse_resource_target,
    parse_surface_from_resource,
    render_consent_screen,
    resolve_public_base_url,
    revoke_grant_family,
    validate_redirect_uri,
    validate_registration_redirect_uris,
    verify_client_secret,
    verify_consent_csrf_token,
    verify_pkce_s256,
)
from kanban.security.keys import KeyMaterialError, load_key_material
from kanban.services.activity import ActivityEventType, record_activity


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

from kanban.api.v1.admin.workload_identities import (  # noqa: E402
    router as admin_workload_identities_router,
)

oauth_v1_router.include_router(admin_workload_identities_router)

__all__ = [
    "OAuth2Error",
    "oauth_root_router",
    "oauth_v1_router",
]

_REQUIRED_AAL_LEVEL: Final[int] = 2
MIN_CODE_CHALLENGE_LEN: Final[int] = 43
MAX_CODE_CHALLENGE_LEN: Final[int] = 128
MAX_STATE_LEN: Final[int] = 4096
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

    model_config = ConfigDict(extra="ignore")

    client_name: str | None = Field(default=None, max_length=200)
    redirect_uris: list[str] = Field(min_length=1)
    client_type: Literal["public", "confidential"] = "public"
    grant_types: list[str] | None = None
    response_types: list[str] | None = None
    token_endpoint_auth_method: str | None = None
    scope: str | None = None
    client_uri: str | None = None
    logo_uri: str | None = None
    contacts: list[str] | None = None
    tos_uri: str | None = None
    policy_uri: str | None = None
    jwks_uri: str | None = None
    software_id: str | None = Field(default=None, max_length=200)
    software_version: str | None = Field(default=None, max_length=100)


class OAuthClientRegisterResponse(BaseModel):
    """Registered client details returned on HTTP 201."""

    model_config = ConfigDict(extra="ignore")

    client_id: str
    client_name: str
    client_type: str = "public"
    redirect_uris: list[str]
    status: str
    grant_types: list[str] | None = None
    response_types: list[str] | None = None
    token_endpoint_auth_method: str = "none"  # noqa: S105
    client_secret: str | None = None
    client_secret_expires_at: int | None = None


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


class AdminOAuthClientCreateRequest(BaseModel):
    """Payload for administrative registration of an OAuth 2.1 client (AAL2)."""

    model_config = ConfigDict(extra="forbid")

    client_name: str = Field(
        default="MCP Client",
        max_length=128,
        description="Human-readable client application name",
    )
    redirect_uris: list[str] = Field(
        ...,
        min_length=1,
        description="List of redirect URIs using HTTPS or loopback HTTP",
    )
    client_type: str = Field(
        default="public",
        description="OAuth 2.1 client type (public or confidential)",
    )
    token_endpoint_auth_method: str = Field(
        default="none",
        description=(
            "Authentication method: 'none', 'private_key_jwt', "
            "'client_secret_basic', or 'client_secret_post'"
        ),
    )
    grant_types: list[str] | None = Field(
        default=None,
        description="Optional allowed grant types",
    )
    response_types: list[str] | None = Field(
        default=None,
        description="Optional allowed response types",
    )
    pkce_enforce: bool = Field(
        default=True,
        description="Mandate RFC 7636 PKCE S256",
    )
    access_token_ttl: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="Access token TTL in seconds",
    )


class OAuthClientPatchRequest(BaseModel):
    """Admin patch request for client approval."""

    model_config = ConfigDict(extra="ignore")

    status: (
        Literal["active", "pending_admin_approval", "disabled", "suspended", "revoked"] | None
    ) = None
    redirect_uris: list[str] | None = None
    client_name: str | None = None


class OAuthClientBulkDeleteRequest(BaseModel):
    """Payload for admin bulk deleting or purging OAuth clients."""

    model_config = ConfigDict(extra="ignore")

    client_ids: list[str] = Field(
        default_factory=list,
        description="Explicit client IDs to permanently delete",
    )
    purge_unused_dcr: bool = Field(
        default=False,
        description=(
            "Purge dynamic client registration clients with no active non-expired tokens or grants"
        ),
    )
    purge_revoked: bool = Field(
        default=False,
        description="Purge revoked clients with no active non-expired tokens or grants",
    )


# =========================================================================
# RFC 8414 & RFC 7591 Root Server Endpoints
# =========================================================================


@oauth_root_router.get(
    "/.well-known/oauth-authorization-server",
    summary="OAuth 2.1 Authorization Server Metadata (RFC 8414)",
)
@oauth_root_router.get(
    "/.well-known/oauth-authorization-server/{subpath:path}",
    summary="OAuth 2.1 Authorization Server Metadata with Subpath (RFC 8414)",
    include_in_schema=False,
)
@oauth_root_router.get(
    "/.well-known/openid-configuration",
    summary="OpenID Connect Discovery Metadata",
)
@oauth_root_router.get(
    "/.well-known/openid-configuration/{subpath:path}",
    summary="OpenID Connect Discovery Metadata with Subpath",
    include_in_schema=False,
)
async def oauth_as_metadata(request: Request, subpath: str | None = None) -> JSONResponse:
    """Return RFC 8414 authorization server discovery metadata."""
    del subpath
    _check_no_token_in_query(request)
    base_url = resolve_public_base_url(request)
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
                "urn:ietf:params:oauth:grant-type:token-exchange",
            ],
            "token_exchange_token_types_supported": [
                "urn:ietf:params:oauth:token-type:jwt",
                "urn:ietf:params:oauth:token-type:id_token",
            ],
            "response_types_supported": ["code"],
            "token_endpoint_auth_methods_supported": [
                "none",
                "private_key_jwt",
                "client_secret_basic",
                "client_secret_post",
            ],
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
    """Register public or confidential OAuth 2.1 client with strict validation."""
    _check_no_token_in_query(request)

    # 1. IP rate limiting (100/hr)
    client_ip = request.client.host if request.client else "127.0.0.1"
    check_registration_rate_limit(client_ip)

    # 2. Redirect URI validation with structured rejection logging
    try:
        validate_registration_redirect_uris(payload.redirect_uris)
    except OAuth2Error as exc:
        _logger.warning(
            "OAuth DCR registration rejected for IP %s: %s (uri_count=%d)",
            client_ip,
            exc.description,
            len(payload.redirect_uris),
            extra={
                "client_ip": client_ip,
                "rejection_reason": exc.error,
                "rejection_detail": exc.description,
                "uri_count": len(payload.redirect_uris),
            },
        )
        raise

    # 3. Grant types validation
    allowed_grants = {
        "authorization_code",
        "refresh_token",
        "urn:ietf:params:oauth:grant-type:device_code",
    }
    err_meta = "invalid_client_metadata"
    if payload.grant_types is not None:
        if not payload.grant_types:
            _logger.warning("OAuth DCR rejected: empty grant_types from IP %s", client_ip)
            raise OAuth2Error(err_meta, "grant_types cannot be empty", 400)
        unsupported = [gt for gt in payload.grant_types if gt not in allowed_grants]
        if unsupported:
            _logger.warning(
                "OAuth DCR rejected: unsupported grant_types %s from IP %s",
                unsupported,
                client_ip,
            )
            raise OAuth2Error(
                err_meta,
                f"Unsupported grant_types: {unsupported}",
                400,
            )

    # 4. Token endpoint auth method validation
    supported_methods = {
        "none",
        "private_key_jwt",
        "client_secret_basic",
        "client_secret_post",
    }
    if (
        payload.token_endpoint_auth_method is not None
        and payload.token_endpoint_auth_method not in supported_methods
    ):
        _logger.warning(
            "OAuth DCR rejected: unsupported token_endpoint_auth_method '%s' from IP %s",
            payload.token_endpoint_auth_method,
            client_ip,
            extra={"client_ip": client_ip, "auth_method": payload.token_endpoint_auth_method},
        )
        raise OAuth2Error(
            err_meta,
            f"Unsupported token_endpoint_auth_method '{payload.token_endpoint_auth_method}'",
            400,
        )

    is_confidential = (
        payload.client_type == "confidential"
        or payload.token_endpoint_auth_method in ("client_secret_basic", "client_secret_post")
    )

    eff_auth_method: str
    if is_confidential:
        eff_client_type = "confidential"
        eff_auth_method = (
            payload.token_endpoint_auth_method
            if payload.token_endpoint_auth_method in ("client_secret_basic", "client_secret_post")
            else "client_secret_basic"
        )
        raw_secret = generate_client_secret()
        secret_hash = hash_client_secret(raw_secret)
        secret_prefix = mask_client_secret_prefix(raw_secret)
    else:
        eff_client_type = "public"
        eff_auth_method = (
            payload.token_endpoint_auth_method
            if payload.token_endpoint_auth_method in ("none", "private_key_jwt")
            else "none"
        )
        raw_secret = None
        secret_hash = None
        secret_prefix = None

    eff_client_name = (
        payload.client_name.strip()
        if payload.client_name and payload.client_name.strip()
        else "MCP Client"
    )
    eff_grant_types = payload.grant_types or [
        "authorization_code",
        "refresh_token",
        "urn:ietf:params:oauth:grant-type:device_code",
    ]
    eff_response_types = payload.response_types or ["code"]

    # 5. Check workspace policy for client approval
    require_approval = (
        os.environ.get("KANBAN_REQUIRE_ADMIN_OAUTH_CLIENT_APPROVAL", "").lower() in ("true", "1")
        or request.headers.get("x-require-admin-oauth-client-approval", "").lower() == "true"
    )
    initial_status = "pending_admin_approval" if require_approval else "active"

    client_id = f"client_{secrets.token_urlsafe(16)}"
    client_record = OAuthClient(
        client_id=client_id,
        client_name=eff_client_name,
        client_type=eff_client_type,
        client_secret_hash=secret_hash,
        client_secret_prefix=secret_prefix,
        redirect_uris=payload.redirect_uris,
        status=initial_status,
        workspace_id=None,
        created_by_id=None,
    )
    session.add(client_record)
    await session.commit()

    resp_payload: dict[str, Any] = {
        "client_id": client_record.client_id,
        "client_name": client_record.client_name,
        "client_type": client_record.client_type,
        "redirect_uris": client_record.redirect_uris,
        "status": client_record.status,
        "grant_types": eff_grant_types,
        "response_types": eff_response_types,
        "token_endpoint_auth_method": eff_auth_method,
    }
    if raw_secret is not None:
        resp_payload["client_secret"] = raw_secret
        resp_payload["client_secret_expires_at"] = 0

    return JSONResponse(resp_payload, status_code=201)


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

    base_url = resolve_public_base_url(request)
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


def _redirect_with_params(redirect_uri: str, params: dict[str, Any]) -> RedirectResponse:
    """Build RFC 6749 compliant 302 redirect preserving any existing query parameters."""
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{sep}{urlencode(params)}", status_code=302)


async def _resolve_target_scope(
    session: AsyncSession,
    resource: str,
    base_url: str,
    caller_principal_id: uuid.UUID,
    caller_workspace_id: uuid.UUID,
) -> tuple[str, uuid.UUID, uuid.UUID, list[uuid.UUID] | None, str]:
    """Resolve (surface, ws_id, principal_id, allowed_projects, tier) from resource.

    Validates that:
    1. If a workspace is in resource (/mcp/{surface}/w/{ws_slug}), it exists and caller is a member.
    2. If a project is specified in resource (/p/{proj_key}), it exists in target workspace.
    3. If resource is server-level (/mcp/{surface}), tier is 'server'.
    """
    surface, ws_slug, proj_key = parse_resource_target(resource, base_url)

    if ws_slug is None:
        # Server-level resource
        return surface, caller_workspace_id, caller_principal_id, None, "server"

    # Workspace-level or project-level resource resolved via SECURITY DEFINER helpers
    ws_res = (
        await session.execute(
            text("SELECT resolve_workspace_by_slug_or_id(:slug)"),
            {"slug": ws_slug},
        )
    ).scalar_one_or_none()
    if ws_res is None:
        err = "access_denied"
        desc = f"Target workspace {ws_slug!r} not found"
        raise OAuth2Error(err, desc, 403)

    target_ws_id = ws_res if isinstance(ws_res, uuid.UUID) else uuid.UUID(str(ws_res))

    # Verify caller membership in target workspace using SECURITY DEFINER procedure
    try:
        switch_row = (
            await session.execute(
                text(
                    "SELECT workspace_id, principal_id FROM kb_auth_switch_workspace(:ws_id, :p_id)"
                ),
                {"ws_id": target_ws_id, "p_id": caller_principal_id},
            )
        ).first()
    except Exception as exc:
        err = "access_denied"
        desc = f"Principal is not a member of target workspace {ws_slug!r}"
        raise OAuth2Error(err, desc, 403) from exc

    if switch_row is None:
        err = "access_denied"
        desc = f"Principal is not a member of target workspace {ws_slug!r}"
        raise OAuth2Error(err, desc, 403)
    effective_principal_id = switch_row[1] or caller_principal_id

    allowed_projects: list[uuid.UUID] | None = None
    scope_tier = "workspace"

    if proj_key is not None:
        proj_res = (
            await session.execute(
                text("SELECT resolve_project_id_by_key_or_id(:ws_id, :ident)"),
                {"ws_id": target_ws_id, "ident": proj_key},
            )
        ).scalar_one_or_none()
        if proj_res is None:
            err = "access_denied"
            desc = f"Target project {proj_key!r} not found in workspace"
            raise OAuth2Error(err, desc, 403)
        proj_id = proj_res if isinstance(proj_res, uuid.UUID) else uuid.UUID(str(proj_res))
        allowed_projects = [proj_id]
        scope_tier = "project"

    return surface, target_ws_id, effective_principal_id, allowed_projects, scope_tier


# =========================================================================
# Interactive Authorization & Consent Flow
# =========================================================================


@oauth_root_router.get(
    "/oauth/authorize",
    summary="OAuth 2.1 Interactive Authorization / Consent Screen",
)
async def oauth_authorize(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917
    request: Request,
    session: UnauthSession,
    response_type: Annotated[str, Query()],
    client_id: Annotated[str, Query()],
    redirect_uri: Annotated[str, Query()],
    code_challenge: Annotated[str, Query()],
    code_challenge_method: Annotated[str, Query()],
    state: Annotated[str, Query()],
    resource: Annotated[str | None, Query()] = None,
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
        desc = f"state parameter required and must be <= {MAX_STATE_LEN} chars"
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

    # 6. Check client approval status (client must be active)
    if client_record.status != "active":
        params = {
            "error": "unauthorized_client",
            "error_description": f"client_{client_record.status}",
            "state": state,
        }
        return _redirect_with_params(redirect_uri, params)

    # 7. Validate resource & surface
    base_url = resolve_public_base_url(request)
    effective_resource = (resource or "").strip() or f"{base_url}/mcp/agent"
    surface = parse_surface_from_resource(effective_resource, base_url)

    # 8. Scopes validation
    allowed_surface_scopes = SURFACE_SCOPES[surface]
    requested_scopes = scope.split() if scope else list(allowed_surface_scopes)
    for sc in requested_scopes:
        if sc not in allowed_surface_scopes:
            params = {
                "error": "invalid_scope",
                "error_description": f"Scope {sc} invalid for {surface}",
                "state": state,
            }
            return _redirect_with_params(redirect_uri, params)

    # 9. Principal resolution
    resolver = getattr(request.app.state, "principal_resolver", DenyAllResolver())
    caller = await resolver.resolve(request)

    if caller is None:
        accept_hdr = request.headers.get("accept", "")
        if "application/json" in accept_hdr and "text/html" not in accept_hdr:
            raise ProblemException(
                code="AUTHENTICATION_REQUIRED",
                status=401,
                title="Authentication Required",
                detail="Authentication required before authorizing OAuth client.",
            )
        # Redirect browser to login with relative next parameter
        next_target = (
            f"{request.url.path}?{request.url.query}" if request.url.query else request.url.path
        )
        login_url = f"/login?next={urllib.parse.quote(next_target, safe='')}"
        return RedirectResponse(login_url, status_code=302)

    # 10. Admin surface requires AAL2
    if surface == "admin" and caller.aal_level < _REQUIRED_AAL_LEVEL:
        params = {
            "error": "access_denied",
            "error_description": "aal2_required",
            "state": state,
        }
        return _redirect_with_params(redirect_uri, params)

    # 11. Target scope & workspace resolution
    try:
        surface, eff_ws_id, eff_p_id, req_projects, _scope_tier = await _resolve_target_scope(
            session=session,
            resource=effective_resource,
            base_url=base_url,
            caller_principal_id=caller.principal_id,
            caller_workspace_id=caller.workspace_id,
        )
    except OAuth2Error as exc:
        params = {
            "error": exc.error,
            "error_description": exc.description,
            "state": state,
        }
        return _redirect_with_params(redirect_uri, params)

    # 12. Bind caller RLS context on session and load available projects + principal display name
    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true), "
            "set_config('app.aal_level', :aal, true)"
        ),
        {
            "p_id": str(eff_p_id),
            "w_id": str(eff_ws_id),
            "aal": str(caller.aal_level),
        },
    )
    if req_projects:
        stmt_projects = select(Project.id, Project.name).where(
            Project.workspace_id == eff_ws_id,
            Project.id.in_(req_projects),
        )
    else:
        stmt_projects = select(Project.id, Project.name).where(Project.workspace_id == eff_ws_id)
    projects_rows = (await session.execute(stmt_projects)).all()
    available_projects = [(row[0], row[1]) for row in projects_rows]

    # Resolve principal display name
    stmt_user = text("SELECT display_name FROM principals WHERE id = :p_id")
    p_name = (await session.execute(stmt_user, {"p_id": eff_p_id})).scalar_one_or_none()
    principal_display = p_name or str(eff_p_id)

    key_material = getattr(request.app.state, "key_material", None)
    session_service = getattr(request.app.state, "session_service", None)
    session_hmac_key: bytes | None = (
        key_material.session_hmac_key
        if key_material is not None and getattr(key_material, "session_hmac_key", None)
        else (
            session_service.session_hmac_key
            if session_service is not None and getattr(session_service, "session_hmac_key", None)
            else None
        )
    )
    if session_hmac_key is None:
        try:
            session_hmac_key = load_key_material().session_hmac_key
        except (KeyMaterialError, OSError):
            session_hmac_key = None
    if not session_hmac_key:
        msg = "Session HMAC key material is not configured."
        raise RuntimeError(msg)

    csrf_token = generate_consent_csrf_token(
        session_hmac_key=session_hmac_key,
        session_id=caller.session_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
        surface=surface,
    )

    return render_consent_screen(
        client_name=client_record.client_name,
        redirect_uri=redirect_uri,
        surface=surface,
        requested_scopes=requested_scopes,
        state=state,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        resource=effective_resource,
        client_id=client_id,
        csrf_token=csrf_token,
        available_projects=available_projects,
        principal_display=principal_display,
    )


@oauth_root_router.post(
    "/oauth/authorize/decision",
    summary="Process OAuth 2.1 Consent Decision",
)
async def oauth_authorize_decision(  # noqa: C901, PLR0912, PLR0915
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
    csrf_token = str(form.get("csrf_token", ""))
    scopes_val = form.get("scopes")
    if isinstance(scopes_val, list):
        selected_scopes = [str(s) for s in scopes_val]
    elif isinstance(scopes_val, str) and scopes_val:
        selected_scopes = [scopes_val]
    else:
        selected_scopes = []
    allowed_project_id = str(form.get("allowed_project_id", "__ALL__"))

    # 1. Same-origin Sec-Fetch-Site and Origin verification (403 CSRF_INVALID on mismatch)
    if not verify_same_origin_request(request):
        raise ProblemException(
            code="CSRF_INVALID",
            status=403,
            title="CSRF Validation Failed",
            detail="Cross-origin OAuth consent submission rejected.",
        )

    # 2. Surface resolution
    base_url = resolve_public_base_url(request)
    surface = parse_surface_from_resource(resource, base_url)

    # 3. HMAC-SHA256 CSRF verification bound to caller session and OAuth parameters
    key_material = getattr(request.app.state, "key_material", None)
    session_service = getattr(request.app.state, "session_service", None)
    session_hmac_key: bytes | None = (
        key_material.session_hmac_key
        if key_material is not None and getattr(key_material, "session_hmac_key", None)
        else (
            session_service.session_hmac_key
            if session_service is not None and getattr(session_service, "session_hmac_key", None)
            else None
        )
    )
    if session_hmac_key is None:
        try:
            session_hmac_key = load_key_material().session_hmac_key
        except (KeyMaterialError, OSError):
            session_hmac_key = None
    if not session_hmac_key:
        msg = "Session HMAC key material is not configured."
        raise RuntimeError(msg)

    if not verify_consent_csrf_token(
        token=csrf_token,
        session_hmac_key=session_hmac_key,
        session_id=caller.session_id,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=code_challenge,
        state=state,
        surface=surface,
    ):
        raise ProblemException(
            code="CSRF_INVALID",
            status=403,
            title="CSRF Validation Failed",
            detail="OAuth consent CSRF token is invalid, expired, or tampered.",
        )

    # 4. Lookup client and validate redirect URI exact string match
    stmt_client = select(OAuthClient).where(OAuthClient.client_id == client_id)
    client_record = (await session.execute(stmt_client)).scalar_one_or_none()
    if client_record is None or not validate_redirect_uri(
        redirect_uri, client_record.redirect_uris
    ):
        err = "invalid_request"
        desc = "Invalid client or redirect URI"
        raise OAuth2Error(err, desc, 400)

    # 5. Re-verify client approval status (client must be active)
    if client_record.status != "active":
        params = {
            "error": "unauthorized_client",
            "error_description": f"client_{client_record.status}",
            "state": state,
        }
        return _redirect_with_params(redirect_uri, params)

    # 6. Admin surface requires AAL2
    if surface == "admin" and caller.aal_level < _REQUIRED_AAL_LEVEL:
        params = {
            "error": "access_denied",
            "error_description": "aal2_required",
            "state": state,
        }
        return _redirect_with_params(redirect_uri, params)

    # 7. Handle User Deny
    if action.lower() != "approve":
        params = {
            "error": "access_denied",
            "error_description": "User denied consent",
            "state": state,
        }
        return _redirect_with_params(redirect_uri, params)

    # 8. Scope validation and rejection of empty approved scopes
    allowed_surface_scopes = SURFACE_SCOPES[surface]
    approved_scopes = [s for s in selected_scopes if s in allowed_surface_scopes]
    if not approved_scopes:
        params = {
            "error": "invalid_scope",
            "error_description": "At least one valid scope must be approved",
            "state": state,
        }
        return _redirect_with_params(redirect_uri, params)

    # 8. Target scope & workspace resolution
    try:
        surface, eff_ws_id, eff_p_id, req_projects, _scope_tier = await _resolve_target_scope(
            session=session,
            resource=resource,
            base_url=base_url,
            caller_principal_id=caller.principal_id,
            caller_workspace_id=caller.workspace_id,
        )
    except OAuth2Error as exc:
        params = {
            "error": exc.error,
            "error_description": exc.description,
            "state": state,
        }
        return _redirect_with_params(redirect_uri, params)

    # 9. Project narrowing
    if req_projects:
        allowed_projects = req_projects
    else:
        allowed_projects = None
        if allowed_project_id and allowed_project_id != "__ALL__":
            with contextlib.suppress(ValueError):
                allowed_projects = [uuid.UUID(allowed_project_id)]

    # 10. Bind effective target workspace & principal RLS context on session
    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true), "
            "set_config('app.aal_level', :aal, true)"
        ),
        {
            "p_id": str(eff_p_id),
            "w_id": str(eff_ws_id),
            "aal": str(caller.aal_level),
        },
    )

    # 11. Create or lookup OAuthGrant
    grant = OAuthGrant(
        workspace_id=eff_ws_id,
        principal_id=eff_p_id,
        client_id=client_record.id,
        surface=surface,
        scopes=approved_scopes,
        allowed_projects=allowed_projects,
    )
    session.add(grant)
    await session.flush()

    # 11. Generate single-use authorization code (256-bit URL-safe)
    code = secrets.token_urlsafe(32)
    code_sha = hash_token(code)
    now = datetime.now(UTC)

    auth_code_record = OAuthAuthorizationCode(
        code_sha256=code_sha,
        grant_id=grant.id,
        client_id=client_record.id,
        principal_id=eff_p_id,
        workspace_id=eff_ws_id,
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
    return _redirect_with_params(redirect_uri, params)


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
    err_inv_client = "invalid_client"
    err_inv_grant = "invalid_grant"

    # Client authentication extraction (client_secret_basic vs client_secret_post vs none)
    auth_header = request.headers.get("authorization", "")
    basic_client_id: str | None = None
    basic_client_secret: str | None = None

    if auth_header.strip().lower().startswith("basic "):
        raw_b64 = auth_header.strip()[6:].strip()
        try:
            decoded_bytes = base64.b64decode(raw_b64, validate=True)
            decoded_str = decoded_bytes.decode("utf-8", errors="replace")
            if ":" in decoded_str:
                raw_cid, raw_sec = decoded_str.split(":", 1)
                basic_client_id = urllib.parse.unquote_plus(raw_cid)
                basic_client_secret = urllib.parse.unquote_plus(raw_sec)
            else:
                desc = "Malformed Basic authorization header"
                raise OAuth2Error(err_inv_client, desc, 401)
        except (ValueError, UnicodeDecodeError) as exc:
            if isinstance(exc, OAuth2Error):
                raise
            desc = "Invalid Basic authorization header encoding"
            raise OAuth2Error(err_inv_client, desc, 401) from None

    body_client_id = form.get("client_id")
    body_client_secret = form.get("client_secret")

    if basic_client_id is not None and body_client_secret is not None:
        desc = "Multiple client authentication methods attempted"
        raise OAuth2Error(err_inv_client, desc, 401)

    if basic_client_id is not None and body_client_id and basic_client_id != str(body_client_id):
        desc = "client_id mismatch between header and body"
        raise OAuth2Error(err_inv_client, desc, 401)

    if basic_client_id is not None:
        eff_client_id = basic_client_id
        eff_client_secret = basic_client_secret
    elif body_client_secret is not None:
        eff_client_id = str(body_client_id) if body_client_id else ""
        eff_client_secret = str(body_client_secret)
    else:
        eff_client_id = str(body_client_id) if body_client_id else ""
        eff_client_secret = None

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

    base_url = resolve_public_base_url(request)
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

        # Client authentication and authorization code binding verification
        stmt_client = select(OAuthClient).where(OAuthClient.id == code_record.client_id)
        client_record = (await session.execute(stmt_client)).scalar_one_or_none()
        if client_record is None or client_record.status != "active":
            desc = "Client is invalid or inactive"
            raise OAuth2Error(err_inv_client, desc, 401)

        if eff_client_id and eff_client_id != client_record.client_id:
            desc = "client_id mismatch with authorization code"
            raise OAuth2Error(err_inv_grant, desc, 400)

        eff_client_id = client_record.client_id

        # Confidential client requires client_secret verification
        if client_record.client_type == "confidential":
            if not eff_client_secret:
                desc = "Confidential client authentication required"
                raise OAuth2Error(err_inv_client, desc, 401)
            if not verify_client_secret(eff_client_secret, client_record.client_secret_hash):
                desc = "Invalid client secret"
                raise OAuth2Error(err_inv_client, desc, 401)

        # Validate redirect_uri exact match
        if code_record.redirect_uri != eff_redirect_uri:
            err = "invalid_grant"
            desc = "redirect_uri mismatch"
            raise OAuth2Error(err, desc, 400)

        # Validate resource match if provided
        if eff_resource and (code_record.resource or "").rstrip("/") != eff_resource.rstrip("/"):
            err = "invalid_grant"
            desc = "resource mismatch"
            raise OAuth2Error(err, desc, 400)

        # Validate PKCE S256 (MANDATORY IN ADDITION TO CLIENT SECRET)
        if not verify_pkce_s256(eff_code_verifier, code_record.code_challenge):
            err = "invalid_grant"
            desc = "PKCE code_verifier validation failed"
            raise OAuth2Error(err, desc, 400)

        # Mark code consumed
        code_record.consumed_at = now

        # Determine scope tier
        _t_surface, t_ws_slug, t_proj_key = parse_resource_target(
            code_record.resource or "", base_url
        )
        if t_ws_slug is None:
            scope_tier = "server"
        elif code_record.allowed_projects or t_proj_key:
            scope_tier = "project"
        else:
            scope_tier = "workspace"

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
            scope_tier=scope_tier,
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

        # Client lookup & authentication for refresh token
        stmt_client = select(OAuthClient).where(OAuthClient.id == existing_rt.client_id)
        client_record = (await session.execute(stmt_client)).scalar_one_or_none()
        if client_record is not None:
            if eff_client_id and eff_client_id != client_record.client_id:
                desc = "client_id mismatch with refresh token"
                raise OAuth2Error(err_inv_grant, desc, 400)
            if client_record.client_type == "confidential":
                if not eff_client_secret:
                    desc = "Confidential client authentication required"
                    raise OAuth2Error(err_inv_client, desc, 401)
                if not verify_client_secret(eff_client_secret, client_record.client_secret_hash):
                    desc = "Invalid client secret"
                    raise OAuth2Error(err_inv_client, desc, 401)
            eff_client_id = client_record.client_id

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
        eff_target_resource = eff_resource or surface_url
        _t_surface, t_ws_slug, t_proj_key = parse_resource_target(eff_target_resource, base_url)
        if t_ws_slug is None:
            scope_tier = "server"
        elif grant.allowed_projects or t_proj_key:
            scope_tier = "project"
        else:
            scope_tier = "workspace"

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
            scope_tier=scope_tier,
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

    # 4. RFC 8693 OAuth 2.0 Token Exchange (KB-AUTH-OIDC-EXCHANGE-01, KAN-74)
    if eff_grant_type == "urn:ietf:params:oauth:grant-type:token-exchange":
        eff_subj_token = form.get("subject_token")
        if not eff_subj_token or not isinstance(eff_subj_token, str):
            err = "invalid_request"
            desc = "subject_token parameter required"
            raise OAuth2Error(err, desc, 400)

        eff_subj_type = form.get("subject_token_type")
        allowed_token_types = {
            "urn:ietf:params:oauth:token-type:jwt",
            "urn:ietf:params:oauth:token-type:id_token",
            "id_token",
        }
        if not eff_subj_type or str(eff_subj_type) not in allowed_token_types:
            err = "invalid_request"
            desc = f"Unsupported subject_token_type {eff_subj_type!r}"
            raise OAuth2Error(err, desc, 400)

        from database.models.workload_identity import WorkloadIdentityPolicy  # noqa: PLC0415
        from kanban.auth.oidc.workload import (  # noqa: PLC0415
            _extract_unverified_header_and_claims,
            validate_workload_jwt,
        )

        _, unverified_claims = _extract_unverified_header_and_claims(eff_subj_token)
        unverified_iss = str(unverified_claims.get("iss", "")).rstrip("/")
        if not unverified_iss:
            err = "invalid_grant"
            desc = "subject_token missing iss claim"
            raise OAuth2Error(err, desc, 400)

        stmt_pol = select(WorkloadIdentityPolicy).where(WorkloadIdentityPolicy.is_enabled.is_(True))
        eff_policy_id = form.get("policy_id")
        if eff_policy_id:
            with contextlib.suppress(ValueError):
                pol_uuid = uuid.UUID(str(eff_policy_id))
                stmt_pol = stmt_pol.where(WorkloadIdentityPolicy.id == pol_uuid)
        if eff_client_id:
            stmt_pol = stmt_pol.where(WorkloadIdentityPolicy.client_id == eff_client_id)

        all_policies = (await session.execute(stmt_pol)).scalars().all()
        matched_policy: WorkloadIdentityPolicy | None = None
        for pol in all_policies:
            if pol.issuer.rstrip("/") == unverified_iss:
                matched_policy = pol
                break

        if matched_policy is None:
            err = "invalid_grant"
            desc = f"No active workload identity policy found for issuer {unverified_iss!r}"
            raise OAuth2Error(err, desc, 400)

        if matched_policy.allowed_cidrs:
            import ipaddress  # noqa: PLC0415

            from kanban.security.client_ip import resolve_client_ip  # noqa: PLC0415

            trusted_proxies = (
                os.environ.get("KANBAN_TRUSTED_PROXIES")
                or os.environ.get("KB_TRUSTED_PROXIES")
                or "127.0.0.1/32,::1/128"
            )
            client_ip = resolve_client_ip(request.scope, trusted_proxies=trusted_proxies)
            if not client_ip:
                err = "invalid_grant"
                desc = "Could not resolve client IP for policy CIDR enforcement"
                raise OAuth2Error(err, desc, 403)

            clean_ip = client_ip.split("/")[0] if "/" in client_ip else client_ip
            try:
                ip_obj = ipaddress.ip_address(clean_ip)
                cidr_allowed = any(
                    ip_obj in ipaddress.ip_network(str(c), strict=False)
                    for c in matched_policy.allowed_cidrs
                )
            except ValueError:
                cidr_allowed = False

            if not cidr_allowed:
                err = "invalid_grant"
                desc = (
                    f"Client IP {client_ip!r} is not permitted by workload policy CIDR restrictions"
                )
                raise OAuth2Error(err, desc, 403)

        validated_claims = await validate_workload_jwt(
            session=session,
            raw_jwt=eff_subj_token,
            policy=matched_policy,
        )

        from joserfc import jwt  # noqa: PLC0415

        from kanban.oauth.jwt import _get_signing_eckey  # noqa: PLC0415

        token_ttl = min(matched_policy.max_ttl_seconds, ACCESS_TOKEN_TTL_SECONDS)
        current_ts = int(time.time())
        eckey, kid = _get_signing_eckey()
        jwt_header = {"alg": "ES256", "typ": "JWT", "kid": kid}
        jwt_jti = str(uuid.uuid4())
        surface_url = f"{base_url}/mcp/{matched_policy.surface}"

        sub_principal = str(matched_policy.created_by_id or matched_policy.id)
        claims_out: dict[str, Any] = {
            "iss": base_url,
            "sub": sub_principal,
            "aud": surface_url,
            "surface": matched_policy.surface,
            "scope": " ".join(matched_policy.scopes),
            "client_id": matched_policy.client_id,
            "policy_id": str(matched_policy.id),
            "ws": str(matched_policy.workspace_id),
            "jti": jwt_jti,
            "iat": current_ts,
            "exp": current_ts + token_ttl,
            "token_kind": "workload",
            "capability_mask": matched_policy.capability_mask,
            "workload_sub": validated_claims.get("sub"),
        }
        if matched_policy.allowed_project_ids:
            claims_out["allowed_project_ids"] = [str(p) for p in matched_policy.allowed_project_ids]
            claims_out["allowed_projects"] = [str(p) for p in matched_policy.allowed_project_ids]
        if matched_policy.allowed_cidrs:
            claims_out["allowed_cidrs"] = list(matched_policy.allowed_cidrs)

        access_token = jwt.encode(jwt_header, claims_out, eckey)

        import json  # noqa: PLC0415

        await session.execute(
            text(
                "SELECT append_activity("
                "  :ws, NULL, NULL, :actor, 'WORKLOAD_TOKEN_EXCHANGED',"
                "  CAST(:payload AS jsonb)"
                ")"
            ),
            {
                "ws": matched_policy.workspace_id,
                "actor": matched_policy.created_by_id,
                "payload": json.dumps(
                    {
                        "policy_id": str(matched_policy.id),
                        "policy_name": matched_policy.name,
                        "issuer": matched_policy.issuer,
                        "subject": validated_claims.get("sub"),
                        "surface": matched_policy.surface,
                        "scopes": matched_policy.scopes,
                        "jti": jwt_jti,
                    }
                ),
            },
        )
        await session.commit()

        return JSONResponse(
            {
                "access_token": access_token,
                "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "token_type": "Bearer",
                "expires_in": token_ttl,
                "scope": " ".join(matched_policy.scopes),
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


@oauth_v1_router.post(
    "/admin/oauth-clients",
    status_code=status.HTTP_201_CREATED,
    summary="Admin register OAuth 2.1 client (AAL2)",
    dependencies=[Depends(require_admin_aal2)],
)
@oauth_v1_router.post(
    "/oauth/admin/oauth-clients",
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
    dependencies=[Depends(require_admin_aal2)],
)
async def admin_register_oauth_client(
    payload: AdminOAuthClientCreateRequest,
    caller: Caller,
    session: Session,
) -> JSONResponse:
    """Workspace Admin registration of an OAuth 2.1 client requiring AAL2."""
    await _require_admin_aal2(caller, session)

    # 1. Strict redirect URI validation allowing https:// or loopback http://
    validate_registration_redirect_uris(payload.redirect_uris)

    # 2. Token endpoint auth method and client type validation
    valid_auth_methods = ("none", "private_key_jwt", "client_secret_basic", "client_secret_post")
    if payload.token_endpoint_auth_method not in valid_auth_methods:
        raise ProblemException(
            code="INVALID_CLIENT_METADATA",
            status=400,
            title="Invalid Client Metadata",
            detail=f"token_endpoint_auth_method must be one of {valid_auth_methods}.",
        )

    if payload.grant_types and "client_credentials" in payload.grant_types:
        raise ProblemException(
            code="UNSUPPORTED_GRANT_TYPE",
            status=400,
            title="Unsupported Grant Type",
            detail="The client_credentials grant type is strictly prohibited in 👍kanban.",
        )

    if payload.client_type not in ("public", "confidential"):
        raise ProblemException(
            code="INVALID_CLIENT_METADATA",
            status=400,
            title="Invalid Client Metadata",
            detail="client_type must be 'public' or 'confidential'.",
        )

    if payload.client_type == "public" and not payload.pkce_enforce:
        raise ProblemException(
            code="INVALID_CLIENT_METADATA",
            status=400,
            title="Invalid Client Metadata",
            detail="Public OAuth 2.1 clients must enforce PKCE S256.",
        )

    is_confidential = (
        payload.client_type == "confidential"
        or payload.token_endpoint_auth_method in ("client_secret_basic", "client_secret_post")
    )

    eff_auth_method: str
    if is_confidential:
        eff_client_type = "confidential"
        eff_auth_method = (
            payload.token_endpoint_auth_method
            if payload.token_endpoint_auth_method in ("client_secret_basic", "client_secret_post")
            else "client_secret_basic"
        )
        raw_secret = generate_client_secret()
        secret_hash = hash_client_secret(raw_secret)
        secret_prefix = mask_client_secret_prefix(raw_secret)
    else:
        eff_client_type = "public"
        eff_auth_method = (
            payload.token_endpoint_auth_method
            if payload.token_endpoint_auth_method in ("none", "private_key_jwt")
            else "none"
        )
        raw_secret = None
        secret_hash = None
        secret_prefix = None

    eff_client_name = (
        payload.client_name.strip()
        if payload.client_name and payload.client_name.strip()
        else "MCP Client"
    )

    client_id = f"client_{secrets.token_urlsafe(16)}"
    client_record = OAuthClient(
        client_id=client_id,
        client_name=eff_client_name,
        client_type=eff_client_type,
        client_secret_hash=secret_hash,
        client_secret_prefix=secret_prefix,
        redirect_uris=payload.redirect_uris,
        status="active",
        workspace_id=caller.workspace_id,
        created_by_id=caller.principal_id,
    )
    session.add(client_record)
    await session.flush()

    # 4. Record audit activity event
    await record_activity(
        session=session,
        workspace_id=caller.workspace_id,
        actor_principal_id=caller.principal_id,
        event_type=ActivityEventType.OAUTH_CLIENT_REGISTERED,
        payload={
            "client_id": client_record.client_id,
            "client_name": client_record.client_name,
            "client_type": client_record.client_type,
            "redirect_uris": client_record.redirect_uris,
            "token_endpoint_auth_method": eff_auth_method,
        },
    )

    await session.commit()

    resp: dict[str, Any] = {
        "client_id": client_record.client_id,
        "client_name": client_record.client_name,
        "client_type": client_record.client_type,
        "token_endpoint_auth_method": eff_auth_method,
        "redirect_uris": client_record.redirect_uris,
        "status": client_record.status,
        "pkce_enforce": payload.pkce_enforce,
        "access_token_ttl": payload.access_token_ttl,
        "grant_types": payload.grant_types,
        "created_at": client_record.created_at.isoformat(),
        "updated_at": client_record.updated_at.isoformat(),
    }
    if raw_secret is not None:
        resp["client_secret"] = raw_secret
        resp["client_secret_prefix"] = secret_prefix

    return JSONResponse(resp, status_code=status.HTTP_201_CREATED)


async def _permanently_delete_clients(
    session: AsyncSession,
    client_uuids: list[uuid.UUID],
) -> int:
    """Permanently delete OAuth clients and cascade dependent records across all 5 tables."""
    if not client_uuids:
        return 0

    # 1. Fetch grant IDs for these clients
    stmt_g = select(OAuthGrant.id).where(OAuthGrant.client_id.in_(client_uuids))
    grant_ids = (await session.execute(stmt_g)).scalars().all()

    # 2. oauth_revoked_jtis (FK -> oauth_grants.id)
    if grant_ids:
        await session.execute(
            delete(OAuthRevokedJti).where(OAuthRevokedJti.grant_id.in_(grant_ids))
        )

    # 3. oauth_refresh_tokens (FK -> oauth_clients.id and oauth_grants.id)
    await session.execute(
        delete(OAuthRefreshToken).where(
            (OAuthRefreshToken.client_id.in_(client_uuids))
            | (OAuthRefreshToken.grant_id.in_(grant_ids) if grant_ids else False)
        )
    )

    # 4. oauth_authorization_codes (FK -> oauth_clients.id and oauth_grants.id)
    await session.execute(
        delete(OAuthAuthorizationCode).where(
            (OAuthAuthorizationCode.client_id.in_(client_uuids))
            | (OAuthAuthorizationCode.grant_id.in_(grant_ids) if grant_ids else False)
        )
    )

    # 5. oauth_device_codes (FK -> oauth_clients.id)
    await session.execute(
        delete(OAuthDeviceCode).where(OAuthDeviceCode.client_id.in_(client_uuids))
    )

    # 6. oauth_grants (FK -> oauth_clients.id)
    await session.execute(delete(OAuthGrant).where(OAuthGrant.client_id.in_(client_uuids)))

    # 7. oauth_clients
    del_res = await session.execute(delete(OAuthClient).where(OAuthClient.id.in_(client_uuids)))
    return del_res.rowcount or len(client_uuids)


@oauth_v1_router.get(
    "/admin/oauth-clients",
    summary="Admin list registered OAuth 2.1 clients (AAL2)",
    dependencies=[Depends(require_admin_aal2)],
)
@oauth_v1_router.get(
    "/oauth/admin/oauth-clients",
    include_in_schema=False,
    dependencies=[Depends(require_admin_aal2)],
)
async def admin_list_oauth_clients(  # noqa: PLR0913
    caller: Caller,
    session: Session,
    *,
    status: Annotated[
        Literal["active", "pending_admin_approval", "disabled", "suspended", "revoked"] | None,
        Query(description="Optional filter by client status"),
    ] = None,
    q: Annotated[
        str | None,
        Query(
            description=(
                "Case-insensitive search query across client_name, client_id, and redirect_uris"
            )
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=200, description="Pagination limit (1-200)"),
    ] = 50,
    offset: Annotated[
        int,
        Query(ge=0, description="Pagination offset"),
    ] = 0,
    envelope: Annotated[
        bool,
        Query(description="Wrap response in envelope containing items, total, limit, and offset"),
    ] = False,
) -> JSONResponse:
    """Workspace/Server Admin list of all dynamically registered OAuth clients."""
    await _require_admin_aal2(caller, session)

    stmt = select(OAuthClient)
    count_stmt = select(func.count(OAuthClient.id))

    if status is not None:
        stmt = stmt.where(OAuthClient.status == status)
        count_stmt = count_stmt.where(OAuthClient.status == status)

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        search_filter = (
            OAuthClient.client_name.ilike(pattern)
            | OAuthClient.client_id.ilike(pattern)
            | func.array_to_string(OAuthClient.redirect_uris, " ").ilike(pattern)
        )
        stmt = stmt.where(search_filter)
        count_stmt = count_stmt.where(search_filter)

    total = (await session.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(OAuthClient.created_at.desc()).offset(offset).limit(limit)
    records = (await session.execute(stmt)).scalars().all()

    items = [
        {
            "client_id": c.client_id,
            "client_name": c.client_name,
            "client_type": c.client_type,
            "client_secret_prefix": c.client_secret_prefix,
            "redirect_uris": c.redirect_uris,
            "status": c.status,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in records
    ]

    resp_headers = {"X-Total-Count": str(total)}
    if envelope:
        return JSONResponse(
            {
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
            },
            headers=resp_headers,
        )

    return JSONResponse(items, headers=resp_headers)


@oauth_v1_router.patch(
    "/admin/oauth-clients/{client_id}",
    summary="Admin approve or disable OAuth client (AAL2)",
    dependencies=[Depends(require_admin_aal2)],
)
@oauth_v1_router.patch(
    "/oauth/admin/oauth-clients/{client_id}",
    include_in_schema=False,
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

    if payload.redirect_uris is not None:
        validate_registration_redirect_uris(payload.redirect_uris)
        client_record.redirect_uris = payload.redirect_uris
    if payload.client_name is not None:
        client_record.client_name = payload.client_name
    if payload.status is not None:
        client_record.status = payload.status
        if payload.status in ("disabled", "suspended", "revoked"):
            stmt_g = select(OAuthGrant).where(
                OAuthGrant.client_id == client_record.id,
                OAuthGrant.revoked_at.is_(None),
            )
            grants = (await session.execute(stmt_g)).scalars().all()
            for g in grants:
                await revoke_grant_family(session, g.id, g.workspace_id)

    client_record.updated_at = datetime.now(UTC)
    await session.commit()

    return JSONResponse(
        {
            "client_id": client_record.client_id,
            "client_name": client_record.client_name,
            "client_type": client_record.client_type,
            "client_secret_prefix": client_record.client_secret_prefix,
            "status": client_record.status,
            "redirect_uris": client_record.redirect_uris,
            "updated_at": client_record.updated_at.isoformat(),
        }
    )


@oauth_v1_router.delete(
    "/admin/oauth-clients/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Admin revoke or delete OAuth client (AAL2)",
    dependencies=[Depends(require_admin_aal2)],
)
@oauth_v1_router.delete(
    "/oauth/admin/oauth-clients/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
    dependencies=[Depends(require_admin_aal2)],
)
async def admin_delete_oauth_client(
    client_id: str,
    caller: Caller,
    session: Session,
    *,
    permanent: Annotated[
        bool,
        Query(description="Whether to permanently hard-delete client and cascade tokens/grants"),
    ] = False,
) -> Response:
    """Admin revocation of OAuth client and all issued grants, or permanent cascade deletion."""
    await _require_admin_aal2(caller, session)

    stmt = select(OAuthClient).where(OAuthClient.client_id == client_id)
    client_record = (await session.execute(stmt)).scalar_one_or_none()
    if client_record is None:
        not_found()

    if permanent:
        await _permanently_delete_clients(session, [client_record.id])
        await session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    stmt_g = select(OAuthGrant).where(
        OAuthGrant.client_id == client_record.id,
        OAuthGrant.revoked_at.is_(None),
    )
    grants = (await session.execute(stmt_g)).scalars().all()
    for g in grants:
        await revoke_grant_family(session, g.id, g.workspace_id)

    client_record.status = "revoked"
    client_record.updated_at = datetime.now(UTC)
    await session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _has_active_grants_or_tokens(
    session: AsyncSession,
    client_internal_id: uuid.UUID,
    now_ts: datetime,
) -> bool:
    """Check whether a client has active grants or non-expired refresh tokens."""
    stmt_grants = select(func.count(OAuthGrant.id)).where(
        OAuthGrant.client_id == client_internal_id,
        OAuthGrant.revoked_at.is_(None),
    )
    if (await session.execute(stmt_grants)).scalar_one() > 0:
        return True

    stmt_tokens = select(func.count(OAuthRefreshToken.id)).where(
        OAuthRefreshToken.client_id == client_internal_id,
        OAuthRefreshToken.revoked_at.is_(None),
        OAuthRefreshToken.expires_at > now_ts,
    )
    return (await session.execute(stmt_tokens)).scalar_one() > 0


async def _collect_stale_clients(
    session: AsyncSession,
    where_clause: ColumnElement[bool],
    already_selected: set[uuid.UUID],
    now_ts: datetime,
) -> dict[uuid.UUID, str]:
    """Collect candidate clients matching where_clause that have zero active grants or tokens."""
    stmt = select(OAuthClient).where(where_clause)
    clients = (await session.execute(stmt)).scalars().all()
    found: dict[uuid.UUID, str] = {}
    for c in clients:
        if c.id not in already_selected and not await _has_active_grants_or_tokens(
            session, c.id, now_ts
        ):
            found[c.id] = c.client_id
    return found


@oauth_v1_router.post(
    "/admin/oauth-clients/bulk-delete",
    summary="Admin bulk delete or purge OAuth clients (AAL2)",
    dependencies=[Depends(require_admin_aal2)],
)
@oauth_v1_router.post(
    "/oauth/admin/oauth-clients/bulk-delete",
    include_in_schema=False,
    dependencies=[Depends(require_admin_aal2)],
)
async def admin_bulk_delete_oauth_clients(
    payload: OAuthClientBulkDeleteRequest,
    caller: Caller,
    session: Session,
) -> JSONResponse:
    """Atomically hard-delete specific clients or purge stale DCR / revoked clients."""
    await _require_admin_aal2(caller, session)

    if not payload.client_ids and not payload.purge_unused_dcr and not payload.purge_revoked:
        raise ProblemException(
            code="INVALID_BULK_DELETE_REQUEST",
            status=400,
            title="Invalid Bulk Delete Request",
            detail=(
                "At least one target mode (client_ids, purge_unused_dcr, or purge_revoked) "
                "must be specified."
            ),
        )

    targets_to_delete: dict[uuid.UUID, str] = {}
    now_ts = datetime.now(UTC)

    # 1. Explicit client_ids
    if payload.client_ids:
        stmt_explicit = select(OAuthClient).where(OAuthClient.client_id.in_(payload.client_ids))
        explicit_clients = (await session.execute(stmt_explicit)).scalars().all()
        for c in explicit_clients:
            targets_to_delete[c.id] = c.client_id

    # 2. Purge unused DCR clients
    if payload.purge_unused_dcr:
        stale_dcr = await _collect_stale_clients(
            session,
            OAuthClient.created_by_id.is_(None),
            set(targets_to_delete.keys()),
            now_ts,
        )
        targets_to_delete.update(stale_dcr)

    # 3. Purge revoked clients
    if payload.purge_revoked:
        stale_revoked = await _collect_stale_clients(
            session,
            OAuthClient.status == "revoked",
            set(targets_to_delete.keys()),
            now_ts,
        )
        targets_to_delete.update(stale_revoked)

    target_uuids = list(targets_to_delete.keys())
    deleted_client_ids = [targets_to_delete[uid] for uid in target_uuids]

    if target_uuids:
        await _permanently_delete_clients(session, target_uuids)

    await session.commit()

    return JSONResponse(
        {
            "deleted_count": len(deleted_client_ids),
            "deleted_client_ids": sorted(deleted_client_ids),
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
