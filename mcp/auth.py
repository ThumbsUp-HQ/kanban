# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""MCP authentication middleware, surface prefix validation, and tool scoping (KB-P4-02a)."""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from starlette.datastructures import Headers
from starlette.responses import JSONResponse, Response

from kanban.api.request_id import (
    format_log_actor,
    register_mcp_key_revocation_listener,
    reset_log_user,
    set_log_user,
)
from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface
from mcp.settings import McpSettings

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from starlette.types import ASGIApp, Receive, Scope, Send

    from mcp.internal_client import KanbanApiClient
    from mcp.scoping import ConnectionScope

__all__ = [
    "DEFAULT_CACHE_TTL_S",
    "MAX_CACHE_ENTRIES",
    "RESERVED_EPHEMERAL_PREFIX",
    "SCOPE_REQUIREMENTS",
    "SURFACE_PREFIXES",
    "IntrospectionCache",
    "McpAuthContext",
    "McpAuthMiddleware",
    "hash_mcp_api_key",
    "set_tool_scope_requirements",
]

_logger: Final[logging.Logger] = logging.getLogger(__name__)

SURFACE_PREFIXES: Final[dict[Surface, str]] = {
    Surface.AGENT: "kb_agt_",
    Surface.DOCS: "kb_doc_",
    Surface.ADMIN: "kb_adm_",
}

RESERVED_EPHEMERAL_PREFIX: Final[str] = "kb_agt_eph_"

DEFAULT_CACHE_TTL_S: Final[float] = 15.0
MAX_CACHE_ENTRIES: Final[int] = 5000

SCOPE_REQUIREMENTS: Final[dict[str, frozenset[str]]] = {
    # Agent surface tools
    "ping_agent": frozenset({"agent:read"}),
    "search_tickets": frozenset({"agent:read"}),
    "read_ticket": frozenset({"agent:read"}),
    "create_ticket": frozenset({"agent:write"}),
    "update_ticket": frozenset({"agent:write"}),
    "begin_work": frozenset({"agent:write"}),
    "transition_ticket": frozenset({"agent:write"}),
    "complete_work": frozenset({"agent:write"}),
    "add_comment": frozenset({"agent:write"}),
    "link_objects": frozenset({"agent:write"}),
    "test_agent_write": frozenset({"agent:write"}),
    # Docs surface tools
    "ping_docs": frozenset({"docs:read"}),
    "search_docs": frozenset({"docs:read"}),
    "search_knowledge": frozenset({"docs:read"}),
    "read_doc": frozenset({"docs:read"}),
    "create_doc": frozenset({"docs:write"}),
    "update_doc": frozenset({"docs:write"}),
    "upsert_doc": frozenset({"docs:write"}),
    "manage_stickies": frozenset({"docs:write"}),
    "promote_sticky_to_doc": frozenset({"docs:write"}),
    "link_knowledge": frozenset({"docs:write"}),
    # Admin surface tools
    "configure_workspace": frozenset({"admin:read"}),
    "manage_auth_cards": frozenset({"admin:read"}),
    "manage_principals_and_groups": frozenset({"admin:read"}),
    "manage_access_policies": frozenset({"admin:read"}),
    "architect_project": frozenset({"admin:read"}),
    "manage_cycles_and_modules": frozenset({"admin:read"}),
    "manage_custom_fields_and_scripts": frozenset({"admin:read"}),
    "manage_workflow_interceptors": frozenset({"admin:read"}),
    "audit_links": frozenset({"admin:read"}),
    "override_ticket_provenance": frozenset({"admin:write"}),
    "audit_and_purge_object_links": frozenset({"admin:read"}),
    "manage_ai_and_agent_runners": frozenset({"admin:read"}),
    "destructive_lifecycle": frozenset({"admin:destructive"}),
    "test_admin_destructive": frozenset({"admin:destructive"}),
}


def set_tool_scope_requirements(tool_name: str, scopes: frozenset[str] | set[str]) -> None:
    """Register or update required scopes for an MCP tool."""
    SCOPE_REQUIREMENTS[tool_name] = frozenset(scopes)


def hash_mcp_api_key(token: str) -> bytes:
    """Compute SHA-256 digest of plaintext token."""
    return hashlib.sha256(token.encode("ascii")).digest()


