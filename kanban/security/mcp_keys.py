# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Scoped kb_* API keys, hierarchical scoping, narrowing and token introspection.

Implementation for KB-P4-02a and KB-P4-14.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import ipaddress
import secrets
import time
import uuid  # Runtime import required for Pydantic / dataclass type annotations
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Literal

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database.models.mcp_api_key import McpApiKey
from database.models.principals import Principal
from kanban.api.problems import ProblemException, not_found
from kanban.api.request_id import (
    notify_mcp_key_revoked,
    register_mcp_key_revocation_listener,
)
from kanban.security.keys import derive_subkey, load_key_material
from kanban.security.permissions import Capability
from kanban.services.activity import ActivityEventType, record_activity
from kanban.settings import get_settings

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
    "evaluate_key_boundary",
    "generate_mcp_api_key",
    "hash_mcp_api_key",
    "introspect_subject_token",
    "mint_mcp_api_key",
    "notify_mcp_key_revoked",
    "register_mcp_key_revocation_listener",
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
REQUIRED_SERVICE_BOT_AAL: Final[int] = 2
MAX_CAPABILITY_MASK: Final[int] = 255
KEY_RANDOM_BYTES_COUNT: Final[int] = 32
KEY_TOKEN_TOTAL_LENGTH: Final[int] = 50  # 7-char prefix + 43-char unpadded base64url
DISPLAY_HINT_LENGTH: Final[int] = 4
INTERNAL_AUTH_DRIFT_SECONDS: Final[int] = 300


@dataclass(frozen=True, slots=True)
class McpIntrospectionResult:
    """Introspection payload returned to MCP protocol handlers and gateways."""

    active: bool
    key_id: uuid.UUID | None = None
    principal_id: uuid.UUID | None = None
    agent_principal_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    workspace_slug: str | None = None
    project_id: uuid.UUID | None = None
    execution_id: uuid.UUID | None = None
    surface: str | None = None
    scopes: list[str] | None = None
    token_kind: str | None = "api_key"  # noqa: S105
    reason: str | None = None
    allowed_projects: list[uuid.UUID] | None = None
    allowed_project_keys: list[str] | None = None
    allowed_tools: list[str] | None = None
    disabled_tools: list[str] | None = None
    calls_used: int | None = None
    max_calls: int | None = None
    expires_at: datetime | str | None = None
    scope_tier: str | None = None
    owner_kind: str | None = None
    allowed_workspace_ids: list[uuid.UUID] | None = None
    allowed_project_ids: list[uuid.UUID] | None = None
    capability_mask: int | None = None
    allowed_cidrs: list[str] | None = None
    credential_boundary: Any | None = None

    def to_dict(self) -> dict[str, Any]:  # noqa: C901, PLR0912
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
            "principal_id": str(self.principal_id) if self.principal_id else None,
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "surface": self.surface,
            "scopes": self.scopes or [],
            "token_kind": self.token_kind,
        }
        if self.workspace_slug is not None:
            payload["workspace_slug"] = self.workspace_slug
        if self.key_id is not None:
            payload["key_id"] = str(self.key_id)
            payload["id"] = str(self.key_id)
        if self.agent_principal_id is not None:
            payload["agent_principal_id"] = str(self.agent_principal_id)
        if self.project_id is not None:
            payload["project_id"] = str(self.project_id)
        if self.execution_id is not None:
            payload["execution_id"] = str(self.execution_id)
        if self.scope_tier is not None:
            payload["scope_tier"] = self.scope_tier
        if self.owner_kind is not None:
            payload["owner_kind"] = self.owner_kind
        if self.allowed_workspace_ids is not None:
            payload["allowed_workspace_ids"] = [str(w) for w in self.allowed_workspace_ids]
        if self.allowed_project_ids is not None:
            payload["allowed_project_ids"] = [str(p) for p in self.allowed_project_ids]
        if self.allowed_projects is not None:
            payload["allowed_projects"] = [str(p) for p in self.allowed_projects]
        if self.allowed_project_keys is not None:
            payload["allowed_project_keys"] = self.allowed_project_keys
        if self.capability_mask is not None:
            payload["capability_mask"] = self.capability_mask
        if self.allowed_tools is not None:
            payload["allowed_tools"] = self.allowed_tools
        if self.disabled_tools is not None:
            payload["disabled_tools"] = self.disabled_tools
        if self.allowed_cidrs is not None:
            payload["allowed_cidrs"] = self.allowed_cidrs
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


