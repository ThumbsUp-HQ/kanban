# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Recursion guard middleware enforcing X-Kanban-Script-Depth limits (KB-P5-14, S13.3)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Final

from starlette.responses import Response

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Receive, Scope, Send

_BLOCKED_PATH_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^/api/v1/issues/[^/]+/custom-fields/[^/]+/execute(?:/.*)?$"),
    re.compile(r"^/api/v1/issues/[^/]+/transitions(?:/.*)?$"),
    re.compile(r"^/api/v1/projects/[^/]+/custom-fields/test-execute(?:/.*)?$"),
    re.compile(r"^/api/v1/projects/[^/]+/workflow-hooks/dry-run(?:/.*)?$"),
    re.compile(r"^/mcp(?:/.*)?$"),
)


class ScriptDepthGuardMiddleware:
    """Pure ASGI middleware enforcing X-Kanban-Script-Depth recursion limits.

    Any inbound request bearing X-Kanban-Script-Depth with a non-digit value
    or integer >= 1 attempting to execute scripts, trigger transitions, or access
    MCP surfaces is rejected immediately with HTTP 409 SCRIPT_RECURSION_BLOCKED.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize the script depth guard middleware wrapping the ASGI app."""
        self.app = app

    async def __call__(  # noqa: C901
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Process incoming ASGI request, enforcing script depth policy."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_headers = scope.get("headers", [])
        depth_val: str | None = None
        for k, v in raw_headers:
            if k.lower() == b"x-kanban-script-depth":
                try:
                    depth_val = v.decode("ascii").strip()
                except UnicodeDecodeError:
                    depth_val = "invalid"
                break

        if "state" not in scope:
            scope["state"] = {}

        if depth_val is None:
            scope["state"]["script_depth"] = 0
            await self.app(scope, receive, send)
            return

        # Check if depth is valid non-negative integer
        is_blocked = False
        depth_int = 0
        if not depth_val.isdigit():
            is_blocked = True
            depth_int = 1
        else:
            depth_int = int(depth_val)
            if depth_int >= 1:
                is_blocked = True

        scope["state"]["script_depth"] = depth_int

        if is_blocked:
            path = scope.get("path", "")
            for pattern in _BLOCKED_PATH_PATTERNS:
                if pattern.match(path):
                    problem_payload = {
                        "type": "urn:kanban:problem:SCRIPT_RECURSION_BLOCKED",
                        "title": "Script Recursion Blocked",
                        "status": 409,
                        "code": "SCRIPT_RECURSION_BLOCKED",
                        "detail": (
                            f"Nested script execution or MCP access blocked at script depth "
                            f"'{depth_val}'"
                        ),
                    }
                    body = json.dumps(problem_payload).encode("utf-8")
                    resp = Response(
                        content=body,
                        status_code=409,
                        media_type="application/problem+json",
                    )
                    await resp(scope, receive, send)
                    return

        await self.app(scope, receive, send)
