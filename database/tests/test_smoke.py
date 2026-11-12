"""Smoke test verifying database package version."""

from database import __version__


def test_database_smoke() -> None:
    """Verify that database package exports version 0.0.0."""
    assert __version__ == "0.0.0"
