# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Out-of-sandbox Unix-socket token-injecting egress proxy (KB-P5-14, S13.3)."""

from __future__ import annotations

import asyncio
import contextlib
import fnmatch
import json
import os
import posixpath
import shutil
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final, Self

import httpx

if TYPE_CHECKING:
    from types import TracebackType

    from starlette.types import ASGIApp

_MAX_BODY_BYTES: Final[int] = 524288  # 512 KiB
_MAX_REQUEST_LINE_LENGTH: Final[int] = 4096
_MIN_REQUEST_LINE_PARTS: Final[int] = 2


@dataclass(frozen=True, slots=True)
class EgressProxyPolicy:
    """Security bounds and allowlist configuration for egress proxy invocation."""

    egress_allowlist: list[str] = field(default_factory=list)
    max_requests: int = 10
    timeout_ms: int = 15000
    target_scope: str = "project"
    credential_mode: str = "ephemeral_token"


class TokenInjectingEgressProxy:
    """Host-side Unix stream server injecting short-lived bearer tokens into sandbox requests.

    Zero token bytes are ever exposed inside the sandbox. Tokens are held exclusively
    in mutable host memory and overwritten with zeroes in finally.
    """

    def __init__(  # noqa: PLR0913
        self,
        token: str,
        policy: EgressProxyPolicy,
        *,
        app: ASGIApp | None = None,
        base_url: str = "http://localhost",
        invocation_id: uuid.UUID | None = None,
        base_dir: Path | None = None,
    ) -> None:
        """Initialize TokenInjectingEgressProxy with policy and isolated token buffer."""
        self.policy = policy
        self.invocation_id = invocation_id or uuid.uuid4()
        self._app = app
        self._base_url = base_url

        # Store token exclusively in mutable bytearray
        token_bytes = token.encode("utf-8")
        self._token_buf = bytearray(token_bytes)
        self._token_len = len(token_bytes)

        # Wall-clock expiry monotonic timestamp
        allowed_duration = min(self.policy.timeout_ms, 15000) / 1000.0
        self._token_expires_at = time.monotonic() + allowed_duration
        self._request_count = 0

        # Runtime directory & socket setup
        if base_dir is not None:
            runtime_base = base_dir
        else:
            default_run = Path("/run/kanban/sandbox")
            if default_run.exists() and os.access(default_run, os.W_OK):
                runtime_base = default_run
            else:
                runtime_base = Path("/tmp/kanban/sandbox")  # noqa: S108

        self.runtime_dir = runtime_base / str(self.invocation_id)
        self.socket_path = self.runtime_dir / "proxy.sock"
        self._server: asyncio.Server | None = None
        self._http_client: httpx.AsyncClient | None = None

    @property
    def request_count(self) -> int:
        """Return the count of requests received during this proxy lifetime."""
        return self._request_count

    def zero_token(self) -> None:
        """Explicitly overwrite token memory with zeroes."""
        for i in range(len(self._token_buf)):
            self._token_buf[i] = 0

    def _get_active_token(self) -> str | None:
        """Return active token if not expired and not zeroed."""
        if time.monotonic() >= self._token_expires_at:
            return None
        if not any(self._token_buf):
            return None
        return self._token_buf.decode("utf-8", errors="replace")

    async def start(self) -> None:
        """Create runtime directory and start listening on Unix stream socket."""
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            self.runtime_dir.chmod(0o700)

        if self.socket_path.exists():
            self.socket_path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self.socket_path),
        )
        with contextlib.suppress(OSError):
            self.socket_path.chmod(0o600)

        if self._app is not None:
            self._http_client = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self._app),
                base_url=self._base_url,
                follow_redirects=False,
            )
        else:
            self._http_client = httpx.AsyncClient(
                base_url=self._base_url,
                follow_redirects=False,
            )

    async def stop(self) -> None:
        """Stop Unix server, close client, zero token memory, and delete socket files."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

        self.zero_token()

        if self.socket_path.exists():
            with contextlib.suppress(OSError):
                self.socket_path.unlink()

        if self.runtime_dir.exists():
            with contextlib.suppress(OSError):
                shutil.rmtree(self.runtime_dir, ignore_errors=True)

    async def __aenter__(self) -> Self:
        """Enter the asynchronous context, starting the Unix stream proxy server."""
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the asynchronous context, stopping the proxy and zeroing token memory."""
        await self.stop()

    def _build_problem_response(self, status: int, code: str, title: str, detail: str) -> bytes:
        payload = {
            "type": f"urn:kanban:problem:{code}",
            "title": title,
            "status": status,
            "code": code,
            "detail": detail,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = [
            f"HTTP/1.1 {status} {title}",
            "Content-Type: application/problem+json",
            f"Content-Length: {len(body)}",
            "Connection: close",
            "",
            "",
        ]
        return "\r\n".join(headers).encode("ascii") + body

    def _validate_path(self, raw_path: str) -> tuple[bool, str, str]:  # noqa: PLR0911
        """Validate, decode, and match raw request path against policy allowlist."""
        # Check invalid characters
        if "\0" in raw_path or "\\" in raw_path or "\r" in raw_path or "\n" in raw_path:
            return False, "403", "Invalid characters in request path"

        # Check authority-form URLs
        if raw_path.startswith(("http://", "https://", "//")):
            return False, "403", "Authority-form URLs forbidden on sandbox proxy"

        # Parse url component
        parsed = urllib.parse.urlsplit(raw_path)
        path_only = parsed.path

        # Unquote path
        unquoted = urllib.parse.unquote(path_only)

        # Check for path traversal attempts
        if ".." in unquoted.split("/") or "%2e" in raw_path.lower():
            return False, "403", "Path traversal forbidden"

        norm = posixpath.normpath(unquoted)
        if norm != unquoted and norm != unquoted.rstrip("/"):
            return False, "403", "Path normalization mismatch"

        if not norm.startswith("/api/v1/"):
            return False, "403", "Only routes under /api/v1/... are permissible"

        # Match against policy allowlist
        matched = False
        for pattern in self.policy.egress_allowlist:
            if pattern == norm or fnmatch.fnmatch(norm, pattern):
                matched = True
                break

        if not matched:
            return False, "403", f"Route '{norm}' not matched by egress allowlist"

        reconstructed = norm
        if parsed.query:
            reconstructed = f"{norm}?{parsed.query}"

        return True, "", reconstructed

    async def _handle_client(  # noqa: C901, PLR0911, PLR0912, PLR0915
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming HTTP/1.1 connection over Unix domain socket."""
        try:
            line_bytes = await reader.readline()
            if not line_bytes:
                writer.close()
                await writer.wait_closed()
                return

            request_line = line_bytes.decode("ascii", errors="replace").strip()
            parts = request_line.split(" ")
            if len(parts) < _MIN_REQUEST_LINE_PARTS:
                resp = self._build_problem_response(
                    400, "BAD_REQUEST", "Bad Request", "Malformed HTTP request line"
                )
                writer.write(resp)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            method, raw_target = parts[0].upper(), parts[1]

            # 1. Lifetime check
            active_token = self._get_active_token()
            if active_token is None:
                resp = self._build_problem_response(
                    401,
                    "PROXY_TOKEN_EXPIRED",
                    "Unauthorized",
                    "Sandbox invocation token has expired or was revoked",
                )
                writer.write(resp)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            # 2. Request count check
            self._request_count += 1
            if self._request_count > self.policy.max_requests:
                resp = self._build_problem_response(
                    429,
                    "PROXY_MAX_REQUESTS_EXCEEDED",
                    "Too Many Requests",
                    f"Maximum invocation request budget of {self.policy.max_requests} exceeded",
                )
                writer.write(resp)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            # 3. Method check: strictly GET
            if method != "GET":
                resp = self._build_problem_response(
                    405,
                    "PROXY_METHOD_NOT_ALLOWED",
                    "Method Not Allowed",
                    f"Method '{method}' is forbidden on sandbox proxy; strictly GET is permitted",
                )
                writer.write(resp)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            # 4. Path check & allowlist matching
            is_valid, err_code, norm_target = self._validate_path(raw_target)
            if not is_valid:
                resp = self._build_problem_response(
                    403,
                    "PROXY_ROUTE_NOT_ALLOWLISTED",
                    "Forbidden",
                    err_code,
                )
                writer.write(resp)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            # 5. Read and scrub client headers
            while True:
                h_line = await reader.readline()
                if not h_line or h_line in (b"\r\n", b"\n"):
                    break

            # 6. Inject authorized headers
            injected_headers = {
                "Authorization": f"Bearer {active_token}",
                "X-Kanban-Script-Depth": "1",
                "Host": "localhost",
                "Accept": "application/json",
            }

            # 7. Forward to internal client
            if self._http_client is None:
                resp = self._build_problem_response(
                    503,
                    "UPSTREAM_UNAVAILABLE",
                    "Service Unavailable",
                    "Internal HTTP client not initialized",
                )
                writer.write(resp)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            up_resp = await self._http_client.get(
                norm_target,
                headers=injected_headers,
            )

            # Cap body at 512 KiB
            content = up_resp.content[:_MAX_BODY_BYTES]
            status_line = f"HTTP/1.1 {up_resp.status_code} {up_resp.reason_phrase}\r\n"
            out_headers = [status_line]
            for hk, hv in up_resp.headers.items():
                if hk.lower() in ("content-type", "etag", "cache-control"):
                    out_headers.append(f"{hk}: {hv}\r\n")
            out_headers.append(f"Content-Length: {len(content)}\r\n")
            out_headers.append("Connection: close\r\n\r\n")

            writer.write("".join(out_headers).encode("ascii"))
            writer.write(content)
            await writer.drain()
        except Exception as exc:  # noqa: BLE001
            with contextlib.suppress(Exception):
                resp = self._build_problem_response(
                    500,
                    "PROXY_INTERNAL_ERROR",
                    "Internal Server Error",
                    f"Egress proxy error: {exc}",
                )
                writer.write(resp)
                await writer.drain()
        finally:
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()
