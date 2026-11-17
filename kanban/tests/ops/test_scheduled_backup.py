# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for scheduled automated backups and snapshot pruning (KANBA-188)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from kanban.jobs.scheduled_backup import (
    DEFAULT_INTERVAL_HOURS,
    DEFAULT_RETENTION_COUNT,
    ScheduledBackupConfig,
    get_backup_schedule,
    list_backups,
    prune_old_backups,
    update_backup_schedule,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_scheduled_backup_config_defaults() -> None:
    """Test default configuration serialization and deserialization."""
    config = ScheduledBackupConfig()
    assert config.enabled is False
    assert config.interval_hours == DEFAULT_INTERVAL_HOURS
    assert config.retention_count == DEFAULT_RETENTION_COUNT
    assert config.last_run_at is None
    assert config.next_run_at is None

    as_dict = config.to_dict()
    assert as_dict["enabled"] is False

    from_dict = ScheduledBackupConfig.from_dict(as_dict)
    assert from_dict.interval_hours == DEFAULT_INTERVAL_HOURS


def test_get_and_update_backup_schedule(tmp_path: Path) -> None:
    """Test updating and reading schedule configuration from disk."""
    config_file = tmp_path / "backup_schedule.json"

    initial = get_backup_schedule(config_file)
    assert initial["enabled"] is False

    updated = update_backup_schedule(
        enabled=True,
        interval_hours=12,
        retention_count=5,
        config_path=config_file,
    )
    assert updated["enabled"] is True
    assert updated["interval_hours"] == 12
    assert updated["retention_count"] == 5
    assert updated["next_run_at"] is not None

    reloaded = get_backup_schedule(config_file)
    assert reloaded["enabled"] is True
    assert reloaded["interval_hours"] == 12
    assert reloaded["retention_count"] == 5

    # Invalid values raise ValueError
    with pytest.raises(ValueError, match="interval_hours must be at least 1"):
        update_backup_schedule(
            enabled=True, interval_hours=0, retention_count=5, config_path=config_file
        )

    with pytest.raises(ValueError, match="retention_count must be at least 1"):
        update_backup_schedule(
            enabled=True, interval_hours=12, retention_count=0, config_path=config_file
        )


def test_list_and_prune_backups(tmp_path: Path) -> None:
    """Test listing and pruning backup files based on retention count."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Empty initially
    assert list_backups(backup_dir) == []

    # Create 5 snapshots
    now = datetime.now(UTC)
    for i in range(5):
        file_path = backup_dir / f"kanban-backup-{i:02d}.kbbak"
        file_path.write_bytes(f"DATA_{i}".encode())
        # Set mtime staggered
        mtime = (now + timedelta(minutes=i * 10)).timestamp()
        os.utime(file_path, (mtime, mtime))

    backups = list_backups(backup_dir)
    assert len(backups) == 5
    assert backups[0]["filename"] == "kanban-backup-04.kbbak"

    # Prune keeping 3
    pruned = prune_old_backups(backup_dir, retention_count=3)
    assert pruned == 2

    remaining = list_backups(backup_dir)
    assert len(remaining) == 3
    filenames = [b["filename"] for b in remaining]
    assert "kanban-backup-04.kbbak" in filenames
    assert "kanban-backup-03.kbbak" in filenames
    assert "kanban-backup-02.kbbak" in filenames
    assert "kanban-backup-01.kbbak" not in filenames
    assert "kanban-backup-00.kbbak" not in filenames
