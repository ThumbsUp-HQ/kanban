# Copyright 2026 Kanban Platform Contributors
"""KAN-538: Ollama think:false, 400 fallback, and length retry tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import BaseModel

from agent.harnesses.in_app_sdk import DEFAULT_STRUCTURED_MAX_OUTPUT_TOKENS
from agent.providers.base import StructuredRequest
from agent.providers.errors import ProviderSchemaError
from agent.providers.ollama import OllamaProvider
from agent.tests.providers.test_ollama import _make_settings

if TYPE_CHECKING:
    from collections.abc import Callable


class _Out(BaseModel):
    passed: bool


def _provider(handler: Callable[[httpx.Request], httpx.Response]) -> OllamaProvider:
    return OllamaProvider(_make_settings(), transport=httpx.MockTransport(handler))


def _req(tokens: int = 100) -> StructuredRequest[_Out]:
    return StructuredRequest(
        model="qwen2.5-coder:7b", prompt="x", response_model=_Out, max_output_tokens=tokens
    )


def test_default_budget() -> None:
    """test_default_budget."""
    assert DEFAULT_STRUCTURED_MAX_OUTPUT_TOKENS == 8192


@pytest.mark.asyncio
async def test_think_false_sent() -> None:
    """test_think_false_sent."""
    seen: list[dict[str, object]] = []

    def h(r: httpx.Request) -> httpx.Response:
        seen.append(json.loads(r.content))
        return httpx.Response(200, json={"message": {"content": '{"passed": true}'}})

    resp = await _provider(h).generate_structured(_req())
    assert resp.parsed.passed is True
    assert seen[0]["think"] is False


@pytest.mark.asyncio
async def test_400_retries_without_think() -> None:
    """test_400_retries_without_think."""
    seen: list[dict[str, object]] = []

    def h(r: httpx.Request) -> httpx.Response:
        body = json.loads(r.content)
        seen.append(body)
        if "think" in body:
            return httpx.Response(400, json={"error": "think not supported"})
        return httpx.Response(200, json={"message": {"content": '{"passed": false}'}})

    resp = await _provider(h).generate_structured(_req())
    assert resp.parsed.passed is False
    assert len(seen) == 2
    assert "think" not in seen[1]


@pytest.mark.asyncio
async def test_length_empty_retries_with_double_budget() -> None:
    """test_length_empty_retries_with_double_budget."""
    budgets: list[int] = []

    def h(r: httpx.Request) -> httpx.Response:
        budgets.append(json.loads(r.content)["options"]["num_predict"])
        if len(budgets) == 1:
            return httpx.Response(
                200,
                json={"message": {"content": "", "thinking": "t" * 50}, "done_reason": "length"},
            )
        return httpx.Response(200, json={"message": {"content": '{"passed": true}'}})

    resp = await _provider(h).generate_structured(_req(100))
    assert resp.parsed.passed is True
    assert budgets == [100, 200]


@pytest.mark.asyncio
async def test_length_twice_reports_thinking_chars() -> None:
    """test_length_twice_reports_thinking_chars."""

    def h(_r: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"content": "", "thinking": "t" * 50}, "done_reason": "length"},
        )

    with pytest.raises(
        ProviderSchemaError, match=r"thinking_chars=50.*num_predict=200|num_predict=200"
    ):
        await _provider(h).generate_structured(_req(100))
