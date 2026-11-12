"""Smoke test verifying agent package version."""

from agent import __version__


def test_agent_smoke() -> None:
    """Verify that agent package exports version 0.0.0."""
    assert __version__ == "0.0.0"