async def mint_mcp_api_key(  # noqa: C901, PLR0912, PLR0913, PLR0915
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID | None = None,
    principal_id: uuid.UUID,
    surface: str,
    scopes: list[str],
    created_by_id: uuid.UUID,
    expires_at: datetime | None = None,
    expires_in_days: int | None = None,
    scope_tier: Literal["global", "workspace", "project", "server"] = "workspace",
    owner_kind: Literal["personal_user", "service_bot"] = "service_bot",
    project_id: uuid.UUID | None = None,
    allowed_workspace_ids: list[uuid.UUID] | None = None,
    allowed_project_ids: list[uuid.UUID] | None = None,
    capability_mask: int = 7,
    allowed_tools: list[str] | None = None,
    disabled_tools: list[str] | None = None,
    allowed_cidrs: list[str] | None = None,
    unlimited: bool = False,
    confirm_unlimited: bool = False,
    caller_aal_level: int | None = None,
    label: str | None = None,
) -> tuple[McpApiKey, str]:
    """Mint an MCP API key, enforce surface, tier, and role constraints, and persist digest."""
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

    # Normalize scope_tier alias ("server" -> "global")
    if scope_tier == "server":
        scope_tier = "global"

    # Resolve effective AAL level early for privilege and scope checks
    if caller_aal_level is None:
        try:
            stmt_aal = text("SELECT NULLIF(current_setting('app.aal_level', true), '')::integer")
            sess_aal = (await session.execute(stmt_aal)).scalar_one_or_none()
            effective_aal = sess_aal if sess_aal is not None else REQUIRED_SERVICE_BOT_AAL
        except SQLAlchemyError:
            effective_aal = REQUIRED_SERVICE_BOT_AAL
    else:
        effective_aal = caller_aal_level

    # Check admin:destructive capability (strictly requires SERVER_ADMIN + fresh AAL2)
    if "admin:destructive" in scopes:
        if effective_aal < REQUIRED_SERVICE_BOT_AAL:
            raise ProblemException(
                code="AAL2_REQUIRED",
                status=403,
                title="AAL2 Required",
                detail="admin:destructive scope requires fresh AAL2 authentication.",
            )
        stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
        is_server_admin = (await session.execute(stmt)).scalar_one()
        if not is_server_admin:
            raise ProblemException(
                code="INSUFFICIENT_CAPABILITY",
                status=403,
                title="Insufficient Capability",
                detail="admin:destructive scope requires SERVER_ADMIN role.",
            )

    # 1. Tier and shape validation
    if scope_tier not in ("global", "workspace", "project"):
        raise ProblemException(
            code="INVALID_SCOPE_TIER",
            status=422,
            title="Invalid Scope Tier",
            detail="scope_tier must be one of ('global', 'workspace', 'project').",
        )

    if scope_tier == "global":
        if workspace_id is not None or project_id is not None:
            raise ProblemException(
                code="INVALID_TIER_SHAPE",
                status=422,
                title="Invalid Tier Shape",
                detail="Global keys must have workspace_id=None and project_id=None.",
            )
    elif scope_tier == "workspace":
        if workspace_id is None or project_id is not None:
            raise ProblemException(
                code="INVALID_TIER_SHAPE",
                status=422,
                title="Invalid Tier Shape",
                detail="Workspace keys must have workspace_id set and project_id=None.",
            )
    elif scope_tier == "project":
        if workspace_id is None or project_id is None:
            raise ProblemException(
                code="INVALID_TIER_SHAPE",
                status=422,
                title="Invalid Tier Shape",
                detail="Project keys must have both workspace_id and project_id set.",
            )
        if allowed_project_ids is None or not allowed_project_ids:
            allowed_project_ids = [project_id]
        elif project_id not in allowed_project_ids:
            allowed_project_ids = [*allowed_project_ids, project_id]

    # 2. Authorization and Privilege Checks
    if owner_kind == "service_bot":
        if effective_aal < REQUIRED_SERVICE_BOT_AAL:
            raise ProblemException(
                code="AAL2_REQUIRED",
                status=403,
                title="AAL2 Required",
                detail="Minting service bot keys requires AAL2 authentication.",
            )
        if scope_tier == "global":
            stmt_sa = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
            if not bool((await session.execute(stmt_sa)).scalar_one()):
                raise ProblemException(
                    code="INSUFFICIENT_CAPABILITY",
                    status=403,
                    title="Insufficient Capability",
                    detail="Minting global service bot keys requires SERVER_ADMIN role.",
                )
        elif scope_tier == "workspace":
            stmt_wa = text(
                "SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])"
            )
            if not bool((await session.execute(stmt_wa)).scalar_one()):
                raise ProblemException(
                    code="INSUFFICIENT_CAPABILITY",
                    status=403,
                    title="Insufficient Capability",
                    detail=(
                        "Minting workspace service bot keys requires "
                        "WORKSPACE_ADMIN or SERVER_ADMIN role."
                    ),
                )
        elif scope_tier == "project":
            stmt_pa = text(
                "SELECT app_principal_has_role("
                ":p_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])"
            )
            if not bool((await session.execute(stmt_pa, {"p_id": project_id})).scalar_one()):
                raise ProblemException(
                    code="INSUFFICIENT_CAPABILITY",
                    status=403,
                    title="Insufficient Capability",
                    detail=(
                        "Minting project service bot keys requires "
                        "PROJECT_ADMIN, WORKSPACE_ADMIN, or SERVER_ADMIN role."
                    ),
                )
    elif owner_kind == "personal_user":
        if principal_id != created_by_id:
            raise ProblemException(
                code="CANNOT_MINT_FOR_OTHER_USER",
                status=403,
                title="Forbidden",
                detail="Personal user keys cannot be minted for another user.",
            )
        # Check delete capability bitmask (Capability.DELETE is 128 / bit 7, not 8 / TRANSITION)
        has_delete_cap = bool(capability_mask & int(Capability.DELETE.value))
        if (surface == "admin" or has_delete_cap) and effective_aal < REQUIRED_SERVICE_BOT_AAL:
            raise ProblemException(
                code="AAL2_REQUIRED",
                status=403,
                title="AAL2 Required",
                detail="Minting admin surface or delete capability personal keys requires AAL2.",
            )
        # Surface == "admin" requires tier-matched admin role + AAL2
        if surface == "admin":
            if scope_tier == "global":
                stmt_sa = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
                if not bool((await session.execute(stmt_sa)).scalar_one()):
                    raise ProblemException(
                        code="INSUFFICIENT_CAPABILITY",
                        status=403,
                        title="Insufficient Capability",
                        detail="Minting admin surface global keys requires SERVER_ADMIN role.",
                    )
            elif scope_tier == "workspace":
                stmt_wa = text(
                    "SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])"
                )
                if not bool((await session.execute(stmt_wa)).scalar_one()):
                    raise ProblemException(
                        code="INSUFFICIENT_CAPABILITY",
                        status=403,
                        title="Insufficient Capability",
                        detail=(
                            "Minting admin surface workspace keys requires "
                            "WORKSPACE_ADMIN or SERVER_ADMIN role."
                        ),
                    )
            elif scope_tier == "project":
                stmt_pa = text(
                    "SELECT app_principal_has_role("
                    ":p_id, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])"
                )
                if not bool((await session.execute(stmt_pa, {"p_id": project_id})).scalar_one()):
                    raise ProblemException(
                        code="INSUFFICIENT_CAPABILITY",
                        status=403,
                        title="Insufficient Capability",
                        detail=(
                            "Minting admin surface project keys requires "
                            "PROJECT_ADMIN, WORKSPACE_ADMIN, or SERVER_ADMIN role."
                        ),
                    )

        # Global tier privilege escalation guard: personal user global keys
        # strictly require SERVER_ADMIN + fresh AAL2
        if scope_tier == "global":
            if effective_aal < REQUIRED_SERVICE_BOT_AAL:
                raise ProblemException(
                    code="AAL2_REQUIRED",
                    status=403,
                    title="AAL2 Required",
                    detail="Minting global personal keys requires fresh AAL2 authentication.",
                )
            stmt_sa = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
            if not bool((await session.execute(stmt_sa)).scalar_one()):
                raise ProblemException(
                    code="INSUFFICIENT_CAPABILITY",
                    status=403,
                    title="Insufficient Capability",
                    detail="Minting global personal user keys requires SERVER_ADMIN role.",
                )
        elif scope_tier == "workspace":
            stmt_ws_view = text(
                "SELECT app_has_object_capability(:ws_id, 1) OR "
                "app_principal_has_role(NULL, "
                "ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'WORKSPACE_MEMBER', "
                "'WORKSPACE_GUEST', 'MEMBER', 'VIEWER'])"
            )
            can_view = bool(
                (await session.execute(stmt_ws_view, {"ws_id": workspace_id})).scalar_one()
            )
            if not can_view:
                raise ProblemException(
                    code="INSUFFICIENT_CAPABILITY",
                    status=403,
                    title="Insufficient Capability",
                    detail="User lacks VIEW permission in target workspace.",
                )
        elif scope_tier == "project":
            stmt_proj_view = text(
                "SELECT app_has_object_capability(:p_id, 1) OR "
                "app_principal_has_role(:p_id, "
                "ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN', "
                "'WORKSPACE_MEMBER', 'MEMBER', 'VIEWER'])"
            )
            can_view = bool(
                (await session.execute(stmt_proj_view, {"p_id": project_id})).scalar_one()
            )
            if not can_view:
                raise ProblemException(
                    code="INSUFFICIENT_CAPABILITY",
                    status=403,
                    title="Insufficient Capability",
                    detail="User lacks VIEW permission on target project.",
                )

    # 3. CIDR Validation
    if allowed_cidrs:
        for c in allowed_cidrs:
            try:
                ipaddress.ip_network(c, strict=False)
            except ValueError as exc:
                raise ProblemException(
                    code="INVALID_CIDR",
                    status=422,
                    title="Invalid CIDR",
                    detail=f"Invalid CIDR string: {c}",
                ) from exc

    # 4. Capability Mask Validation
    if not (1 <= capability_mask <= MAX_CAPABILITY_MASK):
        raise ProblemException(
            code="INVALID_CAPABILITY_MASK",
            status=422,
            title="Invalid Capability Mask",
            detail="capability_mask must be between 1 and 255.",
        )

    # 5. Expiration & Unlimited Keys Validation
    now = datetime.now(UTC)
    effective_expires: datetime | None = None
    if unlimited:
        settings = get_settings()
        if settings.disable_unlimited_mcp_keys:
            raise ProblemException(
                code="UNLIMITED_KEY_FORBIDDEN",
                status=422,
                title="Unlimited Key Forbidden",
                detail="Unlimited MCP API keys are forbidden on this instance.",
            )
        if not confirm_unlimited:
            raise ProblemException(
                code="UNLIMITED_CONFIRMATION_REQUIRED",
                status=422,
                title="Confirmation Required",
                detail="Explicit confirmation required to mint an unlimited MCP API key.",
            )
        effective_expires = None
    else:
        if expires_at is None:
            days = expires_in_days if expires_in_days is not None else 30
            effective_expires = now + timedelta(days=days)
        else:
            effective_expires = (
                expires_at if expires_at.tzinfo is not None else expires_at.replace(tzinfo=UTC)
            )

        max_ttl_days = MAX_KEY_TTL_DAYS
        if workspace_id is not None:
            stmt_ttl = text(
                "SELECT mcp_key_max_ttl_days FROM workspace_settings WHERE workspace_id = :ws_id"
            )
            ws_ttl = (await session.execute(stmt_ttl, {"ws_id": workspace_id})).scalar_one_or_none()
            if ws_ttl is not None:
                max_ttl_days = ws_ttl

        if effective_expires <= now or effective_expires > (now + timedelta(days=max_ttl_days)):
            raise ProblemException(
                code="INVALID_EXPIRATION",
                status=422,
                title="Invalid Expiration",
                detail=f"Key expiration must be in the future and within {max_ttl_days} days.",
            )

    # 6. Target Principal Validation
    principal = await session.get(Principal, principal_id)
    if principal is None or principal.status != "ACTIVE":
        raise ProblemException(
            code="INVALID_PRINCIPAL",
            status=422,
            title="Invalid Principal",
            detail="Target principal must be an active principal.",
        )
    if scope_tier in ("workspace", "project") and principal.workspace_id != workspace_id:
        raise ProblemException(
            code="INVALID_PRINCIPAL",
            status=422,
            title="Invalid Principal",
            detail="Target principal must belong to the workspace.",
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
        scope_tier=scope_tier,
        owner_kind=owner_kind,
        project_id=project_id,
        allowed_workspace_ids=allowed_workspace_ids,
        allowed_project_ids=allowed_project_ids,
        capability_mask=capability_mask,
        allowed_tools=allowed_tools,
        disabled_tools=disabled_tools or [],
        allowed_cidrs=allowed_cidrs,
        created_by_id=created_by_id,
        created_at=now,
        expires_at=effective_expires,
        label=label,
    )
    session.add(key_record)
    await session.flush()
    await session.refresh(key_record)

    # Emit MCP_KEY_MINTED activity
    ws_target = workspace_id or principal.workspace_id
    if ws_target is not None:
        await record_activity(
            session,
            workspace_id=ws_target,
            object_id=None,
            actor_principal_id=created_by_id,
            event_type=ActivityEventType.MCP_KEY_MINTED,
            payload={
                "key_id": str(key_record.id),
                "principal_id": str(principal_id),
                "surface": surface,
                "display_hint": display_hint,
                "scopes": scopes,
                "scope_tier": scope_tier,
                "owner_kind": owner_kind,
                "project_id": str(project_id) if project_id else None,
                "expires_at": effective_expires.isoformat() if effective_expires else None,
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

        notify_mcp_key_revoked(key.id)

        ws_target = key.workspace_id
        if ws_target is None and key.principal_id is not None:
            principal = await session.get(Principal, key.principal_id)
            if principal is not None:
                ws_target = principal.workspace_id

        if ws_target is not None:
            await record_activity(
                session,
                workspace_id=ws_target,
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
    if token.startswith(("kb_agt_eph_", "kb_eat_")):
        from kanban.security.ephemeral_mcp_tokens import (  # noqa: PLC0415
            introspect_and_consume_ephemeral_token,
        )

        eph_res = await introspect_and_consume_ephemeral_token(
            session=session,
            token=token,
            surface=surface,
            consume_call=consume_call,
            tool_name=tool_name,
        )
        if eph_res.active and eph_res.credential_boundary is None:
            from kanban.security.boundary import CredentialBoundary  # noqa: PLC0415

            object.__setattr__(
                eph_res, "credential_boundary", CredentialBoundary.from_introspection(eph_res)
            )
        return eph_res

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
        from kanban.oauth.server import parse_surface_from_resource  # noqa: PLC0415

        aud_surface = None
        with contextlib.suppress(Exception):
            aud_surface = parse_surface_from_resource(token_aud)

        if surface is not None and (token_surface != surface or aud_surface != surface):
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

        ws_slug_res = (
            await session.execute(
                text("SELECT resolve_workspace_slug(:ws_id)"),
                {"ws_id": ws_uuid},
            )
        ).scalar_one_or_none()
        ws_slug: str | None = str(ws_slug_res) if ws_slug_res else None

        oauth_proj_keys: list[str] = []
        if allowed_projects:
            keys_res = (
                await session.execute(
                    text("SELECT resolve_project_keys(:p_ids)"),
                    {"p_ids": allowed_projects},
                )
            ).scalar_one_or_none()
            if keys_res:
                oauth_proj_keys = [str(pk) for pk in keys_res]

        oauth_res = McpIntrospectionResult(
            active=True,
            principal_id=principal_uuid,
            workspace_id=ws_uuid,
            workspace_slug=ws_slug,
            surface=token_surface or surface,
            scopes=scopes_list,
            token_kind="oauth",  # noqa: S106
            allowed_projects=allowed_projects,
            allowed_project_ids=allowed_projects,
            allowed_project_keys=oauth_proj_keys or None,
        )
        from kanban.security.boundary import CredentialBoundary  # noqa: PLC0415

        object.__setattr__(
            oauth_res, "credential_boundary", CredentialBoundary.from_introspection(oauth_res)
        )
        return oauth_res

    digest = hash_mcp_api_key(token)

    expected_prefix = SURFACE_KEY_PREFIXES.get(surface) if surface else None
    prefix_mismatch = expected_prefix is not None and not token.startswith(expected_prefix)

    stmt = text(
        "SELECT id, workspace_id, principal_id, surface, key_prefix, "
        "scopes, created_at, expires_at, revoked_at, last_used_at, principal_status, "
        "scope_tier, owner_kind, project_id, allowed_workspace_ids, allowed_project_ids, "
        "capability_mask, allowed_tools, disabled_tools, allowed_cidrs, "
        "workspace_slug, project_key "
        "FROM introspect_mcp_api_key(:digest)"
    )
    row = None
    has_slug_cols = True
    try:
        async with session.begin_nested():
            result = await session.execute(stmt, {"digest": digest})
            row = result.first()
    except Exception:  # noqa: BLE001
        has_slug_cols = False
        stmt_legacy = text(
            "SELECT id, workspace_id, principal_id, surface, key_prefix, "
            "scopes, created_at, expires_at, revoked_at, last_used_at, principal_status, "
            "scope_tier, owner_kind, project_id, allowed_workspace_ids, allowed_project_ids, "
            "capability_mask, allowed_tools, disabled_tools, allowed_cidrs "
            "FROM introspect_mcp_api_key(:digest)"
        )
        result = await session.execute(stmt_legacy, {"digest": digest})
        row = result.first()

    if row is None:
        # Unknown digest
        if prefix_mismatch:
            return McpIntrospectionResult(active=False, reason="SURFACE_KEY_MISMATCH")
        return McpIntrospectionResult(active=False)

    if has_slug_cols:
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
            scope_tier,
            owner_kind,
            project_id,
            allowed_workspace_ids,
            allowed_project_ids,
            capability_mask,
            allowed_tools,
            disabled_tools,
            allowed_cidrs,
            workspace_slug,
            project_key,
        ) = row
    else:
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
            scope_tier,
            owner_kind,
            project_id,
            allowed_workspace_ids,
            allowed_project_ids,
            capability_mask,
            allowed_tools,
            disabled_tools,
            allowed_cidrs,
        ) = row
        workspace_slug = None
        project_key = None

    if revoked_at is not None:
        return McpIntrospectionResult(active=False)

    now = datetime.now(UTC)
    if expires_at is not None and expires_at <= now:
        return McpIntrospectionResult(active=False)

    if principal_status != "ACTIVE":
        return McpIntrospectionResult(active=False)

    # Surface mismatch checks
    if surface is not None and key_surface != surface:
        return McpIntrospectionResult(active=False, reason="SURFACE_KEY_MISMATCH")

    # Anti-forgery check: token prefix must match key_prefix
    if not token.startswith(key_prefix) or prefix_mismatch:
        return McpIntrospectionResult(active=False, reason="SURFACE_KEY_MISMATCH")

    resolved_proj_keys: list[str] = []
    if project_key:
        resolved_proj_keys.append(str(project_key))
    if allowed_project_ids and has_slug_cols:
        with contextlib.suppress(Exception):
            async with session.begin_nested():
                keys_res = (
                    await session.execute(
                        text("SELECT resolve_project_keys(:p_ids)"),
                        {"p_ids": list(allowed_project_ids)},
                    )
                ).scalar_one_or_none()
                if keys_res:
                    for k in keys_res:
                        if str(k) not in resolved_proj_keys:
                            resolved_proj_keys.append(str(k))

    from kanban.security.boundary import CredentialBoundary  # noqa: PLC0415

    raw_tier = scope_tier if scope_tier in ("global", "workspace", "project") else "workspace"
    raw_surf = key_surface if key_surface in ("agent", "docs", "admin") else "agent"
    ws_set = set(allowed_workspace_ids or [])
    if workspace_id and raw_tier in ("workspace", "project"):
        ws_set.add(workspace_id)
    proj_set = set(allowed_project_ids or [])
    if project_id:
        proj_set.add(project_id)

    boundary = CredentialBoundary(
        scope_tier=raw_tier,
        surface=raw_surf,
        workspace_allowlist=frozenset(ws_set),
        project_allowlist=frozenset(proj_set),
        capability_mask=capability_mask if capability_mask is not None else 7,
        allowed_tools=frozenset(allowed_tools) if allowed_tools is not None else None,
        allowed_cidrs=tuple(str(c) for c in (allowed_cidrs or ())),
        has_aal2_provenance=(raw_surf == "admin"),
    )

    return McpIntrospectionResult(
        active=True,
        key_id=_key_id,
        principal_id=principal_id,
        workspace_id=workspace_id,
        workspace_slug=workspace_slug,
        surface=key_surface,
        scopes=list(key_scopes),
        token_kind="api_key",  # noqa: S106
        scope_tier=scope_tier,
        owner_kind=owner_kind,
        project_id=project_id,
        allowed_workspace_ids=list(allowed_workspace_ids) if allowed_workspace_ids else None,
        allowed_project_ids=list(allowed_project_ids) if allowed_project_ids else None,
        allowed_projects=list(allowed_project_ids) if allowed_project_ids else None,
        allowed_project_keys=resolved_proj_keys or None,
        capability_mask=capability_mask if capability_mask is not None else 7,
        allowed_tools=list(allowed_tools) if allowed_tools is not None else None,
        disabled_tools=list(disabled_tools) if disabled_tools is not None else [],
        allowed_cidrs=[str(c) for c in allowed_cidrs] if allowed_cidrs else None,
        expires_at=expires_at,
        credential_boundary=boundary,
    )


def evaluate_key_boundary(  # noqa: C901, PLR0912, PLR0913
    key: McpApiKey | McpIntrospectionResult,
    *,
    target_workspace_id: uuid.UUID | None = None,
    target_project_id: uuid.UUID | None = None,
    client_ip: str | None = None,
    tool_name: str | None = None,
    required_capability: int | None = None,
) -> None:
    """Evaluate key boundary constraints: CIDR, scope tier, tools, and capability mask."""
    # 1. CIDR Pin Check
    allowed_cidrs = getattr(key, "allowed_cidrs", None)
    if allowed_cidrs and client_ip:
        ip = ipaddress.ip_address(client_ip)
        matched = any(ip in ipaddress.ip_network(str(c), strict=False) for c in allowed_cidrs)
        if not matched:
            raise ProblemException(
                code="KEY_CIDR_DENIED",
                status=403,
                title="CIDR Denied",
                detail=f"Client IP '{client_ip}' is outside allowed CIDRs.",
            )

    # 2. Scope Tier & Hierarchy Boundary Check
    scope_tier = getattr(key, "scope_tier", "workspace")
    key_ws = getattr(key, "workspace_id", None)
    key_proj = getattr(key, "project_id", None)
    allowed_ws = getattr(key, "allowed_workspace_ids", None)
    allowed_projs = getattr(key, "allowed_project_ids", None) or getattr(
        key, "allowed_projects", None
    )

    if scope_tier == "global":
        if target_workspace_id is not None and allowed_ws:
            ws_matches = target_workspace_id in allowed_ws or str(target_workspace_id) in [
                str(w) for w in allowed_ws
            ]
            if not ws_matches:
                raise ProblemException(
                    code="KEY_SCOPE_VIOLATION",
                    status=403,
                    title="Key Scope Violation",
                    detail=f"Workspace '{target_workspace_id}' is outside allowed workspaces.",
                )
        if target_project_id is not None and allowed_projs:
            proj_matches = target_project_id in allowed_projs or str(target_project_id) in [
                str(p) for p in allowed_projs
            ]
            if not proj_matches:
                raise ProblemException(
                    code="KEY_SCOPE_VIOLATION",
                    status=403,
                    title="Key Scope Violation",
                    detail=f"Project '{target_project_id}' is outside allowed projects.",
                )
    elif scope_tier == "workspace":
        if (
            target_workspace_id is not None
            and key_ws is not None
            and str(target_workspace_id) != str(key_ws)
        ):
            raise ProblemException(
                code="KEY_SCOPE_VIOLATION",
                status=403,
                title="Key Scope Violation",
                detail=f"Workspace '{target_workspace_id}' is outside key workspace '{key_ws}'.",
            )
        if target_project_id is not None and allowed_projs:
            proj_matches = target_project_id in allowed_projs or str(target_project_id) in [
                str(p) for p in allowed_projs
            ]
            if not proj_matches:
                raise ProblemException(
                    code="KEY_SCOPE_VIOLATION",
                    status=403,
                    title="Key Scope Violation",
                    detail=f"Project '{target_project_id}' is outside allowed projects.",
                )
    elif scope_tier == "project":
        if (
            target_workspace_id is not None
            and key_ws is not None
            and str(target_workspace_id) != str(key_ws)
        ):
            raise ProblemException(
                code="KEY_SCOPE_VIOLATION",
                status=403,
                title="Key Scope Violation",
                detail=f"Workspace '{target_workspace_id}' is outside key workspace '{key_ws}'.",
            )
        if (
            target_project_id is not None
            and key_proj is not None
            and str(target_project_id) != str(key_proj)
        ):
            raise ProblemException(
                code="KEY_SCOPE_VIOLATION",
                status=403,
                title="Key Scope Violation",
                detail=f"Project '{target_project_id}' is outside key project '{key_proj}'.",
            )

    # 3. Tool Narrowing Check
    if tool_name:
        disabled_tools = getattr(key, "disabled_tools", None) or []
        if tool_name in disabled_tools:
            raise ProblemException(
                code="INSUFFICIENT_SCOPE",
                status=403,
                title="Insufficient Scope",
                detail=f"Tool '{tool_name}' is disabled for this key.",
            )
        allowed_tools = getattr(key, "allowed_tools", None)
        if allowed_tools is not None and tool_name not in allowed_tools:
            raise ProblemException(
                code="INSUFFICIENT_SCOPE",
                status=403,
                title="Insufficient Scope",
                detail=f"Tool '{tool_name}' is not in allowed_tools for this key.",
            )

    # 4. Capability Mask Check
    if required_capability is not None:
        mask = getattr(key, "capability_mask", 7)
        if mask is None:
            mask = 7
        if (mask & required_capability) != required_capability:
            raise ProblemException(
                code="INSUFFICIENT_CAPABILITY",
                status=403,
                title="Insufficient Capability",
                detail=f"Key capability mask {mask} lacks required bit {required_capability}.",
            )
