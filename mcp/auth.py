# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""MCP authentication middleware, surface prefix validation, and tool scoping (KB-P4-02a)."""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from starlette.datastructures import Headers
from starlette.responses import JSONResponse, Response

from mcp.errors import KbMcpError, McpErrorCode
from mcp.registry import Surface
from mcp.settings import McpSettings

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.types import ASGIApp, Receive, Scope, Send

    from mcp.internal_client import KanbanApiClient

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
    "complete_work": frozenset({"agent:write"}),
    "test_agent_write": frozenset({"agent:write"}),
    # Docs surface tools
    "ping_docs": frozenset({"docs:read"}),
    "search_docs": frozenset({"docs:read"}),
    "read_doc": frozenset({"docs:read"}),
    "create_doc": frozenset({"docs:write"}),
    "update_doc": frozenset({"docs:write"}),
    # Admin surface tools
    "audit_links": frozenset({"admin:read"}),
    "override_ticket_provenance": frozenset({"admin:write"}),
    "audit_and_purge_object_links": frozenset({"admin:destructive"}),
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
        if self.surface is not None:
            return self.surface

        path = scope.get("path", "")
        if "/mcp/agent" in path:
            return Surface.AGENT
        if "/mcp/docs" in path:
            return Surface.DOCS
        if "/mcp/admin" in path:
            return Surface.ADMIN
        return None

    def _unauthorized_response(self, surface: Surface) -> Response:
        """Return 401 with WWW-Authenticate header carrying protected-resource metadata."""
        base_url = self.settings.kanban_api_base_url.rstrip("/")
        metadata_url = f"{base_url}/.well-known/oauth-protected-resource/mcp/{surface.value}"
        challenge = f'Bearer realm="kanban-mcp", resource_metadata="{metadata_url}"'
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
        auth_header = headers.get("authorization")

        if not auth_header or not auth_header.lower().startswith("bearer "):
            resp = self._unauthorized_response(surface)
            await resp(scope, receive, send)
            return

        token = auth_header[7:].strip()
        if not token:
            resp = self._unauthorized_response(surface)
            await resp(scope, receive, send)
            return

        # Ephemeral agent key reservation check (rejected until KB-P4-13)
        if token.startswith(RESERVED_EPHEMERAL_PREFIX):
            resp = JSONResponse({"error": "SURFACE_KEY_MISMATCH"}, status_code=403)
            await resp(scope, receive, send)
            return

        # Local surface prefix pre-check before network call for kb_* API keys
        is_jwt = token.startswith("eyJ")
        if not is_jwt:
            expected_prefix = SURFACE_PREFIXES[surface]
            if not token.startswith(expected_prefix):
                resp = JSONResponse({"error": "SURFACE_KEY_MISMATCH"}, status_code=403)
                await resp(scope, receive, send)
                return

        digest = hash_mcp_api_key(token)

        # Check positive introspection cache
        intro_result = self.cache.get(surface.value, digest)
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
                resp = self._unauthorized_response(surface)
                await resp(scope, receive, send)
                return
            except Exception:
                _logger.exception("Introspection request failed")
                resp = self._unauthorized_response(surface)
                await resp(scope, receive, send)
                return

            if not isinstance(res_data, dict):
                resp = self._unauthorized_response(surface)
                await resp(scope, receive, send)
                return

            if not res_data.get("active"):
                reason = res_data.get("reason")
                if reason == "SURFACE_KEY_MISMATCH":
                    resp = JSONResponse({"error": "SURFACE_KEY_MISMATCH"}, status_code=403)
                    await resp(scope, receive, send)
                    return
                resp = self._unauthorized_response(surface)
                await resp(scope, receive, send)
                return

            # Cache positive active result for 15 seconds
            self.cache.set(surface.value, digest, res_data, ttl_s=DEFAULT_CACHE_TTL_S)
            intro_result = res_data

        # Populate request state and forward validated token header
        raw_headers = list(scope.get("headers", []))
        # Add or replace X-KB-Subject-Token
        token_bytes = token.encode("ascii")
        filtered_headers = [(k, v) for k, v in raw_headers if k.lower() != b"x-kb-subject-token"]
        filtered_headers.append((b"x-kb-subject-token", token_bytes))
        scope["headers"] = filtered_headers

        scopes_list = intro_result.get("scopes") or []
        aal = int(intro_result.get("aal_level", 2))
        auth_context = McpAuthContext(
            token=token,
            token_sha256=digest,
            surface=surface,
            scopes=frozenset(str(s) for s in scopes_list),
            principal_id=intro_result.get("principal_id"),
            workspace_id=intro_result.get("workspace_id"),
            token_kind=intro_result.get("token_kind", "api_key"),
            aal_level=aal,
        )

        state = scope.setdefault("state", {})
        state["mcp_auth"] = auth_context
        state["mcp_scopes"] = auth_context.scopes
        state["mcp_token_sha256"] = digest

        await self.app(scope, receive, send)
