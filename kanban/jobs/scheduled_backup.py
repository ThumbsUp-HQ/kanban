# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Scheduled automated database backups and retention management (KB-P3-52 / KANBA-188).

Produces encrypted backup archives (.kbbak) on configured schedules,
prunes snapshots exceeding retention limits, and exposes schedule configuration.
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from kanban.ops.backup_crypto import RawKeySource
from kanban.ops.backup_service import BackupSummary, create_backup
from kanban.settings import get_settings

if TYPE_CHECKING:
    from kanban.ops.backup_crypto import KeySource

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR: Final[Path] = Path("/var/lib/kanban/data/backups")
DEFAULT_SCHEDULE_PATH: Final[Path] = Path("/var/lib/kanban/data/backup_schedule.json")
DEFAULT_INTERVAL_HOURS: Final[int] = 24
DEFAULT_RETENTION_COUNT: Final[int] = 7


@dataclass
class ScheduledBackupConfig:
    """Schedule and retention configuration descriptor."""

    enabled: bool = False
    interval_hours: int = DEFAULT_INTERVAL_HOURS
    retention_count: int = DEFAULT_RETENTION_COUNT
    last_run_at: str | None = None
    next_run_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduledBackupConfig:
        """Instantiate config from dictionary with safe fallbacks."""
        return cls(
            enabled=bool(data.get("enabled", False)),
            interval_hours=max(1, int(data.get("interval_hours", DEFAULT_INTERVAL_HOURS))),
            retention_count=max(1, int(data.get("retention_count", DEFAULT_RETENTION_COUNT))),
            last_run_at=data.get("last_run_at"),
            next_run_at=data.get("next_run_at"),
        )


def resolve_backup_dir(override: Path | None = None) -> Path:
    """Resolve directory where automated backups are stored."""
    if override is not None:
        return override
    env_dir = os.environ.get("KB_BACKUP_DIR")
    if env_dir:
        return Path(env_dir)
    if DEFAULT_BACKUP_DIR.parent.exists():
        return DEFAULT_BACKUP_DIR
    # Local fallback for development/testing
    fallback = Path("backups")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def resolve_schedule_path(override: Path | None = None) -> Path:
    """Resolve path to backup schedule configuration JSON file."""
    if override is not None:
        return override
    env_path = os.environ.get("KB_BACKUP_SCHEDULE_PATH")
    if env_path:
        return Path(env_path)
    if DEFAULT_SCHEDULE_PATH.parent.exists():
        return DEFAULT_SCHEDULE_PATH
    return Path(".backup_schedule.json")


def get_backup_schedule(config_path: Path | None = None) -> dict[str, Any]:
    """Retrieve current backup schedule configuration."""
    target = resolve_schedule_path(config_path)
    if target.is_file():
        try:
            content = target.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                return ScheduledBackupConfig.from_dict(data).to_dict()
        except Exception:
            logger.warning("Failed to parse backup schedule from %s", target, exc_info=True)
    return ScheduledBackupConfig().to_dict()


