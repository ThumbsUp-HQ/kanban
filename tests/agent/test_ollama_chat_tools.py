# ruff: noqa: INP001, D101, D103, ANN401
# Copyright 2026 Kanban Platform Contributors
"""Tests for OllamaProvider.chat_turn tool-calling hardening (KAN-542)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from agent.providers.base import (
    ChatMessage,
    ChatTurnRequest,
    StructuredRequest,
    ToolCallingProvider,
    ToolDefinition,
)
from agent.providers.errors import ProviderHTTPError, ProviderProtocolError
from agent.providers.ollama import OllamaProvider, OllamaSettings

MODEL = "qwen3:8b"
TOOL = ToolDefinition(name="get_ticket", description="d", parameters={"type": "object"})


class Out(BaseModel):
    ok: bool


def _provider(handler: Any) -> tuple[OllamaProvider, list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return handler(request, len(sent))

    settings = OllamaSettings(base_url="http://127.0.0.1:11434", model_allowlist=(MODEL,))
    return OllamaProvider(settings, transport=httpx.MockTransport(wrapped)), sent


def _req(**kw: Any) -> ChatTurnRequest:
    return ChatTurnRequest(model=MODEL, messages=(ChatMessage(role="user", content="hi"),), **kw)


def _ok(message: dict[str, Any], **extra: Any) -> httpx.Response:
    return httpx.Response(200, json={"message": message, "done_reason": "stop", **extra})


def test_protocol_runtime_check() -> None:
    p, _ = _provider(lambda _r, _n: _ok({}))
    assert isinstance(p, ToolCallingProvider)


@pytest.mark.asyncio
async def test_tool_calls_dict_and_string_args() -> None:
    msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "a", "function": {"name": "get_ticket", "arguments": {"k": 1}}},
            {"function": {"name": "get_ticket", "arguments": '{"k": 2}'}},
        ],
    }
    p, sent = _provider(lambda _r, _n: _ok(msg, prompt_eval_count=3, eval_count=4))
    resp = await p.chat_turn(_req(tools=(TOOL,)))
    assert [c.arguments for c in resp.message.tool_calls] == [{"k": 1}, {"k": 2}]
    assert resp.message.tool_calls[0].id == "a"
    assert resp.prompt_tokens == 3
    assert sent[0]["tools"][0]["function"]["name"] == "get_ticket"
    assert "format" not in sent[0]
    assert sent[0]["stream"] is False


@pytest.mark.asyncio
async def test_final_structured_turn_with_format_and_think_false() -> None:
    p, sent = _provider(lambda _r, _n: _ok({"content": '{"ok": true}', "thinking": "t"}))
    req = _req(response_model=Out, think=False)
    resp = await p.chat_turn(req)
    assert sent[0]["think"] is False
    assert sent[0]["format"]["properties"]["ok"]
    assert "tools" not in sent[0]
    assert resp.message.thinking == "t"
    assert resp.message.content == '{"ok": true}'


@pytest.mark.asyncio
async def test_think_400_fallback() -> None:
    def h(_r: httpx.Request, n: int) -> httpx.Response:
        return httpx.Response(400, text="no think") if n == 1 else _ok({"content": "x"})

    p, sent = _provider(h)
    resp = await p.chat_turn(_req(think=True))
    assert "think" in sent[0]
    assert "think" not in sent[1]
    assert resp.message.content == "x"


@pytest.mark.asyncio
async def test_length_retry_doubles_once() -> None:
    def h(_r: httpx.Request, n: int) -> httpx.Response:
        if n < 3:
            return httpx.Response(200, json={"message": {"content": ""}, "done_reason": "length"})
        return _ok({"content": "never"})

    p, sent = _provider(h)
    resp = await p.chat_turn(_req(max_output_tokens=100))
    assert [s["options"]["num_predict"] for s in sent] == [100, 200]
    assert resp.done_reason == "length"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["content", "thinking"])
async def test_fake_tool_calls_in_text_ignored(field: str) -> None:
    fake = json.dumps({"tool_calls": [{"function": {"name": "get_ticket", "arguments": {}}}]})
    p, _ = _provider(lambda _r, _n: _ok({"content": "", field: fake} | {"content": fake}))
    resp = await p.chat_turn(_req(tools=(TOOL,)))
    assert resp.message.tool_calls == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "calls",
    [
        [{"function": {"name": "evil", "arguments": {}}}],
        [{"function": {"name": 5, "arguments": {}}}],
        [{"function": {"name": "get_ticket", "arguments": "[1]"}}],
        [{"function": {"name": "get_ticket", "arguments": "{bad"}}],
        [{"function": {"name": "get_ticket", "arguments": 7}}],
        [{"function": {"name": "get_ticket", "arguments": "x" * 70000}}],
        [{"nofunction": 1}],
        "notalist",
        [{"function": {"name": "get_ticket", "arguments": {}}}] * 9,
    ],
)
async def test_invalid_tool_calls_rejected(calls: Any) -> None:
    p, _ = _provider(lambda _r, _n: _ok({"content": "", "tool_calls": calls}))
    with pytest.raises(ProviderProtocolError):
        await p.chat_turn(_req(tools=(TOOL,)))


@pytest.mark.asyncio
async def test_oversize_rejected_chat_and_structured() -> None:
    big = httpx.Response(200, content=b"x" * (8 * 1024 * 1024 + 1))
    p, _ = _provider(lambda _r, _n: big)
    with pytest.raises(ProviderProtocolError) as ei:
        await p.chat_turn(_req())
    assert ei.value.code == "STREAM_TOO_LARGE"
    p2, _ = _provider(lambda _r, _n: httpx.Response(200, content=b"x" * (8 * 1024 * 1024 + 1)))
    with pytest.raises(ProviderProtocolError):
        await p2.generate_structured(StructuredRequest(model=MODEL, prompt="p", response_model=Out))


@pytest.mark.asyncio
async def test_error_body_scrubbed_and_truncated() -> None:
    secret = "Bearer sk-abcdefghijklmnopqrstuvwxyz0123456789"
    body = f"{secret} " + "y" * 5000
    p, _ = _provider(lambda _r, _n: httpx.Response(500, text=body))
    with pytest.raises(ProviderHTTPError) as ei:
        await p.chat_turn(_req())
    assert "abcdefghijklmnopqrstuvwxyz0123456789" not in str(ei.value)
    assert len(str(ei.value)) < 700
