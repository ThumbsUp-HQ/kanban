"""Pure ASGI Request-ID middleware, contextvar propagation, and log filter (S3.4)."""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from starlette.types import ASGIApp, Receive, Scope, Send

_REQUEST_ID_REGEX = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_REQUEST_ID_CTX: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the active request-id for the current task/coroutine, or generate a fallback."""
    val = _REQUEST_ID_CTX.get()
    return val or uuid.uuid4().hex


class RequestIdFilter(logging.Filter):
    """Logging filter that injects the active request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add request_id attribute to record."""
        record.request_id = get_request_id()
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

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Intercept HTTP scopes to establish and echo request-id."""
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
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = assigned_id

        async def send_with_request_id(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers", []))
                # Add X-Request-ID header to response if not already present
                if not any(name.lower() == b"x-request-id" for name, _ in raw_headers):
                    raw_headers.append((b"x-request-id", assigned_id.encode("ascii")))
                    message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _REQUEST_ID_CTX.reset(token)
