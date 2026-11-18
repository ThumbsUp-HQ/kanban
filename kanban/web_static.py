"""ASGI application for serving pre-compressed single page applications.

Implements encoding negotiation (Brotli, Gzip, Identity), strict path traversal
defense, SPA fallback routing, asset caching headers, and ETag revalidation.
"""

from __future__ import annotations

import hashlib
import mimetypes
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING, Final

from starlette.datastructures import Headers

if TYPE_CHECKING:
    from starlette.types import Receive, Scope, Send

_CHUNK_SIZE: Final[int] = 64 * 1024
_MAX_FILE_SIZE: Final[int] = 50 * 1024 * 1024

_EXPLICIT_MIME_TYPES: Final[dict[str, str]] = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".wasm": "application/wasm",
    ".woff2": "font/woff2",
    ".webmanifest": "application/manifest+json",
}


def _parse_accept_encoding(header: str) -> dict[str, float]:
    """Parse Accept-Encoding header into encoding name to q-value mapping."""
    result: dict[str, float] = {}
    for raw_part in header.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if ";" in part:
            enc, q_part = part.split(";", 1)
            enc = enc.strip().lower()
            q_val = 1.0
            for raw_item in q_part.split(";"):
                item = raw_item.strip()
                if item.startswith("q="):
                    try:
                        q_val = float(item[2:])
                    except ValueError:
                        q_val = 0.0
            result[enc] = q_val
        else:
            result[part.lower()] = 1.0
    return result


