r"""Unit tests for deploy.standalone.storage_probe module.

Covers:
- Longest prefix matching of data_dir against mount points in /proc/mounts.
- Decoding of octal escape sequences (e.g. \\040 for space).
- Ephemeral filesystem detection (overlay, tmpfs -> persistent_volume=False).
- Anonymous Docker volume detection via /proc/self/mountinfo.
- Named Docker volume persistence via /proc/self/mountinfo.
- Fallback when no mount point matches.
- Ephemeral warning emission to stderr.
- Atomic 0644 status file writing.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import TYPE_CHECKING

from deploy.standalone.storage_probe import (
    EPHEMERAL_WARNING,
    StandaloneStatus,
    decode_octal_escapes,
    emit_ephemeral_warning,
    probe,
    write_standalone_status,
)

if TYPE_CHECKING:
    import pytest


def test_decode_octal_escapes() -> None:
    r"""Octal escape sequences such as \040 are decoded to characters."""
    assert decode_octal_escapes(r"/mnt/my\040volume/data") == "/mnt/my volume/data"
    assert decode_octal_escapes(r"/simple/path") == "/simple/path"
    assert decode_octal_escapes(r"/a\011b") == "/a\tb"


def test_probe_overlay_non_persistent() -> None:
    """Overlay filesystem evaluates to persistent_volume=False."""
    mounts = """
overlay / overlay rw,relatime,lowerdir=/l/XYZ,upperdir=/ABC/diff,workdir=/ABC/work 0 0
/dev/sda1 /boot ext4 rw,relatime 0 0
"""
    status = probe(Path("/var/lib/kanban/data"), mounts_text=mounts)
    assert not status.persistent_volume
    assert status.data_mount_point == "/"
    assert status.data_mount_fstype == "overlay"
    assert status.mode == "standalone_embedded_pg"


def test_probe_tmpfs_non_persistent() -> None:
    """Tmpfs mount on data dir evaluates to persistent_volume=False."""
    mounts = """
/dev/sda1 / ext4 rw,relatime 0 0
tmpfs /var/lib/kanban/data tmpfs rw,nosuid,nodev 0 0
"""
    status = probe(Path("/var/lib/kanban/data"), mounts_text=mounts)
    assert not status.persistent_volume
    assert status.data_mount_point == "/var/lib/kanban/data"
    assert status.data_mount_fstype == "tmpfs"


def test_probe_longest_prefix_match() -> None:
    """Longest prefix mount point takes precedence over parent mounts."""
    mounts = """
/dev/sda1 / ext4 rw,relatime 0 0
tmpfs /var tmpfs rw,nosuid 0 0
/dev/sdb1 /var/lib/kanban/data ext4 rw,relatime 0 0
"""
    status = probe(Path("/var/lib/kanban/data/pgdata"), mounts_text=mounts)
    assert status.persistent_volume
    assert status.data_mount_point == "/var/lib/kanban/data"
    assert status.data_mount_fstype == "ext4"


def test_probe_octal_escapes_in_mount_point() -> None:
    r"""Mount points containing octal spaces match correctly."""
    mounts = r"""
/dev/sda1 / ext4 rw 0 0
/dev/sdb1 /var/lib/kanban\040data ext4 rw 0 0
"""
    status = probe(Path("/var/lib/kanban data/sub"), mounts_text=mounts)
    assert status.persistent_volume
    assert status.data_mount_point == "/var/lib/kanban data"
    assert status.data_mount_fstype == "ext4"


def test_probe_no_matching_mount_fail_closed() -> None:
    """Empty or non-matching mounts evaluate fail-closed to persistent_volume=False."""
    mounts = """
# Empty or completely unrelated mounts
/dev/sda1 /other/dir ext4 rw 0 0
"""
    status = probe(Path("/var/lib/kanban/data"), mounts_text=mounts)
    assert not status.persistent_volume
    assert status.data_mount_point == ""
    assert status.data_mount_fstype == ""


def test_probe_anon_docker_volume_detected() -> None:
    """Anonymous 64-hex Docker volume is detected as non-persistent via mountinfo."""
    mounts = """
/dev/sda1 / ext4 rw 0 0
/dev/sda1 /var/lib/kanban/data ext4 rw,relatime 0 0
"""
    # 64-hex characters volume id
    anon_vol_id = "a" * 64
    mountinfo = (
        f"100 50 8:1 /var/lib/docker/volumes/{anon_vol_id}/_data "
        "/var/lib/kanban/data rw - ext4 /dev/sda1 rw\n"
    )
    status = probe(
        Path("/var/lib/kanban/data"),
        mounts_text=mounts,
        mountinfo_text=mountinfo,
    )
    assert not status.persistent_volume
    assert status.data_mount_point == "/var/lib/kanban/data"
    assert status.data_mount_fstype == "ext4"


def test_probe_named_docker_volume_persistent() -> None:
    """Named Docker volume evaluates to persistent_volume=True."""
    mounts = """
/dev/sda1 / ext4 rw 0 0
/dev/sda1 /var/lib/kanban/data ext4 rw,relatime 0 0
"""
    named_mountinfo = (
        "100 50 8:1 /var/lib/docker/volumes/kanban_data/_data "
        "/var/lib/kanban/data rw - ext4 /dev/sda1 rw\n"
    )
    status = probe(
        Path("/var/lib/kanban/data"),
        mounts_text=mounts,
        mountinfo_text=named_mountinfo,
    )
    assert status.persistent_volume
    assert status.data_mount_point == "/var/lib/kanban/data"
    assert status.data_mount_fstype == "ext4"


def test_probe_live_system_fallback(tmp_path: Path) -> None:
    """When mounts_text is None, probe reads live system mounts without crashing."""
    status = probe(tmp_path)
    assert isinstance(status.persistent_volume, bool)
    assert isinstance(status.data_mount_point, str)
    assert isinstance(status.data_mount_fstype, str)
    assert status.mode == "standalone_embedded_pg"


def test_emit_ephemeral_warning(capsys: pytest.CaptureFixture[str]) -> None:
    """emit_ephemeral_warning writes the exact warning text to stderr."""
    emit_ephemeral_warning()
    captured = capsys.readouterr()
    assert captured.err == EPHEMERAL_WARNING
    assert "⚠️ Ephemeral Storage: Mount -v kanban_data:/var/lib/kanban/data" in captured.err


def test_write_standalone_status(tmp_path: Path) -> None:
    """write_standalone_status writes valid JSON atomically with mode 0644."""
    status = StandaloneStatus(
        mode="standalone_embedded_pg",
        persistent_volume=True,
        data_mount_point="/var/lib/kanban/data",
        data_mount_fstype="ext4",
        generated_at="2026-11-11T20:00:00Z",
    )
    target_path = tmp_path / "run" / "standalone_status.json"
    write_standalone_status(status, target_path=target_path)

    assert target_path.is_file()
    # Check permissions 0644
    mode = stat.S_IMODE(target_path.stat().st_mode)
    assert mode == 0o644

    # Check contents
    content = json.loads(target_path.read_text(encoding="utf-8"))
    assert content["mode"] == "standalone_embedded_pg"
    assert content["persistent_volume"] is True
    assert content["data_mount_point"] == "/var/lib/kanban/data"
    assert content["data_mount_fstype"] == "ext4"
    assert content["generated_at"] == "2026-11-11T20:00:00Z"
