"""Pure ASGI Request-ID middleware, contextvar propagation, and log filter (S3.4)."""

from __future__ import annotations

import contextlib
import logging
import re
import uuid
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, MutableMapping

    from starlette.types import ASGIApp, Receive, Scope, Send

_key_revocation_listeners: list[Callable[[uuid.UUID], Any]] = []


def register_mcp_key_revocation_listener(listener: Callable[[uuid.UUID], Any]) -> None:
    """Register an in-process listener invoked when an MCP key is revoked."""
    if listener not in _key_revocation_listeners:
        _key_revocation_listeners.append(listener)


def notify_mcp_key_revoked(key_id: uuid.UUID) -> None:
    """Notify registered in-process listeners to evict a revoked MCP key."""
    for listener in _key_revocation_listeners:
        with contextlib.suppress(Exception):
            listener(key_id)


_REQUEST_ID_REGEX = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_ACTOR_SAFE_CHARS_REGEX = re.compile(r"[^A-Za-z0-9_.:@+-]")
_MAX_ACTOR_LEN = 128
_ZERO_UUID = uuid.UUID(int=0)

_REQUEST_ID_CTX: ContextVar[str] = ContextVar("request_id", default="")
_LOG_USER_CTX: ContextVar[str] = ContextVar("log_user", default="")


def get_request_id() -> str:
    """Return the active request-id for the current task/coroutine, or generate a fallback."""
    val = _REQUEST_ID_CTX.get()
    return val or uuid.uuid4().hex


def _normalize_actor(actor: str | None) -> str:
    """Normalize an actor label into a single-line bracket-safe identifier."""
    if not actor:
        return "-"
    cleaned = _ACTOR_SAFE_CHARS_REGEX.sub("_", str(actor).strip())
    if not cleaned:
        return "-"
    return cleaned[:_MAX_ACTOR_LEN]


def get_log_user() -> str:
    """Return the active user/principal attribution label for the current task, or '-'."""
    val = _LOG_USER_CTX.get()
    return val or "-"


def set_log_user(actor: str | None) -> Token[str]:
    """Bind the active user/principal attribution label in contextvar storage."""
    return _LOG_USER_CTX.set(_normalize_actor(actor))


def reset_log_user(token: Token[str]) -> None:
    """Reset the active user/principal attribution label to its previous token state."""
    _LOG_USER_CTX.reset(token)


def _stringify_non_zero_id(ident: uuid.UUID | str | None) -> str:
    """Return string representation of a principal/agent UUID if non-empty and non-zero."""
    if ident is None:
        return ""
    if isinstance(ident, uuid.UUID):
        return "" if ident == _ZERO_UUID else str(ident)
    s_val = str(ident).strip()
    return "" if (not s_val or s_val == str(_ZERO_UUID)) else s_val


def format_log_actor(
    principal_id: uuid.UUID | str | None,
    *,
    agent_principal_id: uuid.UUID | str | None = None,
    username: str | None = None,
    mfa_pending: bool = False,
) -> str:
    """Format a canonical, non-PII actor attribution string for log correlation."""
    base = _stringify_non_zero_id(principal_id)

    if not base and username:
        u_clean = _normalize_actor(username)
        if u_clean != "-":
            base = f"login:{u_clean}"

    if not base:
        return "-"

    agent_str = _stringify_non_zero_id(agent_principal_id)
    if agent_str:
        base = f"{base}@agent:{agent_str}"

    if mfa_pending:
        base = f"{base}:mfa_pending"

    return _normalize_actor(base)


def bind_request_log_user(request_or_scope: object, actor: str | None) -> str:
    """Bind the normalized actor to both the active ContextVar and request/scope state."""
    normalized = _normalize_actor(actor)
    _LOG_USER_CTX.set(normalized)
    if isinstance(request_or_scope, dict):
        state = request_or_scope.setdefault("state", {})
        if isinstance(state, dict):
            state["log_user"] = normalized
    else:
        state_obj = getattr(request_or_scope, "state", None)
        if state_obj is not None:
            with contextlib.suppress(AttributeError):
                state_obj.log_user = normalized
    return normalized


class RequestIdFilter(logging.Filter):
    """Logging filter that injects the active request_id and log_user into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add request_id and log_user attributes to record."""
        record.request_id = get_request_id()
        record.log_user = get_log_user()
        return True


class RequestIdMiddleware:
    """Pure ASGI middleware managing inbound and outbound X-Request-ID headers.

    Validates that inbound headers strictly match '^[A-Za-z0-9-]{8,64}$' without
    Unicode, whitespace, control characters, or invalid lengths. Non-conforming or
    missing IDs are replaced with a clean 32-character hexadecimal UUIDv4.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize with inner ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:  # noqa: C901
        """Intercept HTTP scopes to establish and echo request-id and reset user context."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound_id: str | None = None
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name.lower() == b"x-request-id":
                try:
                    candidate = raw_value.decode("ascii")
                    if _REQUEST_ID_REGEX.match(candidate):
                        inbound_id = candidate
                except UnicodeDecodeError:
                    pass
                break

        assigned_id = inbound_id if inbound_id is not None else uuid.uuid4().hex

        token = _REQUEST_ID_CTX.set(assigned_id)
        user_token = _LOG_USER_CTX.set("anon")
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = assigned_id
        scope["state"]["log_user"] = "anon"

        async def send_with_request_id(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                # Add X-Request-ID header to response if not already present
                if not any(name.lower() == b"x-request-id" for name, _ in raw_headers):
                    raw_headers.append((b"x-request-id", assigned_id.encode("ascii")))
                # Add X-KB-AAL2-Expires-At header if present in scope state
                aal2_exp = scope.get("state", {}).get("aal2_expires_at")
                hdr_match = any(name.lower() == b"x-kb-aal2-expires-at" for name, _ in raw_headers)
                if aal2_exp and not hdr_match:
                    exp_val = (
                        aal2_exp.isoformat()
                        if hasattr(aal2_exp, "isoformat")
                        else str(aal2_exp)
                    )
                    raw_headers.append((b"x-kb-aal2-expires-at", exp_val.encode("ascii")))
                message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _LOG_USER_CTX.reset(user_token)
            _REQUEST_ID_CTX.reset(token)
