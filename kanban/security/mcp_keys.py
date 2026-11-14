# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Scoped kb_* API keys, surface binding, scopes and token introspection (KB-P4-02a)."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import secrets
import time
import uuid  # Runtime import required for Pydantic / dataclass type annotations
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import text

from database.models.mcp_api_key import McpApiKey
from database.models.principals import Principal
from kanban.api.problems import ProblemException, not_found
from kanban.security.keys import derive_subkey, load_key_material
from kanban.services.activity import ActivityEventType, record_activity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "ALLOWED_SURFACES",
    "DISPLAY_HINT_LENGTH",
    "KEY_RANDOM_BYTES_COUNT",
    "KEY_TOKEN_TOTAL_LENGTH",
    "MAX_KEY_TTL_DAYS",
    "PREFIX_TO_SURFACE",
    "SURFACE_ALLOWED_SCOPES",
    "SURFACE_KEY_PREFIXES",
    "McpIntrospectionResult",
    "create_internal_mcp_auth_header",
    "derive_internal_mcp_auth_key",
    "generate_mcp_api_key",
    "hash_mcp_api_key",
    "introspect_subject_token",
    "mint_mcp_api_key",
    "revoke_mcp_api_key",
    "verify_internal_mcp_auth_header",
]

ALLOWED_SURFACES: Final[frozenset[str]] = frozenset({"agent", "docs", "admin"})

SURFACE_KEY_PREFIXES: Final[dict[str, str]] = {
    "agent": "kb_agt_",
    "docs": "kb_doc_",
    "admin": "kb_adm_",
}

PREFIX_TO_SURFACE: Final[dict[str, str]] = {v: k for k, v in SURFACE_KEY_PREFIXES.items()}

SURFACE_ALLOWED_SCOPES: Final[dict[str, frozenset[str]]] = {
    "agent": frozenset({"agent:read", "agent:write"}),
    "docs": frozenset({"docs:read", "docs:write"}),
    "admin": frozenset({"admin:read", "admin:write", "admin:destructive"}),
}

ALL_SCOPES: Final[frozenset[str]] = frozenset().union(*SURFACE_ALLOWED_SCOPES.values())

MAX_KEY_TTL_DAYS: Final[int] = 365
KEY_RANDOM_BYTES_COUNT: Final[int] = 32
KEY_TOKEN_TOTAL_LENGTH: Final[int] = 50  # 7-char prefix + 43-char unpadded base64url
DISPLAY_HINT_LENGTH: Final[int] = 4
INTERNAL_AUTH_DRIFT_SECONDS: Final[int] = 300


@dataclass(frozen=True, slots=True)
class McpIntrospectionResult:
    """Introspection payload returned to MCP protocol handlers and gateways."""

    active: bool
    principal_id: uuid.UUID | None = None
    agent_principal_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    execution_id: uuid.UUID | None = None
    surface: str | None = None
    scopes: list[str] | None = None
    token_kind: str | None = "api_key"  # noqa: S105
    reason: str | None = None
    allowed_projects: list[uuid.UUID] | None = None
    allowed_tools: list[str] | None = None
    calls_used: int | None = None
    max_calls: int | None = None
    expires_at: datetime | str | None = None

    def to_dict(self) -> dict[str, Any]:  # noqa: C901
        """Convert introspection result to API JSON payload."""
        if not self.active:
            res: dict[str, Any] = {"active": False}
            if self.reason:
                res["reason"] = self.reason
            if self.calls_used is not None:
                res["calls_used"] = self.calls_used
            if self.max_calls is not None:
                res["max_calls"] = self.max_calls
            return res
        payload: dict[str, Any] = {
            "active": True,
            "principal_id": str(self.principal_id),
            "workspace_id": str(self.workspace_id),
            "surface": self.surface,
            "scopes": self.scopes or [],
            "token_kind": self.token_kind,
        }
        if self.agent_principal_id is not None:
            payload["agent_principal_id"] = str(self.agent_principal_id)
        if self.project_id is not None:
            payload["project_id"] = str(self.project_id)
        if self.execution_id is not None:
            payload["execution_id"] = str(self.execution_id)
        if self.allowed_projects is not None:
            payload["allowed_projects"] = [str(p) for p in self.allowed_projects]
        if self.allowed_tools is not None:
            payload["allowed_tools"] = self.allowed_tools
        if self.calls_used is not None:
            payload["calls_used"] = self.calls_used
        if self.max_calls is not None:
            payload["max_calls"] = self.max_calls
        if self.expires_at is not None:
            payload["expires_at"] = (
                self.expires_at.isoformat()
                if isinstance(self.expires_at, datetime)
                else str(self.expires_at)
            )
        return payload


