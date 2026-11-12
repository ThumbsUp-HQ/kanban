# Copyright 2026 Kanban Platform Contributors
"""Provider factory registry for instantiating LLMProvider adapters."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agent.providers.gemini import GeminiProvider, GeminiSettings
from agent.providers.ollama import OllamaProvider, OllamaSettings
from agent.providers.openai_provider import OpenAIProvider, OpenAISettings
from agent.testing.fixtures import Cassette, FixtureLLMProvider

if TYPE_CHECKING:
    import httpx

    from agent.providers.base import LLMProvider

__all__ = [
    "build_provider",
]


def _build_ollama(settings: object, transport: httpx.AsyncBaseTransport | None) -> LLMProvider:
    if isinstance(settings, OllamaSettings):
        return OllamaProvider(settings, transport=transport)
    if isinstance(settings, dict):
        return OllamaProvider(OllamaSettings.model_validate(settings), transport=transport)
    msg = "Settings for ollama provider must be OllamaSettings or dict"
    raise TypeError(msg)


def _build_gemini(settings: object, transport: httpx.AsyncBaseTransport | None) -> LLMProvider:
    if isinstance(settings, GeminiSettings):
        return GeminiProvider(settings, transport=transport)
    if isinstance(settings, dict):
        return GeminiProvider(GeminiSettings.model_validate(settings), transport=transport)
    msg = "Settings for gemini provider must be GeminiSettings or dict"
    raise TypeError(msg)


def _build_openai(settings: object, transport: httpx.AsyncBaseTransport | None) -> LLMProvider:
    if isinstance(settings, OpenAISettings):
        return OpenAIProvider(settings, transport=transport)
    if isinstance(settings, dict):
        return OpenAIProvider(OpenAISettings.model_validate(settings), transport=transport)
    msg = "Settings for openai provider must be OpenAISettings or dict"
    raise TypeError(msg)


def _build_fixture(settings: object) -> LLMProvider:
    if isinstance(settings, (Cassette, str, Path, list)):
        return FixtureLLMProvider(settings)
    msg = "Settings for fixture provider must be Cassette, str, Path, or list"
    raise TypeError(msg)


def build_provider(
    kind: str,
    settings: object,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> LLMProvider:
    """Build and return an LLMProvider instance corresponding to kind and settings."""
    if kind == "ollama":
        return _build_ollama(settings, transport)
    if kind == "gemini":
        return _build_gemini(settings, transport)
    if kind == "openai":
        return _build_openai(settings, transport)
    if kind == "fixture":
        return _build_fixture(settings)

    msg = f"Unknown provider kind '{kind}'"
    raise ValueError(msg)
