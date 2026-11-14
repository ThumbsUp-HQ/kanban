# Copyright 2026 Kanban Platform Contributors
"""Streamable HTTP JSON-RPC 2.0 protocol engine and session store for MCP mounts."""

from __future__ import annotations

import contextlib
import inspect
import json
import logging
import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Protocol, runtime_checkable

from starlette.responses import JSONResponse, Response

from mcp.auth import SCOPE_REQUIREMENTS, hash_mcp_api_key
from mcp.context import (
    McpRequestContext,
    reset_current_mcp_context,
    set_current_mcp_context,
)
from mcp.errors import KbMcpError, McpErrorCode
from mcp.help import build_help
from mcp.yaml_out import dump_yaml

if TYPE_CHECKING:
    from collections.abc import Callable

    from starlette.requests import Request

    from mcp.internal_client import KanbanApiClient
    from mcp.registry import Surface, ToolRegistry
    from mcp.settings import McpSettings

__all__ = [
    "PROTOCOL_VERSION",
    "InMemorySessionStore",
    "McpProtocolHandler",
    "Session",
    "SessionStore",
]

PROTOCOL_VERSION: Final[str] = "2025-06-18"

_logger: Final[logging.Logger] = logging.getLogger(__name__)


@dataclass(frozen=True)
class Session:
    """Active MCP protocol session associated with a specific surface."""

    session_id: str
    surface: Surface
    created_at_s: float
    last_seen_s: float
    token_sha256: bytes | None = None