class PrecompressedSPAStaticApp:
    """Pure ASGI application serving pre-compressed static assets and SPA fallback."""

    def __init__(self, dist_dir: Path) -> None:
        """Initialize static application with root distribution directory."""
        self.dist_dir = dist_dir

    def _is_safe_path(self, unquoted_path: str) -> bool:
        """Verify path does not contain null bytes, backslashes, or directory traversal."""
        return not (
            "\x00" in unquoted_path
            or "\\" in unquoted_path
            or any(seg == ".." for seg in unquoted_path.split("/"))
        )

    def _resolve_file(self, unquoted_path: str, raw_path: str) -> tuple[Path | None, bool]:
        """Resolve requested file safely within dist_dir or resolve SPA fallback index.html."""
        clean_path = unquoted_path.lstrip("/")
        target_path = (self.dist_dir / clean_path) if clean_path else (self.dist_dir / "index.html")

        if target_path.is_file():
            try:
                resolved = target_path.resolve(strict=True)
            except (OSError, RuntimeError):
                return None, False
            else:
                if resolved.is_relative_to(self.dist_dir.resolve()):
                    return resolved, False
                return None, False

        fallback = self._resolve_spa_fallback(unquoted_path, raw_path)
        if fallback is not None:
            return fallback, True
        return None, False

    def _resolve_spa_fallback(self, unquoted_path: str, raw_path: str) -> Path | None:
        """Resolve index.html fallback for extensionless non-reserved paths."""
        segments = [s for s in unquoted_path.split("/") if s]
        last_segment = segments[-1] if segments else ""
        disallowed_prefixes = (
            "/api",
            "/ws",
            "/sse",
            "/mcp",
            "/.well-known",
            "/oauth",
            "/internal",
        )
        is_reserved = any(
            raw_path == p or raw_path.startswith(p + "/") for p in disallowed_prefixes
        )

        if "." in last_segment or is_reserved:
            return None

        index_path = self.dist_dir / "index.html"
        if not index_path.is_file():
            return None

        try:
            resolved_index = index_path.resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        else:
            if resolved_index.is_relative_to(self.dist_dir.resolve()):
                return resolved_index
            return None

    def _select_encoding(
        self, file_path: Path, encodings: dict[str, float]
    ) -> tuple[Path, str | None]:
        """Select best pre-compressed variant according to accepted encodings."""
        br_variant = Path(str(file_path) + ".br")
        gz_variant = Path(str(file_path) + ".gz")

        if encodings.get("br", 0.0) > 0 and br_variant.is_file():
            return br_variant, "br"
        if encodings.get("gzip", 0.0) > 0 and gz_variant.is_file():
            return gz_variant, "gzip"
        return file_path, None

    def _get_cache_control(
        self, file_path: Path, unquoted_path: str, *, is_spa_fallback: bool
    ) -> str:
        """Determine Cache-Control header based on file type and path."""
        if is_spa_fallback or file_path.name == "index.html":
            return "no-cache"
        if unquoted_path in ("/manifest.json", "/manifest.webmanifest") or file_path.name in (
            "manifest.json",
            "manifest.webmanifest",
        ):
            return "public, max-age=86400"
        if unquoted_path.startswith("/assets/"):
            return "public, max-age=31536000, immutable"
        return "no-cache"

    def _is_not_modified(self, if_none_match: str | None, etag: str) -> bool:
        """Check whether If-None-Match matches the current ETag."""
        if not if_none_match:
            return False
        candidate = if_none_match.strip()
        if candidate in (etag, "*"):
            return True
        return etag in [item.strip() for item in candidate.split(",")]

    async def _send_response(
        self,
        send: Send,
        status: int,
        headers: list[tuple[bytes, bytes]],
        body: bytes = b"",
    ) -> None:
        """Send complete single-chunk HTTP response."""
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def _send_404(self, send: Send) -> None:
        """Send 404 Not Found plain text response."""
        await self._send_response(
            send,
            status=404,
            headers=[(b"content-type", b"text/plain; charset=utf-8")],
            body=b"Not Found",
        )

    async def _send_method_not_allowed(self, send: Send) -> None:
        """Send 405 Method Not Allowed response with Allow header."""
        await self._send_response(
            send,
            status=405,
            headers=[
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"allow", b"GET, HEAD"),
            ],
            body=b"Method Not Allowed",
        )

    async def _send_304(self, send: Send, etag: str, cache_control: str) -> None:
        """Send 304 Not Modified response."""
        await send(
            {
                "type": "http.response.start",
                "status": 304,
                "headers": [
                    (b"etag", etag.encode("ascii")),
                    (b"vary", b"Accept-Encoding"),
                    (b"cache-control", cache_control.encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    async def _send_200(
        self,
        send: Send,
        file_bytes: bytes,
        headers: list[tuple[bytes, bytes]],
        *,
        is_head: bool,
    ) -> None:
        """Send 200 OK response with chunked body streaming."""
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": headers,
            }
        )
        if is_head:
            await send({"type": "http.response.body", "body": b""})
            return

        for offset in range(0, len(file_bytes), _CHUNK_SIZE):
            chunk = file_bytes[offset : offset + _CHUNK_SIZE]
            more_body = (offset + _CHUNK_SIZE) < len(file_bytes)
            await send(
                {
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": more_body,
                }
            )
        if not file_bytes:
            await send({"type": "http.response.body", "body": b""})

    async def _serve_file(
        self,
        scope: Scope,
        send: Send,
        file_to_serve: Path,
        unquoted_path: str,
        *,
        is_spa_fallback: bool,
    ) -> None:
        """Read and stream file content with content negotiation and ETag headers."""
        headers = Headers(scope=scope)
        encodings = _parse_accept_encoding(headers.get("accept-encoding", ""))
        actual_file, content_encoding = self._select_encoding(file_to_serve, encodings)

        try:
            file_bytes = actual_file.read_bytes()
        except OSError:
            await self._send_404(send)
            return

        sha16 = hashlib.sha256(file_bytes).hexdigest()[:16]
        encoding_tag = content_encoding or "identity"
        etag = f'"{sha16}-{encoding_tag}"'

        suffix = file_to_serve.suffix.lower()
        if unquoted_path in ("/manifest.json", "/manifest.webmanifest") or file_to_serve.name in (
            "manifest.json",
            "manifest.webmanifest",
        ):
            content_type = "application/manifest+json"
        else:
            content_type = _EXPLICIT_MIME_TYPES.get(
                suffix, mimetypes.guess_type(file_to_serve.name)[0] or "application/octet-stream"
            )
        cache_control = self._get_cache_control(
            file_to_serve, unquoted_path, is_spa_fallback=is_spa_fallback
        )

        if_none_match = headers.get("if-none-match")
        if self._is_not_modified(if_none_match, etag):
            await self._send_304(send, etag, cache_control)
            return

        response_headers: list[tuple[bytes, bytes]] = [
            (b"content-type", content_type.encode("ascii")),
            (b"content-length", str(len(file_bytes)).encode("ascii")),
            (b"etag", etag.encode("ascii")),
            (b"vary", b"Accept-Encoding"),
            (b"cache-control", cache_control.encode("ascii")),
        ]
        if content_encoding:
            response_headers.append((b"content-encoding", content_encoding.encode("ascii")))

        is_head = scope.get("method") == "HEAD"
        await self._send_200(
            send,
            file_bytes,
            response_headers,
            is_head=is_head,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process incoming ASGI request, serving pre-compressed assets or SPA fallback."""
        del receive
        if scope["type"] != "http":
            return

        method = scope.get("method", "GET")
        if method not in ("GET", "HEAD"):
            await self._send_method_not_allowed(send)
            return

        raw_path = scope.get("path", "/")
        unquoted_path = urllib.parse.unquote(raw_path)

        if not self._is_safe_path(unquoted_path):
            await self._send_404(send)
            return

        file_to_serve, is_spa_fallback = self._resolve_file(unquoted_path, raw_path)
        if file_to_serve is None:
            await self._send_404(send)
            return

        try:
            if file_to_serve.stat().st_size > _MAX_FILE_SIZE:
                await self._send_404(send)
                return
        except OSError:
            await self._send_404(send)
            return

        await self._serve_file(
            scope,
            send,
            file_to_serve,
            unquoted_path,
            is_spa_fallback=is_spa_fallback,
        )
