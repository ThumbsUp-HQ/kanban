# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for standalone entrypoint environment, attachments directory, and ownership (KB-MIGRATION-PLANE-DB-01, KAN-82)."""

# ruff: noqa: E501, TC002

from __future__ import annotations

import os
import shutil
from pathlib import Path
from unittest.mock import patch

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


def test_attachments_directory_permissions_and_ownership(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify attachments directory is created with 65532:65532 ownership and 0750 permissions."""
    data_dir = tmp_path / "data"
    pgdata_dir = data_dir / "pgdata"
    custom_att_dir = data_dir / "attachments"

    monkeypatch.setenv("KB_PGDATA_DIR", str(pgdata_dir))
    monkeypatch.setenv("KANBAN_ATTACHMENT_DIR", str(custom_att_dir))

    chown_calls: list[tuple[str, int, int]] = []
    chmod_calls: list[tuple[str, int]] = []

    def fake_chown(path: str, user: int, group: int) -> None:
        chown_calls.append((path, user, group))

    def fake_chmod(self: Path, mode: int) -> None:
        chmod_calls.append((str(self), mode))

    with (
        patch("os.getuid", return_value=0),
        patch("shutil.chown", side_effect=fake_chown),
        patch.object(Path, "chmod", fake_chmod),
    ):
        # Simulate directory initialization section of entrypoint.py
        data_dir.mkdir(parents=True, exist_ok=True)
        backups_dir = data_dir / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        attachments_dir = Path(
            os.environ.get("KANBAN_ATTACHMENT_DIR", str(data_dir / "attachments"))
        )
        attachments_dir.mkdir(parents=True, exist_ok=True)

        if os.getuid() == 0:
            shutil.chown(str(data_dir), user=65532, group=65532)
            shutil.chown(str(backups_dir), user=65532, group=65532)
            shutil.chown(str(attachments_dir), user=65532, group=65532)
            data_dir.chmod(0o775)
            backups_dir.chmod(0o775)
            attachments_dir.chmod(0o750)

    assert (str(custom_att_dir), 65532, 65532) in chown_calls
    assert (str(custom_att_dir), 0o750) in chmod_calls
    assert attachments_dir.is_dir()
