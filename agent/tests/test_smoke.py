# Copyright 2026 Kanban Platform Contributors
"""Smoke tests for kanban-agent package initialization."""

from agent import __version__


def test_agent_smoke() -> None:
    """Verify package version is initialized properly."""
    assert __version__ == "0.0.0"
