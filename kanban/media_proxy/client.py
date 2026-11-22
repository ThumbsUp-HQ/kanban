"""Pinned TLS socket HTTP client for cookieless media retrieval (S5.4, S10.2)."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Final

from kanban.api.problems import ProblemException
from kanban.security.ssrf import (
    DefaultPinnedConnectionTransport,
    PinnedConnectionTransport,
    validate_not_redirect,
)

if TYPE_CHECKING:
    from ipaddress import IPv4Address, IPv6Address

MAX_PROXY_BYTES: Final[int] = 10_485_760  # 10 MiB
_CONNECT_TIMEOUT: Final[float] = 3.0
_READ_TIMEOUT: Final[float] = 5.0
_TOTAL_TIMEOUT: Final[float] = 8.0

_HTTP_OK: Final[int] = 200
_HTTP_REDIRECT_MIN: Final[int] = 300
_HTTP_REDIRECT_MAX: Final[int] = 399
_STATUS_LINE_MIN_PARTS: Final[int] = 2

_MIN_SIGNATURE_BYTES: Final[int] = 4
_CONTAINER_SIGNATURE_BYTES: Final[int] = 12
_AVIF_BRANDS: Final[frozenset[bytes]] = frozenset({b"avif", b"avis", b"mif1"})

_ALLOWED_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/avif",
        "image/gif",
    }
)


def _verify_magic_signature(content_type: str, data: bytes) -> bool:
    """Verify first bytes match expected raster image magic signature."""
    if len(data) < _MIN_SIGNATURE_BYTES:
        return False
    if content_type == "image/png":
        valid = data.startswith(b"\x89PNG\r\n\x1a\n")
    elif content_type == "image/jpeg":
        valid = data.startswith(b"\xff\xd8\xff")
    elif content_type == "image/gif":
        valid = data.startswith((b"GIF87a", b"GIF89a"))
    elif len(data) >= _CONTAINER_SIGNATURE_BYTES and content_type == "image/webp":
        valid = data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    elif len(data) >= _CONTAINER_SIGNATURE_BYTES and content_type == "image/avif":
        valid = data[4:8] == b"ftyp" and data[8:12] in _AVIF_BRANDS
    else:
        valid = False
    return valid


def _parse_status_code(status_line_bytes: bytes, original_host: str) -> int:
    """Parse HTTP status line and validate non-redirect 200 status."""
    if not status_line_bytes:
        msg = f"Empty response received from media host '{original_host}'"
        raise ProblemException(
            code="MEDIA_UPSTREAM_ERROR",
            status=502,
            title="Media Upstream Error",
            detail=msg,
        )

    status_line = status_line_bytes.decode("latin1", errors="replace").strip()
    parts = status_line.split(" ", 2)
    if len(parts) < _STATUS_LINE_MIN_PARTS:
        msg = f"Malformed status line from media host '{original_host}': {status_line!r}"
        raise ProblemException(
            code="MEDIA_UPSTREAM_ERROR",
            status=502,
            title="Media Upstream Error",
            detail=msg,
        )

    try:
        status_code = int(parts[1])
    except ValueError:
        msg = f"Invalid status code from media host '{original_host}': {parts[1]!r}"
        raise ProblemException(
            code="MEDIA_UPSTREAM_ERROR",
            status=502,
            title="Media Upstream Error",
            detail=msg,
        ) from None

    validate_not_redirect(
        status_code,
        original_host,
        error_code="MEDIA_REDIRECT_BLOCKED",
        error_title="Media Redirect Blocked",
    )

    if status_code != _HTTP_OK:
        msg = f"Upstream media host '{original_host}' returned HTTP {status_code}"
        raise ProblemException(
            code="MEDIA_UPSTREAM_ERROR",
            status=502,
            title="Media Upstream Error",
            detail=msg,
        )

    return status_code


async def _read_http_headers(reader: asyncio.StreamReader) -> dict[str, str]:
    """Read RFC 7230 HTTP headers until terminating CRLF."""
    raw_headers: dict[str, str] = {}
    while True:
        header_line_bytes = await asyncio.wait_for(reader.readline(), timeout=_READ_TIMEOUT)
        if not header_line_bytes or header_line_bytes in (b"\r\n", b"\n"):
            break
        header_line = header_line_bytes.decode("latin1", errors="replace").strip()
        if ":" in header_line:
            k, v = header_line.split(":", 1)
            raw_headers[k.strip().lower()] = v.strip()
    return raw_headers


def _validate_content_type_and_length(raw_headers: dict[str, str]) -> str:
    """Validate content-type is raster image and declared length is within limit."""
    content_type_raw = raw_headers.get("content-type", "")
    content_type = content_type_raw.split(";", 1)[0].strip().lower()

    if content_type not in _ALLOWED_CONTENT_TYPES:
        msg = (
            f"Disallowed media content type '{content_type_raw}'; "
            "only raster images (PNG, JPEG, WebP, AVIF, GIF) are allowed"
        )
        raise ProblemException(
            code="MEDIA_TYPE_DISALLOWED",
            status=415,
            title="Media Type Disallowed",
            detail=msg,
        )

    cl_header = raw_headers.get("content-length")
    if cl_header is not None:
        try:
            cl_val = int(cl_header)
            if cl_val > MAX_PROXY_BYTES:
                msg = (
                    f"Declared Content-Length {cl_val} exceeds "
                    f"maximum limit of {MAX_PROXY_BYTES} bytes"
                )
                raise ProblemException(
                    code="MEDIA_TOO_LARGE",
                    status=502,
                    title="Media Too Large",
                    detail=msg,
                )
        except ValueError:
            pass

    return content_type


__all__ = [
    "MAX_PROXY_BYTES",
    "DefaultPinnedConnectionTransport",
    "PinnedConnectionTransport",
    "PinnedTlsMediaClient",
]


class PinnedTlsMediaClient:
    """Cookieless media retrieval client pinning DNS-resolved IP literals."""

    def __init__(self, transport: PinnedConnectionTransport | None = None) -> None:
        """Initialize client with optional socket transport double."""
        self._transport = transport or DefaultPinnedConnectionTransport()

    async def fetch_media(
        self,
        pinned_ip: IPv4Address | IPv6Address,
        original_host: str,
        path_and_query: str,
    ) -> tuple[str, bytes]:
        """Retrieve external media payload over pinned IP socket without cookie forwarding.

        Enforces zero redirects (3xx -> 502), raster content-type verification (415),
        magic signature validation (502), and strict 10 MiB size limit (502).
        """
        return await asyncio.wait_for(
            self._fetch_internal(pinned_ip, original_host, path_and_query),
            timeout=_TOTAL_TIMEOUT,
        )

    async def _fetch_internal(
        self,
        pinned_ip: IPv4Address | IPv6Address,
        original_host: str,
        path_and_query: str,
    ) -> tuple[str, bytes]:
        """Handle internal HTTP wire exchange, status validation, and payload reading."""
        path = path_and_query if path_and_query.startswith("/") else f"/{path_and_query}"
        req_lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {original_host}",
            "User-Agent: Kanban-Media-Proxy/1.0",
            "Accept: image/png, image/jpeg, image/webp, image/avif, image/gif",
            "Accept-Encoding: identity",
            "Connection: close",
            "",
            "",
        ]
        req_payload = "\r\n".join(req_lines).encode("ascii")

        try:
            reader, writer = await self._transport.open_connection(
                ip=str(pinned_ip),
                port=443,
                server_hostname=original_host,
                connect_timeout=_CONNECT_TIMEOUT,
            )
        except Exception as err:
            msg = f"Failed to connect to media host '{original_host}': {err}"
            raise ProblemException(
                code="MEDIA_UPSTREAM_ERROR",
                status=502,
                title="Media Upstream Error",
                detail=msg,
            ) from err

        try:
            writer.write(req_payload)
            await asyncio.wait_for(writer.drain(), timeout=_READ_TIMEOUT)

            status_line_bytes = await asyncio.wait_for(reader.readline(), timeout=_READ_TIMEOUT)
            _parse_status_code(status_line_bytes, original_host)

            raw_headers = await _read_http_headers(reader)
            content_type = _validate_content_type_and_length(raw_headers)

            is_chunked = raw_headers.get("transfer-encoding", "").lower() == "chunked"
            if is_chunked:
                body_bytes = await self._read_chunked_body(reader)
            else:
                body_bytes = await self._read_fixed_body(reader)

            if len(body_bytes) > MAX_PROXY_BYTES:
                msg = f"Payload size {len(body_bytes)} exceeds limit of {MAX_PROXY_BYTES} bytes"
                raise ProblemException(
                    code="MEDIA_TOO_LARGE",
                    status=502,
                    title="Media Too Large",
                    detail=msg,
                )

            if not _verify_magic_signature(content_type, body_bytes):
                msg = f"Payload magic bytes do not match declared content type '{content_type}'"
                raise ProblemException(
                    code="MEDIA_SIGNATURE_MISMATCH",
                    status=502,
                    title="Media Signature Mismatch",
                    detail=msg,
                )

            return content_type, body_bytes

        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()

    async def _read_fixed_body(self, reader: asyncio.StreamReader) -> bytes:
        """Read stream body until EOF with strict MAX_PROXY_BYTES enforcement."""
        chunks: list[bytes] = []
        total_bytes = 0
        while True:
            chunk = await asyncio.wait_for(reader.read(65536), timeout=_READ_TIMEOUT)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_PROXY_BYTES:
                msg = f"Streamed payload exceeded {MAX_PROXY_BYTES} bytes"
                raise ProblemException(
                    code="MEDIA_TOO_LARGE",
                    status=502,
                    title="Media Too Large",
                    detail=msg,
                )
            chunks.append(chunk)
        return b"".join(chunks)

    async def _read_chunked_body(self, reader: asyncio.StreamReader) -> bytes:
        """Read HTTP chunked transfer-encoded body with strict MAX_PROXY_BYTES enforcement."""
        chunks: list[bytes] = []
        total_bytes = 0
        while True:
            size_line = await asyncio.wait_for(reader.readline(), timeout=_READ_TIMEOUT)
            if not size_line:
                break
            chunk_size_str = size_line.decode("ascii", errors="replace").split(";")[0].strip()
            try:
                chunk_len = int(chunk_size_str, 16)
            except ValueError as err:
                msg = f"Invalid chunk size hex: {chunk_size_str!r}"
                raise ProblemException(
                    code="MEDIA_UPSTREAM_ERROR",
                    status=502,
                    title="Media Upstream Error",
                    detail=msg,
                ) from err

            if chunk_len == 0:
                while True:
                    trailer = await asyncio.wait_for(reader.readline(), timeout=_READ_TIMEOUT)
                    if not trailer or trailer in (b"\r\n", b"\n"):
                        break
                break

            chunk_data = await asyncio.wait_for(
                reader.readexactly(chunk_len), timeout=_READ_TIMEOUT
            )
            total_bytes += len(chunk_data)
            if total_bytes > MAX_PROXY_BYTES:
                msg = f"Streamed chunked payload exceeded {MAX_PROXY_BYTES} bytes"
                raise ProblemException(
                    code="MEDIA_TOO_LARGE",
                    status=502,
                    title="Media Too Large",
                    detail=msg,
                )
            chunks.append(chunk_data)

            await asyncio.wait_for(reader.readline(), timeout=_READ_TIMEOUT)

        return b"".join(chunks)
