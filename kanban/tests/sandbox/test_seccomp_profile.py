# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for strict OCI / Kafel seccomp-BPF sandbox profile (KB-P5-14, S13.3)."""

from __future__ import annotations

import json
from pathlib import Path

FORBIDDEN_SYSCALLS: frozenset[str] = frozenset(
    [
        "ptrace",
        "mount",
        "umount2",
        "pivot_root",
        "chroot",
        "unshare",
        "setns",
        "clone3",
        "bpf",
        "perf_event_open",
        "userfaultfd",
        "io_uring_setup",
        "io_uring_enter",
        "keyctl",
        "add_key",
        "request_key",
        "kexec_load",
        "init_module",
        "finit_module",
        "acct",
        "swapon",
        "reboot",
        "syslog",
    ]
)


def test_seccomp_profile_structure_and_defaults() -> None:
    """Assert defaultAction is SCMP_ACT_ERRNO with EPERM (1) and supports x86_64 + aarch64."""
    profile_path = Path("deploy/seccomp/sandbox-profile.json")
    assert profile_path.exists(), f"Profile not found at {profile_path}"

    with profile_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("defaultAction") == "SCMP_ACT_ERRNO"
    assert data.get("defaultErrnoRet") == 1

    architectures = set(data.get("architectures", []))
    assert "SCMP_ARCH_X86_64" in architectures
    assert "SCMP_ARCH_AARCH64" in architectures


def test_seccomp_profile_socket_restriction() -> None:
    """Assert socket syscall is allowed strictly when domain arg 0 == AF_UNIX (1)."""
    profile_path = Path("deploy/seccomp/sandbox-profile.json")
    with profile_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    socket_rules = [
        rule
        for rule in data.get("syscalls", [])
        if "socket" in rule.get("names", []) and rule.get("action") == "SCMP_ACT_ALLOW"
    ]
    assert len(socket_rules) == 1, "Expected exactly one socket allow rule"
    socket_rule = socket_rules[0]

    args = socket_rule.get("args", [])
    assert len(args) == 1, "Expected exact parameter filter on socket syscall"
    arg0 = args[0]
    assert arg0.get("index") == 0
    assert arg0.get("value") == 1  # AF_UNIX = 1
    assert arg0.get("op") == "SCMP_CMP_EQ"


def test_seccomp_profile_forbidden_syscalls_absent() -> None:
    """Assert none of the 23 container escape syscalls appear in any SCMP_ACT_ALLOW rule."""
    profile_path = Path("deploy/seccomp/sandbox-profile.json")
    with profile_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    allowed_names: set[str] = set()
    for rule in data.get("syscalls", []):
        if rule.get("action") == "SCMP_ACT_ALLOW":
            allowed_names.update(rule.get("names", []))

    for forbidden in FORBIDDEN_SYSCALLS:
        assert forbidden not in allowed_names, (
            f"Forbidden escape syscall '{forbidden}' must NOT be allowed in seccomp profile"
        )
