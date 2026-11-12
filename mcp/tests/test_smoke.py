"""Smoke test verifying mcp package version."""

from mcp import __version__


def test_mcp_smoke() -> None:
    """Verify that mcp package exports version 0.0.0."""
    assert __version__ == "0.0.0"