@runtime_checkable
class SessionStore(Protocol):
    """Protocol for MCP session lifecycle management."""

    def create_session(self, surface: Surface, *, token_sha256: bytes | None = None) -> Session:
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

    def create_session(self, surface: Surface, *, token_sha256: bytes | None = None) -> Session:
        """Create and store a new session with URL-safe random ID, evicting oldest if full."""
        now = self._time_provider()
        session_id = secrets.token_urlsafe(32)
        session = Session(
            session_id=session_id,
            surface=surface,
            created_at_s=now,
            last_seen_s=now,
            token_sha256=token_sha256,
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
            refreshed = Session(
                session_id=session.session_id,
                surface=session.surface,
                created_at_s=session.created_at_s,
                last_seen_s=now,
            )
            self._sessions[session_id] = refreshed
            self._sessions.move_to_end(session_id)

    def delete_session(self, session_id: str) -> bool:
        """Terminate and remove a session from storage."""
        return self._sessions.pop(session_id, None) is not None


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
        if request.method == "GET":
            return Response(
                "Standalone SSE streams are not supported; use Streamable HTTP POST",
                status_code=405,
                headers={"Allow": "POST, DELETE"},
            )

        origin = request.headers.get("origin")
        if origin and self.settings.allowed_origins and origin not in self.settings.allowed_origins:
            return Response("Forbidden Origin", status_code=403)

        if request.method not in ("POST", "DELETE"):
            return Response(
                f"Method {request.method} not allowed",
                status_code=405,
                headers={"Allow": "POST, DELETE"},
            )

        proto_ver = request.headers.get("mcp-protocol-version")
        if proto_ver is not None and proto_ver != PROTOCOL_VERSION:
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

    async def _process_valid_payload(
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
            return await self._handle_initialize(req_id, request=request)

        session_id = request.headers.get("mcp-session-id")
        if not session_id:
            return Response("Session not found or expired; please re-initialize", status_code=404)

        session = self.session_store.get_session(session_id)
        if session is None:
            return Response("Session not found or expired; please re-initialize", status_code=404)

        raw_auth = request.headers.get("x-kb-subject-token") or request.headers.get("authorization")
        subject_token = (
            raw_auth[7:].strip()
            if raw_auth and raw_auth.lower().startswith("bearer ")
            else raw_auth
        )

        current_token_sha256 = getattr(request.state, "mcp_token_sha256", None)
        if current_token_sha256 is None and subject_token:
            current_token_sha256 = hash_mcp_api_key(subject_token)

        # Enforce session token binding: if session was bound to a token, token must match
        if (
            session.token_sha256 is not None
            and current_token_sha256 is not None
            and session.token_sha256 != current_token_sha256
        ):
            return Response("Session bound to different token", status_code=404)

        caller_scopes = getattr(request.state, "mcp_scopes", None)
        if caller_scopes is None and "x-kb-scopes" in request.headers:
            caller_scopes = frozenset(
                s.strip() for s in request.headers["x-kb-scopes"].split(",") if s.strip()
            )

        mcp_auth = getattr(request.state, "mcp_auth", None)
        aal_level = getattr(mcp_auth, "aal_level", 2) if mcp_auth else 2
        if "x-kb-aal-level" in request.headers:
            with contextlib.suppress(ValueError):
                aal_level = int(request.headers["x-kb-aal-level"])
        token_kind = getattr(mcp_auth, "token_kind", "api_key") if mcp_auth else "api_key"

        return await self._dispatch_method(
            method,
            req_id,
            params,
            session_id=session_id,
            subject_token=subject_token,
            caller_scopes=caller_scopes,
            aal_level=aal_level,
            token_kind=token_kind,
        )

    def _handle_delete_session(self, request: Request) -> Response:
        session_id = request.headers.get("mcp-session-id")
        if not session_id or not self.session_store.delete_session(session_id):
            return Response("Session not found", status_code=404)
        return Response(status_code=204)

    async def _handle_initialize(
        self, req_id: object, *, request: Request | None = None
    ) -> Response:
        token_sha256: bytes | None = None
        if request is not None:
            token_sha256 = getattr(request.state, "mcp_token_sha256", None)
            if token_sha256 is None:
                raw_auth = request.headers.get("x-kb-subject-token") or request.headers.get(
                    "authorization"
                )
                subject_token = (
                    raw_auth[7:].strip()
                    if raw_auth and raw_auth.lower().startswith("bearer ")
                    else raw_auth
                )
                if subject_token:
                    token_sha256 = hash_mcp_api_key(subject_token)

        session = self.session_store.create_session(self.surface, token_sha256=token_sha256)
        result: dict[str, Any] = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "tools": {
                    "listChanged": False,
                },
            },
            "serverInfo": {
                "name": f"kanban-mcp-{self.surface.value}",
                "version": "0.0.0",
            },
        }
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
        aal_level: int = 2,
        token_kind: str | None = "api_key",  # noqa: S107
    ) -> Response:
        # Notifications (no id)
        if req_id is None:
            return Response(status_code=204)

        if method == "ping":
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})

        if method == "tools/list":
            return self._handle_tools_list(req_id, caller_scopes=caller_scopes)

        if method == "tools/call":
            return await self._handle_tools_call(
                req_id,
                params,
                session_id=session_id,
                subject_token=subject_token,
                caller_scopes=caller_scopes,
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
        self, req_id: object, *, caller_scopes: frozenset[str] | None = None
    ) -> JSONResponse:
        specs = self.registry.list_specs()
        if caller_scopes is not None:
            specs = [
                s
                for s in specs
                if (
                    SCOPE_REQUIREMENTS.get(s.name) is None
                    or SCOPE_REQUIREMENTS[s.name].issubset(caller_scopes)
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

    async def _handle_tools_call(  # noqa: C901, PLR0911, PLR0912, PLR0913
        self,
        req_id: object,
        params: object,
        *,
        session_id: str | None = None,
        subject_token: str | None = None,
        caller_scopes: frozenset[str] | None = None,
        aal_level: int = 2,
        token_kind: str | None = "api_key",  # noqa: S107
    ) -> JSONResponse:
        validated = self._validate_tools_call_params(req_id, params)
        if isinstance(validated, JSONResponse):
            return validated

        tool_name, arguments = validated

        spec = self.registry.get(tool_name)
        if spec is None:
            err = KbMcpError(
                code=McpErrorCode.NOT_FOUND,
                message=f"Tool '{tool_name}' not found on surface '{self.surface.value}'",
                hint="Verify tool name or switch to appropriate MCP surface endpoint",
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

        # Check required scopes
        req_scopes = SCOPE_REQUIREMENTS.get(tool_name)
        if (
            caller_scopes is not None
            and req_scopes is not None
            and not req_scopes.issubset(caller_scopes)
        ):
            msg = f"Caller lacks required scope(s) {sorted(req_scopes)} for tool '{tool_name}'"
            err = KbMcpError(code=McpErrorCode.INSUFFICIENT_SCOPE, message=msg)
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

        # Progressive disclosure: JIT help
        if arguments.get("identifier") == "help" or arguments.get("action") == "help":
            return await self._handle_jit_help(
                req_id,
                tool_name,
                arguments,
                session_id=session_id,
                subject_token=subject_token,
            )

        ctx = McpRequestContext(
            client=self.internal_client,
            surface=self.registry.surface,
            subject_token=subject_token,
            session_id=session_id,
            caller_scopes=caller_scopes,
            aal_level=aal_level,
            token_kind=token_kind,
        )
        ctx_token = set_current_mcp_context(ctx)
        try:
            try:
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

            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": text_result}],
                        "isError": False,
                    },
                }
            )
        except KbMcpError as err:
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
