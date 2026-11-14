# Copyright 2026 Kanban Platform Contributors
"""Test fixtures and transcript recording hook for MCP test suites."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import httpx
import pytest

from mcp.app import create_mcp_app
from mcp.registry import Surface, ToolRegistry, create_placeholder_tool
from mcp.settings import McpSettings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from starlette.applications import Starlette

_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b(kb_[a-z_]+_)[A-Za-z0-9_-]{20,}\b")


def redact_transcript_text(text: str) -> str:
    """Redact sensitive authorization tokens and subject keys from recorded transcripts."""
    return _TOKEN_PATTERN.sub(r"\1***REDACTED***", text)


def format_redacted_headers(headers: httpx.Headers) -> list[str]:
    """Format and redact headers for recording into mcp-transcript.txt."""
    lines: list[str] = []
    for name, value in headers.raw:
        h_name = name.decode("ascii", errors="replace")
        h_val = value.decode("ascii", errors="replace")
        h_name_lower = h_name.lower()
        if h_name_lower in ("authorization", "x-kb-subject-token"):
            if _TOKEN_PATTERN.search(h_val):
                redacted_val = _TOKEN_PATTERN.sub(r"\1***REDACTED***", h_val)
            elif "bearer " in h_val.lower():
                redacted_val = "Bearer ***REDACTED***"
            else:
                redacted_val = "***REDACTED***"
            lines.append(f"{h_name}: {redacted_val}")
        else:
            lines.append(f"{h_name}: {redact_transcript_text(h_val)}")
    return lines


def record_http_exchange(
    transcript_path: Path,
    request: httpx.Request,
    response: httpx.Response,
) -> None:
    """Append a raw, redacted request and response pair to the transcript file."""
    transcript_path.parent.mkdir(parents=True, exist_ok=True)

    req_headers = format_redacted_headers(request.headers)
    req_body_text = redact_transcript_text(request.content.decode("utf-8", errors="replace"))

    resp_headers = format_redacted_headers(response.headers)
    resp_body_text = redact_transcript_text(response.content.decode("utf-8", errors="replace"))

    exchange_lines = [
        f"{request.method} {request.url.raw_path.decode('ascii')} HTTP/1.1",
        *req_headers,
        "",
        req_body_text or "(empty body)",
        "",
        f"HTTP/1.1 {response.status_code} {response.reason_phrase}",
        *resp_headers,
        "",
        resp_body_text or "(empty body)",
        "",
        "-" * 80,
        "",
    ]

    with transcript_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(exchange_lines))


@pytest.fixture(autouse=True)
def transcript_recorder(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Autouse fixture recording all MCP HTTP requests/responses when env is set."""
    transcript_env = os.environ.get("KB_MCP_TRANSCRIPT_PATH")
    if not transcript_env:
        yield
        return

    transcript_path = Path(transcript_env).resolve()
    orig_send = httpx.AsyncClient.send

    async def _recording_send(
        self: httpx.AsyncClient,
        request: httpx.Request,
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> httpx.Response:
        resp = await orig_send(self, request, *args, **kwargs)
        # Ensure response content is loaded for recording
        await resp.aread()
        if "/mcp" in request.url.path:
            record_http_exchange(transcript_path, request, resp)
        return resp

    monkeypatch.setattr(httpx.AsyncClient, "send", _recording_send)
    yield


@pytest.fixture
def mcp_app() -> Starlette:
    """Default Starlette application mounting the 3 MCP surfaces."""
    settings = McpSettings(mode="standalone_inprocess", auth_enabled=False)
    docs_reg = ToolRegistry(Surface.DOCS)
    docs_reg.register(create_placeholder_tool(Surface.DOCS))
    admin_reg = ToolRegistry(Surface.ADMIN)
    admin_reg.register(create_placeholder_tool(Surface.ADMIN))
    return create_mcp_app(settings, docs_registry=docs_reg, admin_registry=admin_reg)


@pytest.fixture
async def mcp_client(mcp_app: Starlette) -> AsyncIterator[httpx.AsyncClient]:
    """Async test client bound via ASGITransport to the MCP application."""
    transport = httpx.ASGITransport(app=mcp_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
