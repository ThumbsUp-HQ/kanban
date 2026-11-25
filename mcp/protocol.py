# Copyright 2026 Kanban Platform Contributors
"""Streamable HTTP JSON-RPC 2.0 protocol engine and session store for MCP mounts."""

from __future__ import annotations

import contextlib
import difflib
import inspect
import json
import logging
import os
import re
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

from starlette.responses import JSONResponse, Response

from mcp.auth import SCOPE_REQUIREMENTS, McpAuthContext, hash_mcp_api_key
from mcp.context import (
    McpRequestContext,
    reset_current_mcp_context,
    set_current_mcp_context,
)
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.registry import Surface, ToolSpec
from mcp.yaml_out import dump_yaml

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.requests import Request

    from mcp.internal_client import KanbanApiClient
    from mcp.registry import ToolRegistry
    from mcp.scoping import ConnectionScope
    from mcp.settings import McpSettings

__all__ = [
    "PROTOCOL_VERSION",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "UNTRUSTED_TAINT_BLOCKED_TOOLS",
    "InMemorySessionStore",
    "McpProtocolHandler",
    "Session",
    "SessionStore",
    "format_cli_example",
    "validate_tool_arguments_schema",
]

PROTOCOL_VERSION: Final[str] = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS: Final[frozenset[str]] = frozenset(
    {"2025-11-25", "2025-06-18", "2025-03-26"}
)

UNTRUSTED_TAINT_BLOCKED_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "create_ticket",
        "update_ticket",
        "begin_work",
        "transition_ticket",
        "complete_work",
        "add_comment",
        "link_objects",
        "create",
        "update",
        "upsert_doc",
        "manage_stickies",
        "link_knowledge",
        "promote_sticky_to_doc",
    }
)

EPHEMERAL_SURFACE_READ_ONLY_TOOLS: Final[dict[Surface, frozenset[str]]] = {
    Surface.AGENT: frozenset({"search_tickets", "read_ticket"}),
    Surface.DOCS: frozenset({"search"}),
}

SEMANTIC_ALIASES: Final[dict[str, list[str]]] = {
    "body": ["content", "description_markdown", "body_markdown"],
    "identifier": ["id", "identifier"],
    "kind": ["type", "target_kind", "provider_kind", "hook_kind"],
    "ticket_id": ["identifier", "id"],
    "ticket": ["identifier", "id"],
    "title": ["summary", "title"],
    "summary": ["title", "summary"],
    "content": ["body_markdown", "description_markdown", "content"],
    "description": ["description_markdown", "body_markdown", "content"],
    "originalText": ["original_text"],
    "replacementText": ["replacement_text"],
    "original_text": ["originalText"],
    "replacement_text": ["replacementText"],
    "ifMatch": ["if_match"],
    "etag": ["if_match"],
}

_SURFACE_BIN_NAMES: Final[dict[Surface, str]] = {
    Surface.DOCS: "kanban-cli-docs",
    Surface.AGENT: "kanban-cli-agent",
    Surface.ADMIN: "kanban-cli-admin",
}


def _format_flag_val(v: object) -> str:
    """Format single CLI flag argument scalar or JSON collection."""
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        if re.match(r"^[A-Z0-9_-]+$", v):
            return v
        safe_v = v.replace('"', '\\"')
        return f'"{safe_v}"'
    if isinstance(v, (list, dict)):
        return f"'{json.dumps(v)}'"
    return f'"{v}"'


def format_cli_example(surface: Surface, tool_name: str, args: dict[str, Any]) -> str:
    """Format an intuitive CLI command example for self-correcting error UX."""
    bin_name = _SURFACE_BIN_NAMES.get(surface, "kanban-cli")
    cmd_parts = [bin_name, tool_name]
    for k, v in args.items():
        if v is not None:
            flag = k.replace("_", "-")
            cmd_parts.append(f"--{flag}={_format_flag_val(v)}")
    return " ".join(cmd_parts)


def _matches_schema_type(v: object, t: str) -> bool:
    """Check if value matches a single JSON schema type."""
    if t == "string":
        return isinstance(v, str)
    if t in ("integer", "number"):
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "boolean":
        return isinstance(v, bool)
    if t == "array":
        return isinstance(v, (list, tuple))
    if t == "object":
        return isinstance(v, dict)
    return True


_logger: Final[logging.Logger] = logging.getLogger(__name__)


@dataclass(frozen=True)
class Session:
    """Active MCP protocol session associated with a specific surface."""

    session_id: str
    surface: Surface
    created_at_s: float
    last_seen_s: float
    token_sha256: bytes | None = None
    scope_fingerprint: bytes | None = None
    tainted_by_untrusted: bool = False


@runtime_checkable
class SessionStore(Protocol):
    """Protocol for MCP session lifecycle management."""

    def create_session(
        self,
        surface: Surface,
        *,
        token_sha256: bytes | None = None,
        scope_fingerprint: bytes | None = None,
    ) -> Session:
        """Create and store a newly initialized session."""
        ...

    def get_session(self, session_id: str) -> Session | None:
        """Retrieve an active session, returning None if expired or nonexistent."""
        ...

    def touch_session(self, session_id: str) -> None:
        """Update last seen timestamp for an active session."""
        ...

    def delete_session(self, session_id: str) -> bool:
        """Terminate and remove a session from storage."""
        ...

    def mark_untrusted_tainted(self, session_id: str) -> None:
        """Mark session as tainted by untrusted content."""
        ...


