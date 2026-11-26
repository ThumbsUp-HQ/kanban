# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Application factory for KAN-413 workout with wired ProviderRouter for Sparkle FIM."""

from __future__ import annotations

import ipaddress
from typing import Any
from uuid import uuid4

from pydantic import HttpUrl

from agent.providers.ollama import OllamaProvider, OllamaSettings
from agent.providers.router import RouteCandidate
from kanban.app import create_app as _base_create_app


def create_app() -> Any:
    """Create Kanban application with wired ProviderRouter and RouteCandidates."""
    app = _base_create_app()
    ollama_settings = OllamaSettings(
        base_url=HttpUrl("http://127.0.0.1:11435"),
        allowed_ollama_cidrs=(ipaddress.ip_network("127.0.0.1/32"),),
        model_allowlist=(
            "llama3.2:latest",
            "qwen2.5-coder:latest",
            "default",
            "local",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gpt-4o",
            "gpt-4o-mini",
        ),
    )
    provider = OllamaProvider(settings=ollama_settings)
    candidate = RouteCandidate(
        provider_config_id=uuid4(),
        provider=provider,
        residency_tier="local",
        priority=10,
    )
    app.state.sparkle_route_candidates = (candidate,)
    return app
