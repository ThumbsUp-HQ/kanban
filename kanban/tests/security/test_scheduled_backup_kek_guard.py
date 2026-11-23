# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: SLF001, E501
"""Security unit tests for scheduled backup KEK enforcement (KAN-340).

Verifies:
  1. Missing KB_MASTER_KEK_B64 with key_source=None raises ValueError refusing all-zero fallback key.
  2. Zero backup files are created when master KEK is missing.
  3. Valid KB_MASTER_KEK_B64 in environment constructs valid RawKeySource from decoded bytes.
  4. Explicit KeySource passed directly as argument succeeds without KB_MASTER_KEK_B64 in env.
  5. Background loop run_scheduled_backup catches the ValueError and logs without crashing.
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from kanban.jobs.scheduled_backup import (
    run_scheduled_backup,
    run_scheduled_backup_pass,
    update_backup_schedule,
)
from kanban.ops.backup_crypto import RawKeySource

if TYPE_CHECKING:
    from pathlib import Path


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def test_case_1_missing_kek_rejects_with_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 1: Missing KB_MASTER_KEK_B64 raises ValueError refusing all-zero key fallback."""
    monkeypatch.delenv("KB_MASTER_KEK_B64", raising=False)
    backup_dir = tmp_path / "backups"
    config_file = tmp_path / "schedule.json"

    with pytest.raises(
        ValueError,
        match="Missing KB_MASTER_KEK_B64 environment variable: refusing all-zero key backup encryption",
    ):
        run_scheduled_backup_pass(
            db_url="postgresql+asyncpg://kanban_app@localhost/testdb",
            key_source=None,
            backup_dir=backup_dir,
            config_path=config_file,
        )

    # Verify zero files created in backup directory
    created_files = list(backup_dir.glob("*.kbbak"))
    assert len(created_files) == 0, "No backup files must be created with missing KEK"


def test_case_2_valid_kb_master_kek_b64_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 2: Valid KB_MASTER_KEK_B64 in environment is decoded into RawKeySource."""
    valid_key = b"v" * 32
    monkeypatch.setenv("KB_MASTER_KEK_B64", _b64(valid_key))

    backup_dir = tmp_path / "backups"
    config_file = tmp_path / "schedule.json"

    with mock.patch("kanban.jobs.scheduled_backup.create_backup") as mock_create:
        mock_create.return_value = mock.MagicMock(
            backup_path=backup_dir / "test.kbbak",
            raw_bytes=100,
            compressed_bytes=80,
            tables_exported=5,
            duration_s=0.5,
            sha256="test-sha",
        )

        summary = run_scheduled_backup_pass(
            db_url="postgresql+asyncpg://kanban_app@localhost/testdb",
            key_source=None,
            backup_dir=backup_dir,
            config_path=config_file,
        )
        assert summary is not None
        mock_create.assert_called_once()
        passed_key_source = mock_create.call_args.kwargs["key_source"]
        assert isinstance(passed_key_source, RawKeySource)
        assert passed_key_source._key == valid_key


def test_case_3_explicit_key_source_bypasses_env_var(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 3: Explicit KeySource parameter succeeds even when KB_MASTER_KEK_B64 is missing."""
    monkeypatch.delenv("KB_MASTER_KEK_B64", raising=False)
    backup_dir = tmp_path / "backups"
    config_file = tmp_path / "schedule.json"

    explicit_key = b"e" * 32
    explicit_source = RawKeySource(explicit_key)

    with mock.patch("kanban.jobs.scheduled_backup.create_backup") as mock_create:
        mock_create.return_value = mock.MagicMock(
            backup_path=backup_dir / "test.kbbak",
            raw_bytes=100,
            compressed_bytes=80,
            tables_exported=5,
            duration_s=0.5,
            sha256="test-sha",
        )

        summary = run_scheduled_backup_pass(
            db_url="postgresql+asyncpg://kanban_app@localhost/testdb",
            key_source=explicit_source,
            backup_dir=backup_dir,
            config_path=config_file,
        )
        assert summary is not None
        mock_create.assert_called_once()
        assert mock_create.call_args.kwargs["key_source"] is explicit_source


@pytest.mark.asyncio
async def test_case_4_background_loop_logs_error_without_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 4: Background scheduled backup loop catches ValueError and logs without crashing."""
    monkeypatch.delenv("KB_MASTER_KEK_B64", raising=False)
    config_file = tmp_path / "schedule.json"

    update_backup_schedule(
        enabled=True,
        interval_hours=1,
        retention_count=3,
        config_path=config_file,
    )

    with (
        mock.patch(
            "kanban.jobs.scheduled_backup.resolve_schedule_path",
            return_value=config_file,
        ),
        mock.patch(
            "kanban.jobs.scheduled_backup.run_scheduled_backup_pass",
            side_effect=ValueError("Missing KB_MASTER_KEK_B64"),
        ),
    ):
        # Must execute cleanly without raising exception
        await run_scheduled_backup(session_target=None)