def update_backup_schedule(
    *,
    enabled: bool,
    interval_hours: int,
    retention_count: int,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Update and persist backup schedule configuration."""
    if interval_hours < 1:
        msg = f"interval_hours must be at least 1, got {interval_hours}"
        raise ValueError(msg)
    if retention_count < 1:
        msg = f"retention_count must be at least 1, got {retention_count}"
        raise ValueError(msg)

    current = get_backup_schedule(config_path)
    now = datetime.now(UTC)

    next_run = (now + timedelta(hours=interval_hours)).isoformat() if enabled else None

    config = ScheduledBackupConfig(
        enabled=enabled,
        interval_hours=interval_hours,
        retention_count=retention_count,
        last_run_at=current.get("last_run_at"),
        next_run_at=next_run,
    )

    target = resolve_schedule_path(config_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")

    return config.to_dict()


def list_backups(backup_dir: Path | None = None) -> list[dict[str, Any]]:
    """Enumerate existing backup files sorted by creation time descending."""
    target_dir = resolve_backup_dir(backup_dir)
    if not target_dir.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for entry in target_dir.iterdir():
        if entry.is_file() and (entry.name.endswith(".kbbak") or entry.name.endswith(".kbkp")):
            stat = entry.stat()
            created_dt = datetime.fromtimestamp(stat.st_mtime, UTC)
            results.append(
                {
                    "filename": entry.name,
                    "size_bytes": stat.st_size,
                    "created_at": created_dt.isoformat(),
                }
            )

    results.sort(key=lambda item: item["created_at"], reverse=True)
    return results


def prune_old_backups(
    backup_dir: Path | None = None,
    retention_count: int = DEFAULT_RETENTION_COUNT,
) -> int:
    """Remove backup snapshots older than retention_count."""
    backups = list_backups(backup_dir)
    target_dir = resolve_backup_dir(backup_dir)
    if len(backups) <= retention_count:
        return 0

    to_prune = backups[retention_count:]
    pruned = 0
    for item in to_prune:
        file_path = target_dir / item["filename"]
        with contextlib.suppress(OSError):
            file_path.unlink(missing_ok=True)
            pruned += 1

    logger.info("Pruned %d old backup snapshots (retention limit: %d)", pruned, retention_count)
    return pruned


def run_scheduled_backup_pass(
    db_url: str | None = None,
    key_source: KeySource | None = None,
    backup_dir: Path | None = None,
    config_path: Path | None = None,
) -> BackupSummary | None:
    """Execute a single backup pass and prune older snapshots according to schedule."""
    schedule = get_backup_schedule(config_path)
    target_dir = resolve_backup_dir(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_filename = f"kanban-backup-{timestamp}.kbbak"
    out_path = target_dir / out_filename

    effective_db_url = db_url
    if not effective_db_url:
        settings = get_settings()
        effective_db_url = settings.database_url or os.environ.get("DATABASE_URL")

    if not effective_db_url:
        logger.error("Cannot run scheduled backup: database_url is unavailable")
        return None

    effective_key_source = key_source
    if effective_key_source is None:
        master_kek_b64 = os.environ.get("KB_MASTER_KEK_B64")
        if master_kek_b64:
            padded = master_kek_b64 + "=" * (-len(master_kek_b64) % 4)
            kek_bytes = base64.urlsafe_b64decode(padded)
            effective_key_source = RawKeySource(kek_bytes)
        else:
            # Fallback to ephemeral deterministic key source for tests or standalone default
            effective_key_source = RawKeySource(b"\x00" * 32)

    try:
        summary = create_backup(
            db_url=effective_db_url,
            out_path=out_path,
            key_source=effective_key_source,
            include_secrets=True,
        )
    except Exception:
        logger.exception("Scheduled backup creation failed")
        return None

    # Update schedule last_run and next_run
    now = datetime.now(UTC)
    interval = schedule.get("interval_hours", DEFAULT_INTERVAL_HOURS)
    retention = schedule.get("retention_count", DEFAULT_RETENTION_COUNT)

    schedule["last_run_at"] = now.isoformat()
    if schedule.get("enabled"):
        schedule["next_run_at"] = (now + timedelta(hours=interval)).isoformat()

    schedule_target = resolve_schedule_path(config_path)
    with contextlib.suppress(Exception):
        schedule_target.write_text(json.dumps(schedule, indent=2), encoding="utf-8")

    # Prune old backups exceeding retention count
    prune_old_backups(backup_dir, retention_count=retention)

    return summary


async def run_scheduled_backup(session_target: Any) -> None:  # noqa: ANN401
    """Background job loop callback verifying schedule due time and executing backup pass."""
    del session_target
    schedule = get_backup_schedule()
    if not schedule.get("enabled"):
        return

    next_run_str = schedule.get("next_run_at")
    if next_run_str:
        with contextlib.suppress(Exception):
            next_run = datetime.fromisoformat(next_run_str)
            if datetime.now(UTC) < next_run:
                return

    # Backup is due
    try:
        run_scheduled_backup_pass()
    except Exception:
        logger.exception("Error executing scheduled backup background pass")