@dataclass(frozen=True, slots=True)
class McpAuthContext:
    """Authenticated MCP identity context stored in request state."""

    token: str
    token_sha256: bytes
    surface: Surface
    scopes: frozenset[str]
    principal_id: str | None = None
    workspace_id: str | None = None
    token_kind: str | None = "api_key"  # noqa: S105
    agent_principal_id: str | None = None
    project_id: str | None = None
    execution_id: str | None = None
    allowed_tools: frozenset[str] | None = None
    calls_used: int | None = None
    max_calls: int | None = None
    workspace_slug: str | None = None
    scope_tier: str | None = None
    owner_kind: str | None = None
    allowed_projects: list[str] | None = None
    allowed_project_keys: list[str] | None = None
    allowed_workspace_ids: list[str] | None = None
    allowed_project_ids: list[str] | None = None
    capability_mask: int = 7
    allowed_cidrs: list[str] | None = None
    disabled_tools: frozenset[str] | None = None
    aal_level: int = 2


class IntrospectionCache:
    """Thread-safe LRU cache for positive token introspection results (15s TTL)."""

    def __init__(
        self,
        *,
        max_entries: int = MAX_CACHE_ENTRIES,
        default_ttl_s: float = DEFAULT_CACHE_TTL_S,
        time_provider: Callable[[], float] = time.time,
    ) -> None:
        """Initialize positive introspection cache."""
        self._max_entries: Final[int] = max_entries
        self._default_ttl_s: Final[float] = default_ttl_s
        self._time_provider: Final[Callable[[], float]] = time_provider
        self._entries: OrderedDict[tuple[str, bytes], tuple[float, dict[str, Any]]] = OrderedDict()

    def get(self, surface: str, digest: bytes) -> dict[str, Any] | None:
        """Retrieve active cached introspection dictionary if unexpired."""
        key = (surface, digest)
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, result = entry
        now = self._time_provider()
        if now > expires_at:
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return result

    def set(
        self,
        surface: str,
        digest: bytes,
        result: dict[str, Any],
        ttl_s: float | None = None,
    ) -> None:
        """Cache positive active introspection result for TTL seconds (default 15s)."""
        key = (surface, digest)
        ttl = ttl_s if ttl_s is not None else self._default_ttl_s
        now = self._time_provider()
        expires_at = now + ttl

        if len(self._entries) >= self._max_entries and key not in self._entries:
            self._entries.popitem(last=False)

        self._entries[key] = (expires_at, result)

    def invalidate(self, surface: str, digest: bytes) -> None:
        """Evict a specific entry from the cache."""
        self._entries.pop((surface, digest), None)

    def evict_by_key_id(self, key_id: str | uuid.UUID) -> int:
        """Immediately evict all cached introspection entries matching key_id."""
        target_str = str(key_id)
        to_evict = [
            k
            for k, (_, res) in self._entries.items()
            if str(res.get("key_id", "")) == target_str or str(res.get("id", "")) == target_str
        ]
        for k in to_evict:
            self._entries.pop(k, None)
        return len(to_evict)

    def clear(self) -> None:
        """Clear all cached introspection entries."""
        self._entries.clear()


_global_cache: IntrospectionCache | None = None


def get_default_cache() -> IntrospectionCache:
    """Retrieve or construct the process-level introspection cache."""
    global _global_cache  # noqa: PLW0603
    if _global_cache is None:
        _global_cache = IntrospectionCache()
    return _global_cache


register_mcp_key_revocation_listener(lambda key_id: get_default_cache().evict_by_key_id(key_id))


