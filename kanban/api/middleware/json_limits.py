# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Pure ASGI middleware enforcing body size, JSON depth, keys, and surrogates (KB-P3-AUDIT-11)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

from starlette.responses import Response

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

DEFAULT_MAX_BODY_BYTES: Final[int] = 2 * 1024 * 1024  # 2 MiB
LARGE_UPLOAD_MAX_BODY_BYTES: Final[int] = 25 * 1024 * 1024  # 25 MiB
MAX_JSON_DEPTH: Final[int] = 32
MAX_JSON_KEYS: Final[int] = 5000

SURROGATE_MIN: Final[int] = 0xD800
SURROGATE_MAX: Final[int] = 0xDFFF


class JsonLimitError(Exception):
    """Base class for JSON limits errors."""

    def __init__(self, code: str, title: str, status: int, detail: str) -> None:
        """Initialize error details."""
        super().__init__(detail)
        self.code = code
        self.title = title
        self.status = status
        self.detail = detail


class PayloadTooLargeLimitError(JsonLimitError):
    """Request body exceeds byte size ceiling."""

    def __init__(self, detail: str) -> None:
        """Initialize 413 Payload Too Large error."""
        super().__init__(
            code="PAYLOAD_TOO_LARGE",
            title="Payload Too Large",
            status=413,
            detail=detail,
        )


class JsonSurrogateLimitError(JsonLimitError):
    """JSON payload contains forbidden UTF-16 lone surrogate character."""

    def __init__(self, detail: str) -> None:
        """Initialize 422 Invalid UTF-8 Surrogate error."""
        super().__init__(
            code="INVALID_UTF8_SURROGATE",
            title="Invalid UTF-8 Surrogate",
            status=422,
            detail=detail,
        )


class JsonDepthLimitError(JsonLimitError):
    """JSON nesting depth exceeds ceiling."""

    def __init__(self, detail: str) -> None:
        """Initialize 422 JSON Depth Exceeded error."""
        super().__init__(
            code="JSON_DEPTH_EXCEEDED",
            title="JSON Depth Exceeded",
            status=422,
            detail=detail,
        )


class JsonKeysLimitError(JsonLimitError):
    """JSON total object keys count exceeds ceiling."""

    def __init__(self, detail: str) -> None:
        """Initialize 422 JSON Keys Exceeded error."""
        super().__init__(
            code="JSON_KEYS_EXCEEDED",
            title="JSON Keys Exceeded",
            status=422,
            detail=detail,
        )


class JsonSyntaxLimitError(JsonLimitError):
    """JSON syntax decode error."""

    def __init__(self, detail: str) -> None:
        """Initialize 422 Invalid JSON syntax error."""
        super().__init__(
            code="INVALID_JSON",
            title="Invalid JSON",
            status=422,
            detail=detail,
        )


def is_large_upload_path(path: str) -> bool:
    """Check if request path matches large attachment or import upload routes."""
    return (
        "/attachments" in path
        or "/imports" in path
        or path.startswith(("/api/v1/attachments", "/api/v1/admin/imports"))
    )


def _scan_json_depth_iterative(text: str) -> bool:
    """Scan JSON text iteratively to ensure bracket nesting depth does not exceed ceiling.

    Runs in O(N) time and O(1) stack space before full AST deserialization.
    """
    in_string = False
    escape = False
    depth = 0

    for char in text:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in ("{", "["):
            depth += 1
            if depth > MAX_JSON_DEPTH:
                return False
        elif char in ("}", "]") and depth > 0:
            depth -= 1

    return True


def _validate_json_structure_iterative(root: Any) -> None:  # noqa: C901, PLR0912, ANN401
    """Validate parsed JSON structure depth, total keys, and lone surrogates using a heap stack."""
    stack: list[tuple[Any, int]] = [(root, 1)]
    total_keys = 0

    while stack:
        node, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            depth_msg = f"JSON nesting depth exceeds maximum allowed depth of {MAX_JSON_DEPTH}"
            raise JsonDepthLimitError(depth_msg)

        if isinstance(node, dict):
            total_keys += len(node)
            if total_keys > MAX_JSON_KEYS:
                keys_msg = f"JSON object key count ({total_keys}) exceeds maximum ({MAX_JSON_KEYS})"
                raise JsonKeysLimitError(keys_msg)

            for k, v in node.items():
                if isinstance(k, str):
                    for ch in k:
                        if SURROGATE_MIN <= ord(ch) <= SURROGATE_MAX:
                            surr_k_msg = (
                                "JSON key contains forbidden UTF-16 lone surrogate character"
                            )
                            raise JsonSurrogateLimitError(surr_k_msg)
                if isinstance(v, str):
                    for ch in v:
                        if SURROGATE_MIN <= ord(ch) <= SURROGATE_MAX:
                            surr_v_msg = (
                                "JSON value contains forbidden UTF-16 lone surrogate character"
                            )
                            raise JsonSurrogateLimitError(surr_v_msg)
                elif isinstance(v, (dict, list)):
                    stack.append((v, depth + 1))

        elif isinstance(node, list):
            for item in node:
                if isinstance(item, str):
                    for ch in item:
                        if SURROGATE_MIN <= ord(ch) <= SURROGATE_MAX:
                            surr_item_msg = (
                                "JSON array item contains forbidden UTF-16 lone surrogate character"
                            )
                            raise JsonSurrogateLimitError(surr_item_msg)
                elif isinstance(item, (dict, list)):
                    stack.append((item, depth + 1))

        elif isinstance(node, str):
            for ch in node:
                if SURROGATE_MIN <= ord(ch) <= SURROGATE_MAX:
                    surr_str_msg = "JSON string contains forbidden UTF-16 lone surrogate character"
                    raise JsonSurrogateLimitError(surr_str_msg)