def hash_mcp_api_key(token: str) -> bytes:
    """Compute SHA-256 digest of plaintext token."""
    return hashlib.sha256(token.encode("ascii")).digest()


def generate_mcp_api_key(surface: str) -> tuple[str, str, bytes, str]:
    """Generate a high-entropy surface-bound API key.

    Returns:
        (plaintext_token, key_prefix, key_sha256, display_hint)

    """
    if surface not in SURFACE_KEY_PREFIXES:
        msg = f"Unknown surface {surface!r}; allowed: {sorted(ALLOWED_SURFACES)}"
        raise ValueError(msg)

    prefix = SURFACE_KEY_PREFIXES[surface]
    raw_bytes = secrets.token_bytes(KEY_RANDOM_BYTES_COUNT)
    b64_payload = base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")
    token = f"{prefix}{b64_payload}"
    display_hint = token[-DISPLAY_HINT_LENGTH:]
    key_sha256 = hash_mcp_api_key(token)
    return token, prefix, key_sha256, display_hint


def derive_internal_mcp_auth_key() -> bytes:
    """Derive dedicated internal HMAC key for MCP gateway introspection."""
    km = load_key_material()
    return derive_subkey(km.master_kek, "mcp-internal-v1")


def create_internal_mcp_auth_header() -> str:
    """Generate timestamped internal HMAC authentication header for mcp-introspect calls."""
    key = derive_internal_mcp_auth_key()
    ts = int(time.time())
    msg = f"{ts}".encode("ascii")
    sig = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def verify_internal_mcp_auth_header(
    header_val: str | None, max_drift_s: int = INTERNAL_AUTH_DRIFT_SECONDS
) -> bool:
    """Verify internal HMAC authentication header."""
    if not header_val:
        return False

    key = derive_internal_mcp_auth_key()
    # Support t=<ts>,v1=<sig>
    if "t=" in header_val and "v1=" in header_val:
        parts = dict(
            part.strip().split("=", 1) for part in header_val.split(",") if "=" in part.strip()
        )
        ts_str = parts.get("t")
        sig = parts.get("v1")
        if not ts_str or not sig:
            return False
        try:
            ts = float(ts_str)
        except ValueError:
            return False

        if abs(time.time() - ts) > max_drift_s:
            return False

        expected_sig = hmac.new(key, f"{int(ts)}".encode("ascii"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig)

    # Fallback to direct signature comparison
    expected_direct = hmac.new(key, b"mcp-internal-v1", hashlib.sha256).hexdigest()
    return hmac.compare_digest(header_val, expected_direct)


async def mint_mcp_api_key(  # noqa: PLR0913
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    principal_id: uuid.UUID,
    surface: str,
    scopes: list[str],
    created_by_id: uuid.UUID,
    expires_at: datetime | None = None,
    expires_in_days: int | None = None,
) -> tuple[McpApiKey, str]:
    """Mint an MCP API key, enforce surface and role constraints, and persist digest."""
    if surface not in ALLOWED_SURFACES:
        raise ProblemException(
            code="INVALID_SURFACE",
            status=422,
            title="Invalid Surface",
            detail=f"Surface must be one of {sorted(ALLOWED_SURFACES)}.",
        )

    allowed_scopes = SURFACE_ALLOWED_SCOPES[surface]
    invalid_scopes = [s for s in scopes if s not in allowed_scopes]
    if invalid_scopes or not scopes:
        raise ProblemException(
            code="INVALID_SCOPE",
            status=422,
            title="Invalid Scope",
            detail=f"Scopes {invalid_scopes} not allowed for surface {surface!r}.",
        )

    # Check admin:destructive capability
    if "admin:destructive" in scopes:
        stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
        is_server_admin = (await session.execute(stmt)).scalar_one()
        if not is_server_admin:
            raise ProblemException(
                code="INSUFFICIENT_CAPABILITY",
                status=403,
                title="Insufficient Capability",
                detail="admin:destructive scope requires SERVER_ADMIN role.",
            )

    now = datetime.now(UTC)
    if expires_at is None:
        days = expires_in_days if expires_in_days is not None else 30
        effective_expires = now + timedelta(days=days)
    else:
        effective_expires = (
            expires_at if expires_at.tzinfo is not None else expires_at.replace(tzinfo=UTC)
        )

    if effective_expires <= now or effective_expires > (now + timedelta(days=MAX_KEY_TTL_DAYS)):
        raise ProblemException(
            code="INVALID_EXPIRATION",
            status=422,
            title="Invalid Expiration",
            detail=f"Key expiration must be in the future and within {MAX_KEY_TTL_DAYS} days.",
        )

    # Validate target principal
    principal = await session.get(Principal, principal_id)
    if principal is None or principal.workspace_id != workspace_id or principal.status != "ACTIVE":
        raise ProblemException(
            code="INVALID_PRINCIPAL",
            status=422,
            title="Invalid Principal",
            detail="Target principal must be an active principal in the current workspace.",
        )

    token, prefix, key_sha256, display_hint = generate_mcp_api_key(surface)

    key_record = McpApiKey(
        workspace_id=workspace_id,
        principal_id=principal_id,
        surface=surface,
        key_prefix=prefix,
        key_sha256=key_sha256,
        display_hint=display_hint,
        scopes=scopes,
        created_by_id=created_by_id,
        created_at=now,
        expires_at=effective_expires,
    )
    session.add(key_record)
    await session.flush()
    await session.refresh(key_record)

    # Emit MCP_KEY_MINTED activity
    await record_activity(
        session,
        workspace_id=workspace_id,
        object_id=None,
        actor_principal_id=created_by_id,
        event_type=ActivityEventType.MCP_KEY_MINTED,
        payload={
            "key_id": str(key_record.id),
            "principal_id": str(principal_id),
            "surface": surface,
            "display_hint": display_hint,
            "scopes": scopes,
            "expires_at": effective_expires.isoformat(),
        },
    )

    return key_record, token


async def revoke_mcp_api_key(
    session: AsyncSession,
    *,
    key_id: uuid.UUID,
    caller_principal_id: uuid.UUID,
) -> McpApiKey:
    """Revoke an MCP API key and record activity."""
    key = await session.get(McpApiKey, key_id)
    if key is None:
        not_found()

    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        await session.flush()

        await record_activity(
            session,
            workspace_id=key.workspace_id,
            object_id=None,
            actor_principal_id=caller_principal_id,
            event_type=ActivityEventType.MCP_KEY_REVOKED,
            payload={
                "key_id": str(key.id),
                "principal_id": str(key.principal_id),
                "surface": key.surface,
                "display_hint": key.display_hint,
                "revoked_by": str(caller_principal_id),
            },
        )

    return key


async def introspect_subject_token(  # noqa: C901, PLR0911, PLR0912, PLR0915
    session: AsyncSession,
    token: str,
    surface: str | None = None,
    consume_call: bool = False,  # noqa: FBT001, FBT002
    tool_name: str | None = None,
) -> McpIntrospectionResult:
    """Introspect bearer token digest against database and verify active state."""
    if token.startswith("kb_agt_eph_"):
        from kanban.security.ephemeral_mcp_tokens import (  # noqa: PLC0415
            introspect_and_consume_ephemeral_token,
        )

        return await introspect_and_consume_ephemeral_token(
            session=session,
            token=token,
            surface=surface,
            consume_call=consume_call,
            tool_name=tool_name,
        )

    if token.startswith("eyJ"):
        # JWT OAuth 2.1 access token path
        from kanban.oauth.jwt import OAuthTokenError, verify_access_token  # noqa: PLC0415

        try:
            claims = verify_access_token(token)
        except OAuthTokenError as exc:
            if exc.code == "SURFACE_KEY_MISMATCH":
                return McpIntrospectionResult(active=False, reason="SURFACE_KEY_MISMATCH")
            return McpIntrospectionResult(active=False)

        # Check surface match
        token_surface = claims.get("surface")
        token_aud = str(claims.get("aud", ""))
        if surface is not None and (
            token_surface != surface or not token_aud.endswith(f"/mcp/{surface}")
        ):
            return McpIntrospectionResult(active=False, reason="SURFACE_KEY_MISMATCH")

        # Check JTI revocation, Grant revocation, and Principal status via
        # SECURITY DEFINER helper check_oauth_token_status
        jti_str = claims.get("jti")
        jti_uuid: uuid.UUID | None = None
        if jti_str:
            with contextlib.suppress(ValueError):
                jti_uuid = uuid.UUID(jti_str)

        grant_id_str = claims.get("grant_id")
        grant_uuid: uuid.UUID | None = None
        if grant_id_str:
            with contextlib.suppress(ValueError):
                grant_uuid = uuid.UUID(grant_id_str)

        principal_id_str = claims.get("sub")
        if not principal_id_str:
            return McpIntrospectionResult(active=False)
        try:
            principal_uuid = uuid.UUID(principal_id_str)
        except ValueError:
            return McpIntrospectionResult(active=False)

        stmt_status = text(
            "SELECT grant_revoked, jti_revoked, principal_active "
            "FROM check_oauth_token_status(:gid, :jti, :pid)"
        )
        status_row = (
            await session.execute(
                stmt_status,
                {"gid": grant_uuid, "jti": jti_uuid, "pid": principal_uuid},
            )
        ).first()

        if status_row is None:
            return McpIntrospectionResult(active=False)

        grant_revoked, jti_revoked, principal_active = (
            bool(status_row[0]),
            bool(status_row[1]),
            bool(status_row[2]),
        )
        if grant_revoked or jti_revoked or not principal_active:
            return McpIntrospectionResult(active=False)

        ws_id_str = claims.get("ws")
        if not ws_id_str:
            return McpIntrospectionResult(active=False)
        try:
            ws_uuid = uuid.UUID(ws_id_str)
        except ValueError:
            return McpIntrospectionResult(active=False)

        scope_str = claims.get("scope", "")
        scopes_list = scope_str.split() if scope_str else []

        allowed_projects_raw = claims.get("allowed_projects")
        allowed_projects: list[uuid.UUID] | None = None
        if allowed_projects_raw and isinstance(allowed_projects_raw, list):
            with contextlib.suppress(ValueError):
                allowed_projects = [uuid.UUID(str(p)) for p in allowed_projects_raw]

        return McpIntrospectionResult(
            active=True,
            principal_id=principal_uuid,
            workspace_id=ws_uuid,
            surface=token_surface or surface,
            scopes=scopes_list,
            token_kind="oauth",  # noqa: S106
            allowed_projects=allowed_projects,
        )

    digest = hash_mcp_api_key(token)

    expected_prefix = SURFACE_KEY_PREFIXES.get(surface) if surface else None
    prefix_mismatch = expected_prefix is not None and not token.startswith(expected_prefix)

    stmt = text(
        "SELECT id, workspace_id, principal_id, surface, key_prefix, "
        "scopes, created_at, expires_at, revoked_at, last_used_at, principal_status "
        "FROM introspect_mcp_api_key(:digest)"
    )
    result = await session.execute(stmt, {"digest": digest})
    row = result.first()

    if row is None:
        # Unknown digest
        if prefix_mismatch:
            return McpIntrospectionResult(active=False, reason="SURFACE_KEY_MISMATCH")
        return McpIntrospectionResult(active=False)

    (
        _key_id,
        workspace_id,
        principal_id,
        key_surface,
        key_prefix,
        key_scopes,
        _created_at,
        expires_at,
        revoked_at,
        _last_used_at,
        principal_status,
    ) = row

    if revoked_at is not None:
        return McpIntrospectionResult(active=False)

    now = datetime.now(UTC)
    if expires_at <= now:
        return McpIntrospectionResult(active=False)

    if principal_status != "ACTIVE":
        return McpIntrospectionResult(active=False)

    # Surface mismatch checks
    if surface is not None and key_surface != surface:
        return McpIntrospectionResult(active=False, reason="SURFACE_KEY_MISMATCH")

    # Anti-forgery check: token prefix must match key_prefix
    if not token.startswith(key_prefix) or prefix_mismatch:
        return McpIntrospectionResult(active=False, reason="SURFACE_KEY_MISMATCH")

    return McpIntrospectionResult(
        active=True,
        principal_id=principal_id,
        workspace_id=workspace_id,
        surface=key_surface,
        scopes=list(key_scopes),
        token_kind="api_key",  # noqa: S106
    )