class McpAuthMiddleware:
    """ASGI middleware enforcing Bearer tokens, surface prefixes, and introspection."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        surface: Surface | None = None,
        internal_client: KanbanApiClient | None = None,
        settings: McpSettings | None = None,
        cache: IntrospectionCache | None = None,
    ) -> None:
        """Initialize middleware with target surface and internal API client."""
        self.app: Final[ASGIApp] = app
        self.surface: Final[Surface | None] = surface
        self.internal_client: Final[KanbanApiClient | None] = internal_client
        self.settings: Final[McpSettings] = settings or McpSettings()
        self.cache: Final[IntrospectionCache] = cache if cache is not None else get_default_cache()

    def _resolve_surface(self, scope: Scope) -> Surface | None:
        """Resolve surface from explicit configuration or URL path."""
        path = scope.get("path", "")
        if path.startswith("/.well-known/"):
            return None

        if self.surface is not None:
            return self.surface

        if "/mcp/docs" in path:
            return Surface.DOCS
        if "/mcp/admin" in path:
            return Surface.ADMIN
        if "/mcp/agent" in path or path == "/mcp" or path.startswith("/mcp/"):
            return Surface.AGENT
        return None

    def _unauthorized_response(
        self,
        surface: Surface,
        req_scope: ConnectionScope | None = None,
        headers: Headers | None = None,
        scope: Scope | None = None,
    ) -> Response:
        """Return 401 with WWW-Authenticate header carrying protected-resource metadata."""
        env_origin = os.environ.get("KANBAN_PUBLIC_ORIGIN", "").strip()
        if env_origin:
            base_url = env_origin.rstrip("/")
        elif headers:
            host = headers.get("x-forwarded-host") or headers.get("host")
            proto = headers.get("x-forwarded-proto") or (
                str(scope.get("scheme", "https")) if scope else "https"
            )
            local_hosts = (
                "localhost",
                "127.0.0.1",
                "127.0.0.1:8443",
                "127.0.0.1:8080",
                "testserver",
                "test",
            )
            if (host and host not in local_hosts) or (headers.get("x-forwarded-proto") and host):
                base_url = f"{proto}://{host}".rstrip("/")
            else:
                base_url = self.settings.kanban_api_base_url.rstrip("/")
        else:
            base_url = self.settings.kanban_api_base_url.rstrip("/")

        metadata_url = f"{base_url}/.well-known/oauth-protected-resource/mcp/{surface.value}"
        if req_scope and getattr(req_scope, "workspace_slug", None):
            metadata_url += f"/w/{req_scope.workspace_slug}"
            if getattr(req_scope, "project_key", None):
                metadata_url += f"/p/{req_scope.project_key}"
        challenge = f'Bearer realm="kanban-mcp", resource_metadata="{metadata_url}"'
        method = scope.get("method", "HTTP") if scope else "HTTP"
        path = scope.get("path", "/mcp") if scope else "/mcp"
        _logger.warning(
            "MCP 401 Unauthorized on %s %s (surface=%s, resource_metadata=%s)",
            method,
            path,
            surface.value,
            metadata_url,
        )
        return JSONResponse(
            {"error": "unauthorized", "message": "Bearer authentication required"},
            status_code=401,
            headers={"WWW-Authenticate": challenge},
        )

    async def __call__(  # noqa: C901, PLR0911, PLR0912, PLR0915
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Process ASGI request through authentication gate."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not self.settings.auth_enabled:
            await self.app(scope, receive, send)
            return

        surface = self._resolve_surface(scope)
        if surface is None:
            await self.app(scope, receive, send)
            return

        headers = Headers(raw=scope.get("headers", []))

        # Parse connection scope early to validate path and header constraints
        from mcp.scoping import (  # noqa: PLC0415
            intersect_key_and_connection_scope,
            parse_connection_scope,
        )

        try:
            req_scope = parse_connection_scope(scope.get("path", ""), headers)
        except KbMcpError as exc:
            status_code = 400
            err_resp: Response = JSONResponse(
                {"error": exc.code.value, "message": exc.message}, status_code=status_code
            )
            await err_resp(scope, receive, send)
            return

        auth_header = headers.get("authorization", "").strip()
        parts = auth_header.split(maxsplit=1)
        if len(parts) != 2 or parts[0].lower() != "bearer":  # noqa: PLR2004
            resp = self._unauthorized_response(
                surface, req_scope=req_scope, headers=headers, scope=scope
            )
            await resp(scope, receive, send)
            return

        token = parts[1].strip()
        if not token:
            resp = self._unauthorized_response(
                surface, req_scope=req_scope, headers=headers, scope=scope
            )
            await resp(scope, receive, send)
            return

        # Ephemeral agent key reservation and surface check (KB-P4-13)
        if token.startswith(RESERVED_EPHEMERAL_PREFIX):
            if surface == Surface.ADMIN:
                resp = JSONResponse({"error": "SURFACE_KEY_MISMATCH"}, status_code=403)
                await resp(scope, receive, send)
                return
            # Allowed on agent and docs surfaces; bypass normal SURFACE_PREFIXES check
        else:
            # Local surface prefix pre-check before network call for kb_* API keys
            is_jwt = token.startswith("eyJ")
            if not is_jwt:
                expected_prefix = SURFACE_PREFIXES[surface]
                if not token.startswith(expected_prefix):
                    resp = JSONResponse({"error": "SURFACE_KEY_MISMATCH"}, status_code=403)
                    await resp(scope, receive, send)
                    return

        digest = hash_mcp_api_key(token)

        # Check positive introspection cache (bypassed for ephemeral tokens)
        intro_result = (
            None
            if token.startswith(RESERVED_EPHEMERAL_PREFIX)
            else self.cache.get(surface.value, digest)
        )
        if intro_result is None:
            # Perform introspection call via internal_client
            client = self.internal_client
            if client is None:
                # Attempt to retrieve from app state
                app_state = scope.get("app", getattr(self.app, "state", None))
                client = getattr(app_state, "internal_client", None)

            if client is None:
                _logger.error("KanbanApiClient unavailable for MCP token introspection")
                err_resp = JSONResponse(
                    {
                        "error": "UPSTREAM_UNAVAILABLE",
                        "message": "Introspection client unavailable",
                    },
                    status_code=503,
                )
                await err_resp(scope, receive, send)
                return

            try:
                res_data = await client.request(
                    "POST",
                    "/internal/v1/mcp/introspect",
                    json_data={"token": token, "surface": surface.value},
                )
            except KbMcpError as exc:
                if exc.code == McpErrorCode.SURFACE_KEY_MISMATCH:
                    resp = JSONResponse({"error": "SURFACE_KEY_MISMATCH"}, status_code=403)
                    await resp(scope, receive, send)
                    return
                resp = self._unauthorized_response(
                    surface, req_scope=req_scope, headers=headers, scope=scope
                )
                await resp(scope, receive, send)
                return
            except Exception:
                _logger.exception("Introspection request failed")
                resp = self._unauthorized_response(
                    surface, req_scope=req_scope, headers=headers, scope=scope
                )
                await resp(scope, receive, send)
                return

            if not isinstance(res_data, dict):
                resp = self._unauthorized_response(
                    surface, req_scope=req_scope, headers=headers, scope=scope
                )
                await resp(scope, receive, send)
                return

            if not res_data.get("active"):
                reason = res_data.get("reason")
                if reason == "SURFACE_KEY_MISMATCH":
                    resp = JSONResponse({"error": "SURFACE_KEY_MISMATCH"}, status_code=403)
                    await resp(scope, receive, send)
                    return
                if reason == "EPHEMERAL_CALL_BUDGET_EXCEEDED":
                    intro_result = res_data
                else:
                    resp = self._unauthorized_response(
                        surface, req_scope=req_scope, headers=headers, scope=scope
                    )
                    await resp(scope, receive, send)
                    return
            else:
                # Cache positive active result for 15 seconds (NEVER cache ephemeral tokens)
                if not token.startswith(RESERVED_EPHEMERAL_PREFIX):
                    self.cache.set(surface.value, digest, res_data, ttl_s=DEFAULT_CACHE_TTL_S)
                intro_result = res_data

        # Check CIDR restriction if configured on token
        allowed_cidrs = intro_result.get("allowed_cidrs")
        if allowed_cidrs:
            client_ip = None
            xff = headers.get("x-forwarded-for")
            if xff:
                client_ip = xff.split(",")[0].strip()
            elif scope.get("client"):
                client_ip = scope["client"][0]

            if client_ip:
                try:
                    ip = ipaddress.ip_address(client_ip)
                    matched = False
                    for cidr_str in allowed_cidrs:
                        if ip in ipaddress.ip_network(str(cidr_str), strict=False):
                            matched = True
                            break
                    if not matched:
                        resp = JSONResponse(
                            {
                                "error": "KEY_CIDR_DENIED",
                                "message": (
                                    f"Client IP '{client_ip}' not allowed by key CIDR restriction"
                                ),
                            },
                            status_code=403,
                        )
                        await resp(scope, receive, send)
                        return
                except ValueError:
                    resp = JSONResponse(
                        {"error": "KEY_CIDR_DENIED", "message": "Invalid client IP format"},
                        status_code=403,
                    )
                    await resp(scope, receive, send)
                    return

        # Populate request state and forward validated token header
        raw_headers = list(scope.get("headers", []))
        # Add or replace X-KB-Subject-Token
        token_bytes = token.encode("ascii")
        filtered_headers = [(k, v) for k, v in raw_headers if k.lower() != b"x-kb-subject-token"]
        filtered_headers.append((b"x-kb-subject-token", token_bytes))
        scope["headers"] = filtered_headers

        scopes_list = intro_result.get("scopes") or []
        allowed_tools_list = intro_result.get("allowed_tools")
        allowed_tools_set = (
            frozenset(allowed_tools_list) if allowed_tools_list is not None else None
        )
        disabled_tools_list = intro_result.get("disabled_tools")
        disabled_tools_set = frozenset(disabled_tools_list) if disabled_tools_list else frozenset()
        token_kind = (
            "ephemeral"
            if token.startswith(RESERVED_EPHEMERAL_PREFIX)
            else intro_result.get("token_kind", "api_key")
        )
        allowed_projects_raw = intro_result.get("allowed_projects")
        allowed_projects = (
            [str(p) for p in allowed_projects_raw]
            if isinstance(allowed_projects_raw, list)
            else None
        )
        allowed_project_keys_raw = intro_result.get("allowed_project_keys")
        allowed_project_keys = (
            [str(k) for k in allowed_project_keys_raw]
            if isinstance(allowed_project_keys_raw, list)
            else None
        )
        aal = int(intro_result.get("aal_level", 2))
        auth_context = McpAuthContext(
            token=token,
            token_sha256=digest,
            surface=surface,
            scopes=frozenset(str(s) for s in scopes_list),
            principal_id=intro_result.get("principal_id"),
            workspace_id=intro_result.get("workspace_id"),
            token_kind=token_kind,
            aal_level=aal,
            agent_principal_id=intro_result.get("agent_principal_id"),
            project_id=intro_result.get("project_id"),
            execution_id=intro_result.get("execution_id"),
            allowed_tools=allowed_tools_set,
            disabled_tools=disabled_tools_set,
            calls_used=intro_result.get("calls_used"),
            max_calls=intro_result.get("max_calls"),
            workspace_slug=intro_result.get("workspace_slug"),
            scope_tier=intro_result.get("scope_tier"),
            owner_kind=intro_result.get("owner_kind"),
            allowed_projects=allowed_projects,
            allowed_project_keys=allowed_project_keys,
            allowed_workspace_ids=(
                [str(w) for w in intro_result["allowed_workspace_ids"]]
                if intro_result.get("allowed_workspace_ids")
                else None
            ),
            allowed_project_ids=(
                [str(p) for p in intro_result["allowed_project_ids"]]
                if intro_result.get("allowed_project_ids")
                else None
            ),
            capability_mask=int(intro_result.get("capability_mask") or 7),
            allowed_cidrs=allowed_cidrs,
        )

        mcp_actor = format_log_actor(
            auth_context.principal_id,
            agent_principal_id=auth_context.agent_principal_id,
        )
        user_ctx_token = set_log_user(mcp_actor)
        try:
            try:
                effective_scope = intersect_key_and_connection_scope(auth_context, req_scope)
            except KbMcpError as exc:
                status_code = 403 if exc.code == McpErrorCode.KEY_SCOPE_VIOLATION else 400
                _logger.warning(
                    "MCP %d %s on %s %s (surface=%s, tier=%s, key_ws=%s, req_ws=%s, proj=%s): %s",
                    status_code,
                    exc.code.value,
                    scope.get("method", "HTTP"),
                    scope.get("path", "/mcp"),
                    surface.value,
                    auth_context.scope_tier,
                    auth_context.workspace_slug or auth_context.workspace_id,
                    req_scope.workspace_slug,
                    req_scope.project_key,
                    exc.message,
                )
                payload: dict[str, Any] = {"error": exc.code.value, "message": exc.message}
                if exc.extra:
                    payload.update(exc.extra)
                if exc.hint:
                    payload["hint"] = exc.hint
                resp = JSONResponse(payload, status_code=status_code)
                await resp(scope, receive, send)
                return

            state = scope.setdefault("state", {})
            state["mcp_auth"] = auth_context
            state["mcp_scopes"] = auth_context.scopes
            state["mcp_token_sha256"] = digest
            state["connection_scope"] = effective_scope
            state["log_user"] = mcp_actor

            await self.app(scope, receive, send)
        finally:
            reset_log_user(user_ctx_token)
