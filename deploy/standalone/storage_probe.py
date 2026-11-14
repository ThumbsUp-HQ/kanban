"""Storage persistence detection and status reporter for standalone deployment.

Probes /proc/mounts and /proc/self/mountinfo to detect ephemeral overlay or anonymous
Docker storage, emits high-visibility console warnings, and writes standalone_status.json.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from typing import Final

EPHEMERAL_WARNING: Final[str] = (
    "⚠️ Ephemeral Storage: Mount -v kanban_data:/var/lib/kanban/data "
    "to persist data across container removal\n"
)
DEFAULT_STATUS_PATH: Final[Path] = Path("/run/kanban/standalone_status.json")
ANON_DOCKER_VOLUME_REGEX: Final[re.Pattern[str]] = re.compile(
    r"/var/lib/docker/volumes/[0-9a-f]{64}/_data"
)
_MIN_MOUNT_PARTS: Final[int] = 3
_MIN_MOUNTINFO_PARTS: Final[int] = 5
_STATUS_FILE_MODE: Final[int] = 0o644
_STATUS_DIR_MODE: Final[int] = 0o755


@dataclass(frozen=True)
class StandaloneStatus:
    """Runtime storage persistence and deployment status descriptor."""

    mode: Literal["standalone_embedded_pg", "external_db"]
    persistent_volume: bool
    data_mount_point: str
    data_mount_fstype: str
    generated_at: str  # ISO-8601 UTC
    tier_b_sandbox_available: bool = False
    tier_b_unavailable_reason: str | None = None


def decode_octal_escapes(raw: str) -> str:
    r"""Decode octal escape sequences commonly found in /proc/mounts (e.g. \040 -> space)."""
    return re.sub(
        r"\\([0-7]{3})",
        lambda m: chr(int(m.group(1), 8)),
        raw,
    )


def _is_path_prefix(mount_point: str, target_dir: str) -> bool:
    """Determine if mount_point is a path prefix of target_dir."""
    mp = mount_point.rstrip("/")
    td = target_dir.rstrip("/")
    if not mp:
        return True
    return td == mp or td.startswith(f"{mp}/")


def _read_mounts(mounts_text: str | None) -> str:
    """Return mounts content from argument or read from /proc/mounts."""
    if mounts_text is not None:
        return mounts_text
    mounts_path = Path("/proc/mounts")
    return mounts_path.read_text(encoding="utf-8") if mounts_path.is_file() else ""


def _read_mountinfo(
    mountinfo_text: str | None,
    *,
    read_host_fallback: bool,
) -> str | None:
    """Return mountinfo content from argument or read from /proc/self/mountinfo."""
    if mountinfo_text is not None:
        return mountinfo_text
    if read_host_fallback:
        mountinfo_path = Path("/proc/self/mountinfo")
        if mountinfo_path.is_file():
            return mountinfo_path.read_text(encoding="utf-8")
    return None


def _parse_matching_mounts(effective_mounts: str, norm_data_dir: str) -> list[tuple[str, str]]:
    """Extract (mount_point, fstype) tuples that are prefixes of norm_data_dir."""
    matching: list[tuple[str, str]] = []
    for raw_line in effective_mounts.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < _MIN_MOUNT_PARTS:
            continue
        mount_point = decode_octal_escapes(parts[1])
        fstype = parts[2]
        if _is_path_prefix(mount_point, norm_data_dir):
            matching.append((mount_point, fstype))
    return matching


def _is_anon_volume(effective_mountinfo: str, target_mount: str) -> bool:
    """Check if target_mount corresponds to an anonymous Docker volume in mountinfo."""
    for raw_line in effective_mountinfo.splitlines():
        parts = raw_line.strip().split()
        if len(parts) >= _MIN_MOUNTINFO_PARTS:
            root_path = parts[3]
            mp = decode_octal_escapes(parts[4])
            if mp == target_mount and ANON_DOCKER_VOLUME_REGEX.search(root_path):
                return True
    return False


def probe(  # noqa: PLR0913
    data_dir: Path,
    mounts_text: str | None = None,
    mountinfo_text: str | None = None,
    mode: Literal["standalone_embedded_pg", "external_db"] = "standalone_embedded_pg",
    *,
    tier_b_sandbox_available: bool = False,
    tier_b_unavailable_reason: str | None = None,
) -> StandaloneStatus:
    """Probe /proc/mounts to determine if data_dir is backed by persistent storage.

    When mounts_text is not supplied, reads /proc/mounts and /proc/self/mountinfo from disk.
    Picks the longest mount point prefix of data_dir.
    Evaluates persistent_volume as False for overlay, tmpfs, anonymous Docker volumes,
    or when no matching mount is found.
    """
    generated_at = datetime.now(UTC).isoformat()
    norm_data_dir = str(data_dir.resolve() if data_dir.exists() else data_dir)

    is_live_probe = mounts_text is None
    effective_mounts = _read_mounts(mounts_text)
    effective_mountinfo = _read_mountinfo(
        mountinfo_text,
        read_host_fallback=is_live_probe,
    )

    matching_mounts = _parse_matching_mounts(effective_mounts, norm_data_dir)
    if not matching_mounts:
        return StandaloneStatus(
            mode=mode,
            persistent_volume=False,
            data_mount_point="",
            data_mount_fstype="",
            generated_at=generated_at,
            tier_b_sandbox_available=tier_b_sandbox_available,
            tier_b_unavailable_reason=tier_b_unavailable_reason,
        )

    # Pick the longest mount point prefix
    matching_mounts.sort(key=lambda item: len(item[0]), reverse=True)
    best_mp, best_fstype = matching_mounts[0]

    # overlay and tmpfs are inherently non-persistent
    persistent = best_fstype.lower() not in ("overlay", "tmpfs")

    # Check for anonymous Docker volume in mountinfo if available
    if persistent and effective_mountinfo and _is_anon_volume(effective_mountinfo, best_mp):
        persistent = False

    return StandaloneStatus(
        mode=mode,
        persistent_volume=persistent,
        data_mount_point=best_mp,
        data_mount_fstype=best_fstype,
        generated_at=generated_at,
        tier_b_sandbox_available=tier_b_sandbox_available,
        tier_b_unavailable_reason=tier_b_unavailable_reason,
    )


def emit_ephemeral_warning() -> None:
    """Print the exact Section 2.2 item 1 ephemeral storage warning to stderr."""
    sys.stderr.write(EPHEMERAL_WARNING)
    sys.stderr.flush()


probe_storage = probe


def write_standalone_status(
    status: StandaloneStatus,
    target_path: Path = DEFAULT_STATUS_PATH,
) -> None:
    """Atomically write StandaloneStatus JSON to target_path with mode 0644."""
    parent = target_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        parent.chmod(_STATUS_DIR_MODE)

    raw_bytes = json.dumps(asdict(status), indent=2).encode("utf-8")
    rand_hex = os.urandom(8).hex()
    tmp_path = parent / f"{target_path.name}.{rand_hex}.tmp"

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(tmp_path), flags, _STATUS_FILE_MODE)
    try:
        os.write(fd, raw_bytes)
        os.fsync(fd)
    finally:
        os.close(fd)

    tmp_path.replace(target_path)