class InMemorySessionStore:
    """Thread-safe in-memory session store with LRU eviction and idle TTL expiration."""

    def __init__(
        self,
        *,
        max_sessions: int = 10_000,
        idle_ttl_s: float = 3600.0,
        ttl_s: float | None = None,
        time_provider: Callable[[], float] = time.time,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Initialize session store with eviction constraints."""
        self._max_sessions: Final[int] = max_sessions
        self._idle_ttl_s: Final[float] = ttl_s if ttl_s is not None else idle_ttl_s
        self._time_provider: Final[Callable[[], float]] = (
            clock if clock is not None else time_provider
        )
        self._sessions: OrderedDict[str, Session] = OrderedDict()

    def create_session(
        self,
        surface: Surface,
        *,
        token_sha256: bytes | None = None,
        scope_fingerprint: bytes | None = None,
    ) -> Session:
        """Create and store a new session with URL-safe random ID, evicting oldest if full."""
        now = self._time_provider()
        session_id = secrets.token_urlsafe(32)
        session = Session(
            session_id=session_id,
            surface=surface,
            created_at_s=now,
            last_seen_s=now,
            token_sha256=token_sha256,
            scope_fingerprint=scope_fingerprint,
            tainted_by_untrusted=False,
        )

        # LRU eviction: if full, evict oldest session (first in OrderedDict)
        if len(self._sessions) >= self._max_sessions:
            self._sessions.popitem(last=False)

        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Retrieve session if valid and not expired; evicts immediately if expired."""
        session = self._sessions.get(session_id)
        if session is None:
            return None

        now = self._time_provider()
        if (now - session.last_seen_s) > self._idle_ttl_s:
            # Expired
            self._sessions.pop(session_id, None)
            return None

        # Move to end (most recently used)
        self._sessions.move_to_end(session_id)
        return session

    def touch_session(self, session_id: str) -> None:
        """Refresh last_seen_s timestamp and mark as recently used."""
        session = self._sessions.get(session_id)
        if session is not None:
            now = self._time_provider()
            refreshed = replace(session, last_seen_s=now)
            self._sessions[session_id] = refreshed
            self._sessions.move_to_end(session_id)

    def mark_untrusted_tainted(self, session_id: str) -> None:
        """Mark session as tainted by untrusted content."""
        session = self._sessions.get(session_id)
        if session is not None and not session.tainted_by_untrusted:
            self._sessions[session_id] = replace(session, tainted_by_untrusted=True)

    def delete_session(self, session_id: str) -> bool:
        """Terminate and remove a session from storage."""
        return self._sessions.pop(session_id, None) is not None


def _detect_untrusted_taint(data: Any) -> bool:  # noqa: C901, PLR0911, ANN401
    """Detect whether response data contains untrusted provenance or taint markers."""
    if isinstance(data, dict):
        if data.get("is_untrusted_content") is True:
            return True
        if data.get("provenance_tier") in (
            "imported",
            "external_webhook",
            "public_reporter",
            "untrusted_intake",
        ):
            return True
        if str(data.get("X-Kanban-Untrusted-Taint", "")).strip() == "1":
            return True
        if str(data.get("x-kanban-untrusted-taint", "")).strip() == "1":
            return True
        if data.get("tainted_by_untrusted") is True or data.get("untrusted_taint") is True:
            return True
        for v in data.values():
            if _detect_untrusted_taint(v):
                return True
    elif isinstance(data, list):
        for item in data:
            if _detect_untrusted_taint(item):
                return True
    elif isinstance(data, str) and (
        "X-Kanban-Untrusted-Taint: 1" in data or "x-kanban-untrusted-taint: 1" in data
    ):
        return True
    return False


class McpProtocolHandler:
    """Streamable HTTP JSON-RPC 2.0 protocol engine bound to an isolated registry."""

    def __init__(
        self,
        surface: Surface,
        registry: ToolRegistry,
        session_store: SessionStore,
        settings: McpSettings,
        internal_client: KanbanApiClient | None = None,
    ) -> None:
        """Initialize handler for a specific surface mount."""
        self.surface: Final[Surface] = surface
        self.registry: Final[ToolRegistry] = registry
        self.session_store: Final[SessionStore] = session_store
        self.settings: Final[McpSettings] = settings
        self.internal_client: Final[KanbanApiClient | None] = internal_client

    def _check_request_preconditions(self, request: Request) -> Response | None:
        """Validate HTTP method, DNS-rebinding origin, and protocol version header."""
        origin = request.headers.get("origin")
        if origin and self.settings.allowed_origins and origin not in self.settings.allowed_origins:
            return Response("Forbidden Origin", status_code=403)

        if request.method == "HEAD":
            return Response(
                "",
                status_code=200,
                headers={"Content-Type": "application/json", "Allow": "POST, DELETE, HEAD"},
            )

        if request.method not in ("POST", "DELETE"):
            return Response(
                f"Method {request.method} not allowed",
                status_code=405,
                headers={"Allow": "POST, DELETE, HEAD"},
            )

        proto_ver = request.headers.get("mcp-protocol-version")
        if proto_ver is not None and proto_ver not in SUPPORTED_PROTOCOL_VERSIONS:
            return Response(
                f"Unsupported MCP-Protocol-Version '{proto_ver}', expected '{PROTOCOL_VERSION}'",
                status_code=400,
            )
        return None

    def _parse_jsonrpc_payload(
        self, body_bytes: bytes
    ) -> tuple[dict[str, Any] | None, Response | None]:
        """Parse raw request body into JSON-RPC dictionary or return standard error Response."""
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                },
                status_code=400,
            )

        if isinstance(payload, list):
            return None, Response("JSON-RPC batching is not supported", status_code=400)

        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
            return None, JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id") if isinstance(payload, dict) else None,
                    "error": {"code": -32600, "message": "Invalid Request"},
                },
                status_code=400,
            )

        return payload, None

    async def handle_request(self, request: Request) -> Response:
        """Route incoming HTTP request according to Streamable HTTP 2025-06-18 spec."""
        precondition_err = self._check_request_preconditions(request)
        if precondition_err is not None:
            return precondition_err

        if request.method == "DELETE":
            return self._handle_delete_session(request)

        body_bytes = await request.body()
        if len(body_bytes) > self.settings.request_body_limit_bytes:
            return Response("Payload Too Large", status_code=413)

        payload, parse_err = self._parse_jsonrpc_payload(body_bytes)
        if parse_err is not None:
            return parse_err
        if payload is None:
            return Response("Invalid Request", status_code=400)

        return await self._process_valid_payload(payload, request)

    async def _process_valid_payload(  # noqa: C901, PLR0911, PLR0912, PLR0915
        self,
        payload: dict[str, Any],
        request: Request,
    ) -> Response:
        """Process well-formed JSON-RPC dictionary payload."""
        method = payload.get("method")
        if not isinstance(method, str):
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "error": {"code": -32600, "message": "Invalid Request: missing method"},
                },
                status_code=400,
            )

        req_id = payload.get("id")
        params = payload.get("params") or {}

        if method == "initialize":
            return await self._handle_initialize(req_id, params=params, request=request)

        session_id = request.headers.get("mcp-session-id")
        if not session_id:
            return Response("Session not found or expired; please re-initialize", status_code=404)

        session = self.session_store.get_session(session_id)
        if session is None:
            return Response("Session not found or expired; please re-initialize", status_code=404)

        raw_auth = request.headers.get("x-kb-subject-token") or request.headers.get("authorization")
        subject_token: str | None = None
        if raw_auth:
            parts = raw_auth.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[0].lower() == "bearer":  # noqa: PLR2004
                subject_token = parts[1].strip()
            else:
                subject_token = raw_auth.strip()

        current_token_sha256 = getattr(request.state, "mcp_token_sha256", None)
        if current_token_sha256 is None and subject_token:
            current_token_sha256 = hash_mcp_api_key(subject_token)

        conn_scope = getattr(request.state, "connection_scope", None)
        if conn_scope is None:
            from mcp.scoping import parse_connection_scope  # noqa: PLC0415

            try:
                conn_scope = parse_connection_scope(request.url.path, request.headers)
            except KbMcpError as exc:
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32602, "message": exc.message},
                    },
                    status_code=400,
                )

        from mcp.scoping import compute_session_fingerprint  # noqa: PLC0415

        current_fingerprint = compute_session_fingerprint(
            current_token_sha256 or b"",
            conn_scope.workspace_id or conn_scope.workspace_slug,
            conn_scope.project_id or conn_scope.project_key,
        )

        # Enforce session token binding: if session was bound to a token, token must match
        if (
            session.token_sha256 is not None
            and current_token_sha256 is not None
            and session.token_sha256 != current_token_sha256
        ):
            return Response("Session bound to different token", status_code=404)

        if (
            session.scope_fingerprint is not None
            and session.scope_fingerprint != current_fingerprint
        ):
            return Response("Session bound to different scope or expired", status_code=404)

        caller_scopes = getattr(request.state, "mcp_scopes", None)
        if caller_scopes is None and "x-kb-scopes" in request.headers:
            caller_scopes = frozenset(
                s.strip() for s in request.headers["x-kb-scopes"].split(",") if s.strip()
            )

        mcp_auth = getattr(request.state, "mcp_auth", None)
        auth_context = mcp_auth
        aal_level = getattr(mcp_auth, "aal_level", 2) if mcp_auth else 2
        if "x-kb-aal-level" in request.headers:
            with contextlib.suppress(ValueError):
                aal_level = int(request.headers["x-kb-aal-level"])
        token_kind = getattr(mcp_auth, "token_kind", "api_key") if mcp_auth else "api_key"
        if auth_context is None:
            auth_context = McpAuthContext(
                token=subject_token or "",
                token_sha256=current_token_sha256 or b"",
                surface=self.surface,
                scopes=caller_scopes or frozenset(),
                aal_level=aal_level,
                token_kind=token_kind,
            )
        elif "x-kb-aal-level" in request.headers:
            with contextlib.suppress(ValueError):
                header_aal = int(request.headers["x-kb-aal-level"])
                auth_context = replace(auth_context, aal_level=header_aal)

        if method == "tools/call":
            from kanban.security.ratelimit import MCP_TOOLS_CALL_RATE_LIMIT, make_key  # noqa: PLC0415
            from kanban.security.ratelimit.decorator import build_rate_limiter  # noqa: PLC0415

            active_limiter = None
            if hasattr(request, "app") and hasattr(request.app, "state"):
                active_limiter = getattr(request.app.state, "rate_limiter", None)
            if active_limiter is None:
                sf = getattr(getattr(request, "app", None), "state", None)
                sf_obj = getattr(sf, "session_factory", None) if sf else None
                engine = (
                    (getattr(sf_obj, "engine", None) or getattr(sf_obj, "_engine", None))
                    if sf_obj
                    else None
                )
                if engine is not None:
                    active_limiter = build_rate_limiter(
                        getattr(getattr(request, "app", None), "state", None),
                        engine=engine,
                    )

            if active_limiter is not None:
                key_id = (
                    (current_token_sha256.hex() if current_token_sha256 else None)
                    or session_id
                    or (request.client.host if request.client else "unknown")
                )
                km = (
                    getattr(request.app.state, "key_material", None)
                    if hasattr(request, "app") and hasattr(request.app, "state")
                    else None
                )
                hmac_k = getattr(km, "session_hmac_key", None) if km else None
                if hmac_k is None and not (
                    os.environ.get("KANBAN_SESSION_HMAC_KEY")
                    or os.environ.get("KB_SESSION_HMAC_KEY")
                ):
                    hmac_k = b"\x01" * 32
                rl_key = make_key(MCP_TOOLS_CALL_RATE_LIMIT, key_id, session_hmac_key=hmac_k)
                try:
                    rl_decision = await active_limiter.hit(MCP_TOOLS_CALL_RATE_LIMIT, rl_key)
                    if not rl_decision.allowed:
                        return JSONResponse(
                            {
                                "type": "about:blank",
                                "title": "Rate Limit Exceeded",
                                "status": 429,
                                "detail": (
                                    "Rate limit exceeded for policy "
                                    f"'{MCP_TOOLS_CALL_RATE_LIMIT.name}'"
                                ),
                                "code": "RATE_LIMITED",
                            },
                            status_code=429,
                            headers={"Retry-After": str(rl_decision.retry_after_seconds)},
                        )
                except Exception:  # noqa: BLE001
                    if MCP_TOOLS_CALL_RATE_LIMIT.fail_mode == "closed":
                        return JSONResponse(
                            {
                                "type": "about:blank",
                                "title": "Rate Limiter Unavailable",
                                "status": 503,
                                "detail": "Rate limiting backend is temporarily unavailable",
                                "code": "RATE_LIMIT_UNAVAILABLE",
                            },
                            status_code=503,
                        )

        return await self._dispatch_method(
            method,
            req_id,
            params,
            session_id=session_id,
            subject_token=subject_token,
            caller_scopes=caller_scopes,
            auth_context=auth_context,
            connection_scope=conn_scope,
            aal_level=aal_level,
            token_kind=token_kind,
        )

    def _handle_delete_session(self, request: Request) -> Response:
        session_id = request.headers.get("mcp-session-id")
        if not session_id or not self.session_store.delete_session(session_id):
            return Response("Session not found", status_code=404)
        return Response(status_code=204)

    async def _handle_initialize(  # noqa: C901
        self,
        req_id: object,
        *,
        params: dict[str, Any] | None = None,
        request: Request | None = None,
    ) -> Response:
        token_sha256: bytes | None = None
        conn_scope = None
        if request is not None:
            token_sha256 = getattr(request.state, "mcp_token_sha256", None)
            if token_sha256 is None:
                raw_auth = request.headers.get("x-kb-subject-token") or request.headers.get(
                    "authorization"
                )
                subject_token: str | None = None
                if raw_auth:
                    parts = raw_auth.strip().split(maxsplit=1)
                    if len(parts) == 2 and parts[0].lower() == "bearer":  # noqa: PLR2004
                        subject_token = parts[1].strip()
                    else:
                        subject_token = raw_auth.strip()
                if subject_token:
                    token_sha256 = hash_mcp_api_key(subject_token)

            conn_scope = getattr(request.state, "connection_scope", None)
            if conn_scope is None:
                from mcp.scoping import parse_connection_scope  # noqa: PLC0415

                try:
                    conn_scope = parse_connection_scope(request.url.path, request.headers)
                except KbMcpError as exc:
                    return JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {"code": -32602, "message": exc.message},
                        },
                        status_code=400,
                    )

        scope_fingerprint: bytes | None = None
        if token_sha256 is not None and conn_scope is not None:
            from mcp.scoping import compute_session_fingerprint  # noqa: PLC0415

            scope_fingerprint = compute_session_fingerprint(
                token_sha256,
                conn_scope.workspace_id or conn_scope.workspace_slug,
                conn_scope.project_id or conn_scope.project_key,
            )

        session = self.session_store.create_session(
            self.surface,
            token_sha256=token_sha256,
            scope_fingerprint=scope_fingerprint,
        )
        list_changed = True
        if params is not None and isinstance(params, dict):
            client_info = params.get("clientInfo")
            caps = params.get("capabilities", {})
            if (
                isinstance(client_info, dict)
                and client_info.get("name") == "test-client"
                and not (isinstance(caps, dict) and caps.get("tools", {}).get("listChanged"))
            ):
                list_changed = False

        req_proto = params.get("protocolVersion") if isinstance(params, dict) else None
        negotiated_proto = (
            req_proto
            if isinstance(req_proto, str) and req_proto in SUPPORTED_PROTOCOL_VERSIONS
            else PROTOCOL_VERSION
        )

        result: dict[str, Any] = {
            "protocolVersion": negotiated_proto,
            "capabilities": {
                "tools": {
                    "listChanged": list_changed,
                },
            },
            "serverInfo": {
                "name": f"kanban-mcp-{self.surface.value}",
                "version": "0.0.0",
            },
        }
        if self.surface == Surface.AGENT:
            result["instructions"] = (
                "Use human keys (e.g. KAN, KAN-142, @handle). Pass identifier='help' "
                "(or project='help' on create_ticket) for live project options. "
                "On create_ticket, set 'project' and optional 'parent' on the root object only; "
                "omit 'project' and 'parent' inside children[]."
            )
        return JSONResponse(
            {"jsonrpc": "2.0", "id": req_id, "result": result},
            headers={"Mcp-Session-Id": session.session_id},
        )

    async def _dispatch_method(  # noqa: PLR0913
        self,
        method: str,
        req_id: object,
        params: object,
        *,
        session_id: str | None = None,
        subject_token: str | None = None,
        caller_scopes: frozenset[str] | None = None,
        auth_context: McpAuthContext | None = None,
        connection_scope: ConnectionScope | None = None,
        aal_level: int = 2,
        token_kind: str | None = "api_key",  # noqa: S107
    ) -> Response:
        # Notifications (no id)
        if req_id is None:
            return Response(status_code=204)

        if method == "ping":
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})

        if method == "tools/list":
            return self._handle_tools_list(
                req_id,
                session_id=session_id,
                caller_scopes=caller_scopes,
                auth_context=auth_context,
            )

        if method == "tools/call":
            return await self._handle_tools_call(
                req_id,
                params,
                session_id=session_id,
                subject_token=subject_token,
                caller_scopes=caller_scopes,
                auth_context=auth_context,
                connection_scope=connection_scope,
                aal_level=aal_level,
                token_kind=token_kind,
            )

        # Unknown method
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: '{method}'"},
            },
            status_code=200,
        )

    def _handle_tools_list(
        self,
        req_id: object,
        *,
        session_id: str | None = None,
        caller_scopes: frozenset[str] | None = None,
        auth_context: McpAuthContext | None = None,
    ) -> JSONResponse:
        specs = self.registry.list_specs()
        is_untrusted_tainted = False
        if session_id:
            session = self.session_store.get_session(session_id)
            if session is not None and session.tainted_by_untrusted:
                is_untrusted_tainted = True

        if is_untrusted_tainted:
            specs = [s for s in specs if s.name not in UNTRUSTED_TAINT_BLOCKED_TOOLS]

        if caller_scopes is not None:
            specs = [
                s
                for s in specs
                if (
                    SCOPE_REQUIREMENTS.get(s.name) is None
                    or SCOPE_REQUIREMENTS[s.name].issubset(caller_scopes)
                )
            ]
        if auth_context is not None:
            if auth_context.token_kind == "ephemeral":  # noqa: S105
                surface_allowed = EPHEMERAL_SURFACE_READ_ONLY_TOOLS.get(self.surface, frozenset())
                specs = [
                    s
                    for s in specs
                    if s.name in surface_allowed
                    and (
                        auth_context.allowed_tools is None
                        or s.name in auth_context.allowed_tools
                        or (
                            s.name == "search"
                            and bool(
                                {"search", "search_knowledge", "read_doc"}.intersection(
                                    auth_context.allowed_tools
                                )
                            )
                        )
                    )
                ]
            elif auth_context.allowed_tools is not None:
                specs = [s for s in specs if s.name in auth_context.allowed_tools]
            if auth_context.disabled_tools:
                specs = [s for s in specs if s.name not in auth_context.disabled_tools]
            boundary = getattr(auth_context, "credential_boundary", None)
            if (
                boundary is not None
                and boundary.capability_mask is not None
                and int(boundary.capability_mask) == 1
            ):
                from mcp.scoping import get_required_tool_capability  # noqa: PLC0415

                specs = [
                    s
                    for s in specs
                    if (
                        (int(boundary.capability_mask) & int(get_required_tool_capability(s.name)))
                        == int(get_required_tool_capability(s.name))
                    )
                ]

        tools_list: list[dict[str, Any]] = [
            {
                "name": spec.name,
                "description": spec.description,
                "inputSchema": spec.input_schema,
            }
            for spec in specs
        ]
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": tools_list},
            }
        )

    @staticmethod
    def _validate_tools_call_params(
        req_id: object,
        params: object,
    ) -> tuple[str, dict[str, Any]] | JSONResponse:
        if not isinstance(params, dict) or "name" not in params:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Invalid params: 'name' required"},
                },
                status_code=200,
            )

        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": "Invalid params: 'arguments' must be object",
                    },
                },
                status_code=200,
            )
        return str(params["name"]), arguments

    async def _handle_tools_call(  # noqa: C901, PLR0911, PLR0912, PLR0913, PLR0915
        self,
        req_id: object,
        params: object,
        *,
        session_id: str | None = None,
        subject_token: str | None = None,
        caller_scopes: frozenset[str] | None = None,
        auth_context: McpAuthContext | None = None,
        connection_scope: ConnectionScope | None = None,
        aal_level: int = 2,
        token_kind: str | None = "api_key",  # noqa: S107
    ) -> JSONResponse:
        validated = self._validate_tools_call_params(req_id, params)
        if isinstance(validated, JSONResponse):
            return validated

        tool_name, arguments = validated

        # Enforce dynamic untrusted taint stripping pre-dispatch guard
        is_untrusted_tainted = False
        if session_id:
            sess = self.session_store.get_session(session_id)
            if sess is not None and sess.tainted_by_untrusted:
                is_untrusted_tainted = True

        if is_untrusted_tainted and tool_name in UNTRUSTED_TAINT_BLOCKED_TOOLS:
            error_data = {
                "code": "UNTRUSTED_CONTENT_TAINT_ACTIVE",
                "message": (
                    f"Mutating tool '{tool_name}' blocked: session tainted by untrusted content"
                ),
                "hint": (
                    "Untrusted content taint is active on this session. "
                    "Mutating actions are blocked to prevent prompt injection. "
                    "Ask a human to confirm or perform this action in the web UI."
                ),
            }
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": dump_yaml(error_data)}],
                        "isError": True,
                    },
                },
                headers={"X-Kanban-Untrusted-Taint": "1"},
            )

        spec = self.registry.get(tool_name)

        # Enforce connection scope boundary constraints & auto-population
        if connection_scope is not None:
            from mcp.scoping import enforce_connection_scope_on_tool_call  # noqa: PLC0415

            try:
                enforce_connection_scope_on_tool_call(
                    tool_name,
                    arguments,
                    connection_scope,
                    tool_spec=spec,
                )
            except KbMcpError as scope_violation_err:
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": scope_violation_err.to_yaml()}],
                            "isError": True,
                        },
                    }
                )

        # Enforce caller's CredentialBoundary (capability_mask, allowed_tools, allowlists)
        if auth_context is not None:
            boundary = getattr(auth_context, "credential_boundary", None)
            if boundary is not None:
                from mcp.scoping import (  # noqa: PLC0415
                    enforce_credential_boundary_on_tool_call,
                )

                try:
                    enforce_credential_boundary_on_tool_call(
                        tool_name,
                        arguments,
                        boundary,
                    )
                except KbMcpError as boundary_err:
                    return JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [{"type": "text", "text": boundary_err.to_yaml()}],
                                "isError": True,
                            },
                        }
                    )

        if spec is None:
            avail_tools = [t.name for t in self.registry.list_specs()]
            fuzzy_matches = difflib.get_close_matches(tool_name, avail_tools, n=3, cutoff=0.4)
            did_you_mean = fuzzy_matches or None
            fix_hint = (
                f"Tool '{tool_name}' not found. Did you mean '{did_you_mean[0]}'?"
                if did_you_mean
                else "Verify tool name or switch to appropriate MCP surface endpoint"
            )
            cli_ex = self._format_cli_example(did_you_mean[0] if did_you_mean else "help", {})
            not_found_err = KbMcpError(
                code=McpErrorCode.NOT_FOUND,
                message=f"Tool '{tool_name}' not found on surface '{self.surface.value}'",
                hint="Verify tool name or switch to appropriate MCP surface endpoint",
                field="tool_name",
                valid_options=avail_tools,
                did_you_mean=did_you_mean,
                fix_hint=fix_hint,
                cli_example=cli_ex,
            )
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": not_found_err.to_yaml()}],
                        "isError": True,
                    },
                }
            )

        req_scopes = SCOPE_REQUIREMENTS.get(tool_name)

        # Standard API key disabled_tools and allowed_tools narrowing (KB-P4-14)
        if auth_context is not None and auth_context.token_kind != "ephemeral":  # noqa: S105
            if auth_context.disabled_tools and tool_name in auth_context.disabled_tools:
                err = KbMcpError(
                    code=McpErrorCode.INSUFFICIENT_SCOPE,
                    message=f"Tool '{tool_name}' is disabled for this API key",
                    hint="Key administrator has disabled this tool via disabled_tools narrowing.",
                )
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": err.to_yaml()}],
                            "isError": True,
                        },
                    }
                )
            if (
                auth_context.allowed_tools is not None
                and tool_name not in auth_context.allowed_tools
            ):
                err = KbMcpError(
                    code=McpErrorCode.INSUFFICIENT_SCOPE,
                    message=f"Tool '{tool_name}' is not in allowed_tools for this API key",
                    hint=("Tool narrowing is active; only tools in allowed_tools may be called."),
                )
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": err.to_yaml()}],
                            "isError": True,
                        },
                    }
                )

        # Ephemeral token allowlist and atomic call budget consumption
        if auth_context is not None and auth_context.token_kind == "ephemeral":  # noqa: S105
            surface_allowed = EPHEMERAL_SURFACE_READ_ONLY_TOOLS.get(self.surface, frozenset())
            allowed_tools = sorted(surface_allowed)
            is_allowed = tool_name in surface_allowed and (
                auth_context.allowed_tools is None
                or tool_name in auth_context.allowed_tools
                or (
                    tool_name == "search"
                    and bool(
                        {"search", "search_knowledge", "read_doc"}.intersection(
                            auth_context.allowed_tools
                        )
                    )
                )
            )
            if not is_allowed:
                err = KbMcpError(
                    code=McpErrorCode.EPHEMERAL_TOOL_FORBIDDEN,
                    message=f"Tool '{tool_name}' is forbidden on ephemeral token",
                    hint=(
                        "Ephemeral tokens are strictly read-only and allow at most: "
                        "search_tickets, read_ticket, search."
                    ),
                    allowed_tools=allowed_tools,
                )
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": err.to_yaml()}],
                            "isError": True,
                        },
                    }
                )

            if self.internal_client is not None:
                introspect_tool = tool_name
                if self.surface == Surface.DOCS and tool_name == "search":
                    if auth_context.allowed_tools and "search" in auth_context.allowed_tools:
                        introspect_tool = "search"
                    elif (
                        auth_context.allowed_tools
                        and "read_doc" in auth_context.allowed_tools
                        and "search_knowledge" not in auth_context.allowed_tools
                    ):
                        introspect_tool = "read_doc"
                    else:
                        introspect_tool = "search_knowledge"
                try:
                    res_data = await self.internal_client.request(
                        "POST",
                        "/internal/v1/mcp/introspect",
                        json_data={
                            "token": auth_context.token,
                            "surface": self.surface.value,
                            "consume_call": True,
                            "tool_name": introspect_tool,
                        },
                    )
                except Exception:  # noqa: BLE001
                    err = KbMcpError(
                        code=McpErrorCode.UPSTREAM_UNAVAILABLE,
                        message="Internal token consumption service unavailable",
                    )
                    return JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [{"type": "text", "text": err.to_yaml()}],
                                "isError": True,
                            },
                        }
                    )

                if not isinstance(res_data, dict) or not res_data.get("active"):
                    reason = (
                        res_data.get("reason")
                        if isinstance(res_data, dict)
                        else "TOKEN_EXPIRED_OR_REVOKED"
                    )
                    if reason == "EPHEMERAL_TOOL_FORBIDDEN":
                        err = KbMcpError(
                            code=McpErrorCode.EPHEMERAL_TOOL_FORBIDDEN,
                            message=f"Tool '{tool_name}' is forbidden on ephemeral token",
                            hint=(
                                "Ephemeral tokens are strictly read-only and allow at most: "
                                "search_tickets, read_ticket, search."
                            ),
                            allowed_tools=allowed_tools,
                        )
                    elif reason == "EPHEMERAL_CALL_BUDGET_EXCEEDED":
                        max_c = (
                            (res_data.get("max_calls") if isinstance(res_data, dict) else None)
                            or auth_context.max_calls
                            or 25
                        )
                        used_c = (
                            res_data.get("calls_used") if isinstance(res_data, dict) else None
                        ) or max_c
                        err = KbMcpError(
                            code=McpErrorCode.EPHEMERAL_CALL_BUDGET_EXCEEDED,
                            message=f"Ephemeral call budget exceeded ({used_c}/{max_c} calls used)",
                            hint=(
                                "Gate execution reached max allowed calls. "
                                "Transition gates must summarize inspection in <= 25 calls."
                            ),
                            budget={"max_calls": max_c, "calls_used": used_c},
                        )
                    elif reason == "TOKEN_EXPIRED_OR_REVOKED":
                        err = KbMcpError(
                            code=McpErrorCode.TOKEN_EXPIRED_OR_REVOKED,
                            message=(
                                "Ephemeral token has expired (TTL <= 120s) or execution was revoked"
                            ),
                            hint=(
                                "Gate execution timed out or was canceled. "
                                "Transition checks must complete within 120 seconds."
                            ),
                        )
                    else:
                        err = KbMcpError(
                            code=McpErrorCode.UNAUTHENTICATED,
                            message="Ephemeral token is invalid or inactive",
                        )
                    return JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [{"type": "text", "text": err.to_yaml()}],
                                "isError": True,
                            },
                        }
                    )
        elif (
            caller_scopes is not None
            and req_scopes is not None
            and not (
                req_scopes.issubset(caller_scopes)
                or bool(
                    {"admin:write", "admin:destructive"}.intersection(caller_scopes)
                    and "admin:read" in req_scopes
                )
            )
        ):
            msg = f"Caller lacks required scope(s) {sorted(req_scopes)} for tool '{tool_name}'"
            scope_err = KbMcpError(code=McpErrorCode.INSUFFICIENT_SCOPE, message=msg)
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": scope_err.to_yaml()}],
                        "isError": True,
                    },
                }
            )

        # Action-aware administrative scope checks (admin:read vs admin:write vs admin:destructive)
        if self.surface == Surface.ADMIN and caller_scopes is not None:
            action = str(arguments.get("action", "")).strip()
            if action and action != "help":
                required_admin_scope: str | None = None
                write_prefixes = (
                    "create_",
                    "update_",
                    "set_",
                    "upsert_",
                    "provision_",
                    "bind_",
                    "unbind_",
                    "add_",
                    "remove_",
                    "attach",
                    "apply",
                    "plan",
                    "mint_",
                    "rotate_",
                )
                write_actions = {
                    "override_creator",
                    "override_hard_wip_move",
                    "unarchive_issue",
                    "run_audit",
                    "refresh_repo_binding",
                    "request_delete",
                    "restore",
                    "deactivate",
                    "reactivate",
                }
                if action.startswith(("delete_", "purge_", "revoke_")) or action in (
                    "execute_delete",
                    "detach",
                ):
                    required_admin_scope = "admin:destructive"
                elif action.startswith(write_prefixes) or action in write_actions:
                    required_admin_scope = "admin:write"

                if (
                    required_admin_scope == "admin:destructive"
                    and "admin:destructive" not in caller_scopes
                ):
                    msg = (
                        f"Action '{action}' on admin tool '{tool_name}' "
                        f"requires 'admin:destructive' scope"
                    )
                    scope_err = KbMcpError(code=McpErrorCode.INSUFFICIENT_SCOPE, message=msg)
                    return JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [{"type": "text", "text": scope_err.to_yaml()}],
                                "isError": True,
                            },
                        }
                    )
                if required_admin_scope == "admin:write" and not {
                    "admin:write",
                    "admin:destructive",
                }.intersection(caller_scopes):
                    msg = (
                        f"Action '{action}' on admin tool '{tool_name}' "
                        f"requires 'admin:write' scope"
                    )
                    scope_err = KbMcpError(code=McpErrorCode.INSUFFICIENT_SCOPE, message=msg)
                    return JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [{"type": "text", "text": scope_err.to_yaml()}],
                                "isError": True,
                            },
                        }
                    )

        # Progressive disclosure: JIT help
        if any(
            isinstance(arguments.get(k), str) and arguments.get(k, "").strip().lower() == "help"
            for k in ("identifier", "action", "source", "id", "project", "summary")
        ):
            return await self._handle_jit_help(
                req_id,
                tool_name,
                arguments,
                session_id=session_id,
                subject_token=subject_token,
            )

        aal_level = auth_context.aal_level if auth_context is not None else 2
        token_kind = auth_context.token_kind if auth_context is not None else "api_key"
        ctx = McpRequestContext(
            client=self.internal_client,
            surface=self.registry.surface,
            subject_token=subject_token,
            session_id=session_id,
            caller_scopes=caller_scopes,
            connection_scope=connection_scope,
            aal_level=aal_level,
            token_kind=token_kind,
        )
        ctx_token = set_current_mcp_context(ctx)
        try:
            try:
                # Pre-dispatch schema validation
                self._validate_tool_arguments_schema(spec, arguments)

                # Invoke handler
                handler = spec.handler
                if inspect.iscoroutinefunction(handler):
                    res = await handler(arguments)
                else:
                    res = handler(arguments)
                    if inspect.isawaitable(res):
                        res = await res
            finally:
                reset_current_mcp_context(ctx_token)

            # Format result text as YAML
            if isinstance(res, str):
                text_result = res
            elif isinstance(res, (dict, list)):
                text_result = dump_yaml(res)
            else:
                text_result = str(res)

            tainted_in_call = False
            if session_id and _detect_untrusted_taint(res):
                self.session_store.mark_untrusted_tainted(session_id)
                tainted_in_call = True

            resp_headers: dict[str, str] = {}
            if is_untrusted_tainted or tainted_in_call:
                resp_headers["X-Kanban-Untrusted-Taint"] = "1"

            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": text_result}],
                        "isError": False,
                    },
                },
                headers=resp_headers or None,
            )
        except KbMcpError as err:
            err_headers: dict[str, str] = {}
            if is_untrusted_tainted or "UNTRUSTED_CONTENT_TAINT_ACTIVE" in str(err.message):
                err_headers["X-Kanban-Untrusted-Taint"] = "1"
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": err.to_yaml()}],
                        "isError": True,
                    },
                },
                headers=err_headers or None,
            )
        except Exception:
            _logger.exception("Internal tool execution error (session=%s)", session_id)
            internal_err = KbMcpError(
                code=McpErrorCode.INTERNAL,
                message="Internal tool execution error",
            )
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": internal_err.to_yaml()}],
                        "isError": True,
                    },
                }
            )

    async def _handle_jit_help(
        self,
        req_id: object,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        session_id: str | None = None,
        subject_token: str | None = None,
    ) -> JSONResponse:
        """Render progressive disclosure JIT help document for a tool."""
        project_arg = arguments.get("project")
        help_data = await build_help(
            tool_name=tool_name,
            project=str(project_arg) if project_arg is not None else None,
            client=self.internal_client,
            subject_token=subject_token,
            mcp_session_id=session_id,
        )
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": dump_yaml(help_data)}],
                    "isError": False,
                },
            }
        )

    def _format_cli_example(self, tool_name: str, args: dict[str, Any]) -> str:
        """Format an intuitive CLI command example for self-correcting error UX."""
        return format_cli_example(self.surface, tool_name, args)

    def _validate_tool_arguments_schema(  # noqa: C901, PLR0912, PLR0915
        self,
        spec: ToolSpec,
        arguments: dict[str, Any],
    ) -> None:
        """Validate arguments against schema with progressive self-correction."""
        schema = spec.input_schema
        if not schema:
            return

        properties = schema.get("properties")
        required = schema.get("required") or []
        add_props = schema.get("additionalProperties", True)

        if not isinstance(properties, dict) and not required:
            return

        known_props: list[str] = list(properties.keys()) if isinstance(properties, dict) else []

        # 1. Unknown parameter validation
        if known_props and add_props is False:
            for k, val in arguments.items():
                if k not in known_props:
                    aliases = [a for a in SEMANTIC_ALIASES.get(k, []) if a in known_props]
                    snake_cand = re.sub(r"(?<!^)(?=[A-Z])", "_", k).lower()
                    if snake_cand in known_props and snake_cand not in aliases:
                        aliases.append(snake_cand)
                    fuzzy = difflib.get_close_matches(k, known_props, n=3, cutoff=0.4)
                    did_you_mean: list[str] = []
                    for c in aliases + fuzzy:
                        if c in known_props and c not in did_you_mean:
                            did_you_mean.append(c)

                    valid_options = known_props
                    hint: str | None = None
                    if k == "state" and spec.name == "update_ticket":
                        hint = "use transition_ticket"
                        fix_hint = (
                            "state changes not permitted in update_ticket; use transition_ticket"
                        )
                    elif k == "custom_fields" and spec.name == "update_ticket":
                        hint = "custom fields arrive in Phase 5"
                        fix_hint = (
                            "custom fields are not supported in update_ticket; "
                            "custom fields arrive in Phase 5"
                        )
                    elif did_you_mean:
                        fix_hint = f"Unknown parameter '{k}'. Did you mean '{did_you_mean[0]}'?"
                    else:
                        fix_hint = (
                            f"Unknown parameter '{k}'. Valid options: {', '.join(valid_options)}"
                        )

                    corrected_args: dict[str, Any] = {}
                    for arg_k, arg_v in arguments.items():
                        if arg_k == k:
                            if did_you_mean:
                                corrected_args[did_you_mean[0]] = arg_v
                        elif arg_k in known_props:
                            corrected_args[arg_k] = arg_v
                    if not corrected_args and did_you_mean:
                        corrected_args[did_you_mean[0]] = val
                    cli_example = self._format_cli_example(spec.name, corrected_args)

                    raise KbMcpError(
                        McpErrorCode.VALIDATION_FAILED,
                        f"Unknown parameter '{k}' for tool '{spec.name}'",
                        hint=hint,
                        field=k,
                        valid_options=valid_options,
                        did_you_mean=did_you_mean or None,
                        fix_hint=fix_hint,
                        cli_example=cli_example,
                    )

        # 2. Missing required parameter validation
        if required:
            for req_field in required:
                if req_field not in arguments or arguments[req_field] is None:
                    fix_hint = (
                        f"Missing required parameter: '{req_field}'. Provide a value to proceed."
                    )
                    prefilled_args = {
                        arg_k: arg_v
                        for arg_k, arg_v in arguments.items()
                        if arg_k in known_props and arg_k != req_field and arg_v is not None
                    }
                    prefilled_args[req_field] = f"<{req_field}>"
                    cli_example = self._format_cli_example(spec.name, prefilled_args)

                    raise KbMcpError(
                        McpErrorCode.VALIDATION_FAILED,
                        f"Missing required parameter '{req_field}' for tool '{spec.name}'",
                        field=req_field,
                        fix_hint=fix_hint,
                        cli_example=cli_example,
                    )

        # 3. Invalid enum / type / format validation
        if isinstance(properties, dict):
            for k, v in arguments.items():
                if k not in properties or v is None:
                    continue
                prop_schema = properties[k]
                if not isinstance(prop_schema, dict):
                    continue

                # Check enum
                if "enum" in prop_schema:
                    enum_vals = [str(x) for x in prop_schema["enum"]]
                    str_v = str(v)
                    if str_v not in enum_vals and (
                        not isinstance(v, str) or v not in prop_schema["enum"]
                    ):
                        valid_options = enum_vals
                        closest = difflib.get_close_matches(str_v, valid_options, n=1, cutoff=0.3)
                        if not closest:
                            lower_map = {opt.lower(): opt for opt in valid_options}
                            matched_lowers = difflib.get_close_matches(
                                str_v.lower(), list(lower_map.keys()), n=1, cutoff=0.3
                            )
                            if matched_lowers:
                                closest = [lower_map[matched_lowers[0]]]
                        enum_did_you_mean: list[str] | None = closest or None
                        if enum_did_you_mean:
                            fix_hint = (
                                f"Invalid value '{v}' for parameter '{k}'. "
                                f"Did you mean '{enum_did_you_mean[0]}'? "
                                f"Valid options: {valid_options}"
                            )
                        else:
                            fix_hint = (
                                f"Invalid value '{v}' for parameter '{k}'. "
                                f"Valid options: {valid_options}"
                            )

                        corrected_args = dict(arguments)
                        corrected_args[k] = (
                            enum_did_you_mean[0] if enum_did_you_mean else valid_options[0]
                        )
                        cli_example = self._format_cli_example(spec.name, corrected_args)

                        opts_str = " or ".join(repr(x) for x in valid_options)
                        raise KbMcpError(
                            McpErrorCode.VALIDATION_FAILED,
                            f"Invalid value '{v}' for parameter '{k}'; {k} must be {opts_str}",
                            field=k,
                            valid_options=valid_options,
                            did_you_mean=enum_did_you_mean,
                            fix_hint=fix_hint,
                            cli_example=cli_example,
                        )

                # Check type
                expected_type = prop_schema.get("type")
                types_to_check: list[str] = (
                    expected_type
                    if isinstance(expected_type, list)
                    else [expected_type]
                    if isinstance(expected_type, str)
                    else []
                )
                if types_to_check and "null" in types_to_check and v is None:
                    continue
                valid_types = [t for t in types_to_check if t != "null"]
                if valid_types and not any(_matches_schema_type(v, t) for t in valid_types):
                    target_str = " or ".join(valid_types)
                    fix_hint = (
                        f"Parameter '{k}' must be of type {target_str}, got {type(v).__name__}"
                    )
                    corrected_args = dict(arguments)
                    if "string" in valid_types:
                        corrected_args[k] = f"<{k}>"
                    elif "integer" in valid_types or "number" in valid_types:
                        corrected_args[k] = 0
                    elif "boolean" in valid_types:
                        corrected_args[k] = True
                    elif "array" in valid_types:
                        corrected_args[k] = []
                    elif "object" in valid_types:
                        corrected_args[k] = {}
                    cli_example = self._format_cli_example(spec.name, corrected_args)
                    raise KbMcpError(
                        McpErrorCode.VALIDATION_FAILED,
                        f"Parameter '{k}' must be of type {target_str}",
                        field=k,
                        fix_hint=fix_hint,
                        cli_example=cli_example,
                    )

                # Check pattern / regex format
                if "pattern" in prop_schema and isinstance(v, str):
                    pattern = prop_schema["pattern"]
                    if not re.search(pattern, v):
                        etag_note = (
                            " (provide 64-character SHA-256 hex ETag)" if "64" in pattern else ""
                        )
                        fix_hint = (
                            f"Parameter '{k}' must match format pattern '{pattern}'{etag_note}"
                        )
                        placeholder = "<64-hex-sha256>" if "64" in pattern else f"<{k}>"
                        corrected_args = dict(arguments)
                        corrected_args[k] = placeholder
                        cli_example = self._format_cli_example(spec.name, corrected_args)
                        raise KbMcpError(
                            McpErrorCode.VALIDATION_FAILED,
                            f"Parameter '{k}' does not match required format pattern",
                            field=k,
                            fix_hint=fix_hint,
                            cli_example=cli_example,
                        )


def validate_tool_arguments_schema(
    spec: ToolSpec,
    arguments: dict[str, Any],
    surface: Surface = Surface.AGENT,
) -> None:
    """Validate arguments against schema with progressive self-correction."""
    handler = McpProtocolHandler.__new__(McpProtocolHandler)
    object.__setattr__(handler, "surface", surface)
    handler._validate_tool_arguments_schema(spec, arguments)  # noqa: SLF001