def _make_problem_response(exc: JsonLimitError) -> Response:
    """Construct canonical RFC 7807 problem response."""
    payload = {
        "type": f"urn:kanban:problem:{exc.code}",
        "title": exc.title,
        "status": exc.status,
        "code": exc.code,
        "detail": exc.detail,
    }
    return Response(
        content=json.dumps(payload).encode("utf-8"),
        status_code=exc.status,
        media_type="application/problem+json",
    )


class JsonLimitsMiddleware:
    """Pure ASGI middleware enforcing streaming body size caps and JSON structural bounds."""

    def __init__(self, app: ASGIApp) -> None:
        """Initialize middleware wrapping next ASGI application."""
        self.app = app

    async def __call__(  # noqa: C901, PLR0911, PLR0912, PLR0915
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Process ASGI HTTP request enforcing size, depth, keys, and surrogate limits."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        max_bytes = (
            LARGE_UPLOAD_MAX_BODY_BYTES if is_large_upload_path(path) else DEFAULT_MAX_BODY_BYTES
        )

        content_type = ""
        content_length: int | None = None
        for raw_k, raw_v in scope.get("headers", []):
            k_lower = raw_k.lower()
            if k_lower == b"content-type":
                content_type = raw_v.decode("latin1", errors="replace").strip().lower()
            elif k_lower == b"content-length":
                try:
                    content_length = int(raw_v.decode("ascii").strip())
                except ValueError:
                    content_length = None

        if content_length is not None and content_length > max_bytes:
            cl_err_msg = (
                f"Request content-length ({content_length} bytes) exceeds {max_bytes} bytes"
            )
            resp = _make_problem_response(PayloadTooLargeLimitError(cl_err_msg))
            await resp(scope, receive, send)
            return

        media_type = content_type.split(";")[0].strip()
        is_json = media_type == "application/json" or media_type.endswith("+json")

        if not is_json:
            bytes_received = 0

            async def limited_streaming_receive() -> Message:
                nonlocal bytes_received
                msg = await receive()
                if msg["type"] == "http.request":
                    chunk = msg.get("body", b"")
                    bytes_received += len(chunk)
                    if bytes_received > max_bytes:
                        stream_msg = (
                            f"Streaming request body exceeded maximum limit of {max_bytes} bytes"
                        )
                        raise PayloadTooLargeLimitError(stream_msg)
                return msg

            try:
                await self.app(scope, limited_streaming_receive, send)
            except PayloadTooLargeLimitError as err:
                resp = _make_problem_response(err)
                await resp(scope, receive, send)
            return

        chunks: list[bytes] = []
        total_bytes = 0
        more_body = True

        while more_body:
            msg = await receive()
            if msg["type"] != "http.request":
                await self.app(scope, receive, send)
                return

            chunk = msg.get("body", b"")
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                body_limit_msg = f"Request body size exceeded limit of {max_bytes} bytes"
                resp = _make_problem_response(PayloadTooLargeLimitError(body_limit_msg))
                await resp(scope, receive, send)
                return

            chunks.append(chunk)
            more_body = msg.get("more_body", False)

        raw_body = b"".join(chunks)

        if not raw_body.strip():
            body_sent = False

            async def empty_receive() -> Message:
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {"type": "http.request", "body": raw_body, "more_body": False}
                return await receive()

            await self.app(scope, empty_receive, send)
            return

        try:
            decoded_text = raw_body.decode("utf-8", errors="surrogatepass")
        except UnicodeDecodeError as err:
            decode_msg = f"Request body is not valid UTF-8: {err}"
            resp = _make_problem_response(JsonSyntaxLimitError(decode_msg))
            await resp(scope, receive, send)
            return

        for ch in decoded_text:
            if SURROGATE_MIN <= ord(ch) <= SURROGATE_MAX:
                surr_msg = "JSON payload contains forbidden UTF-16 lone surrogate character"
                resp = _make_problem_response(JsonSurrogateLimitError(surr_msg))
                await resp(scope, receive, send)
                return

        if not _scan_json_depth_iterative(decoded_text):
            depth_err_msg = f"JSON nesting depth exceeds maximum allowed depth of {MAX_JSON_DEPTH}"
            resp = _make_problem_response(JsonDepthLimitError(depth_err_msg))
            await resp(scope, receive, send)
            return

        try:
            parsed_data = json.loads(decoded_text)
        except (json.JSONDecodeError, ValueError) as err:
            parse_msg = f"Failed to parse JSON request body: {err}"
            resp = _make_problem_response(JsonSyntaxLimitError(parse_msg))
            await resp(scope, receive, send)
            return

        try:
            _validate_json_structure_iterative(parsed_data)
        except JsonLimitError as err:
            resp = _make_problem_response(err)
            await resp(scope, receive, send)
            return

        body_sent = False

        async def validated_receive() -> Message:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": raw_body, "more_body": False}
            return await receive()

        await self.app(scope, validated_receive, send)
