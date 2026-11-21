# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for standalone entrypoint environment and directory configuration (KB-MIGRATION-PLANE-DB-01)."""

# ruff: noqa: E501, TC002

from __future__ import annotations

import pytest

from deploy.standalone.entrypoint import (
    _PASSTHROUGH_ENV_VARS,
    build_child_env,
)


def test_passthrough_env_vars_includes_attachment_dir() -> None:
    """Verify KANBAN_ATTACHMENT_DIR is explicitly in _PASSTHROUGH_ENV_VARS allowlist."""
    assert "KANBAN_ATTACHMENT_DIR" in _PASSTHROUGH_ENV_VARS


def test_build_child_env_attachment_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify build_child_env defaults KANBAN_ATTACHMENT_DIR to /var/lib/kanban/data/attachments."""
    monkeypatch.delenv("KANBAN_ATTACHMENT_DIR", raising=False)
    env = build_child_env(db_url="postgresql+asyncpg://app@/kanban")
    assert env["KANBAN_ATTACHMENT_DIR"] == "/var/lib/kanban/data/attachments"


def test_build_child_env_attachment_dir_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify build_child_env respects KANBAN_ATTACHMENT_DIR from environment."""
    monkeypatch.setenv("KANBAN_ATTACHMENT_DIR", "/custom/data/attachments")
    env = build_child_env(db_url="postgresql+asyncpg://app@/kanban")
    assert env["KANBAN_ATTACHMENT_DIR"] == "/custom/data/attachments"
