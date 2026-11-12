"""Smoke test verifying kanban package version."""

from kanban import __version__


def test_kanban_smoke() -> None:
    """Verify that kanban package exports version 0.0.0."""
    assert __version__ == "0.0.0"
