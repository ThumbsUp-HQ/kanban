# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for MirrorManager SSH known_hosts persistence and pinning (Problem 1)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from database.models.repo_binding import ProjectRepoBinding
from kanban.repos.mirror import (
    FakeGitCommandRunner,
    GitResult,
    MirrorManager,
    MirrorPolicy,
)
from kanban.security.envelope import StaticKekProvider, seal_bound

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_TEST_KNOWN_HOSTS = (
    "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
)


def _get_test_kek() -> StaticKekProvider:
    return StaticKekProvider(keys={"test-kek-1": b"\xaa" * 32}, current="test-kek-1")


def _create_ssh_binding(
    *,
    ssh_known_hosts: str | None = None,
    credential_bytes: bytes | None = (
        b"-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----"
    ),
) -> tuple[ProjectRepoBinding, StaticKekProvider]:
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    binding_id = uuid.uuid4()
    kek_provider = _get_test_kek()

    ct: bytes | None = None
    dek_kid: str | None = None
    if credential_bytes:
        aad = f"kanban/repo-binding/v1|{binding_id}|{proj_id}".encode()
        sealed = seal_bound(credential_bytes, aad, kek_provider)
        wrapped_len = len(sealed.wrapped_dek)
        ct = wrapped_len.to_bytes(2, "big") + sealed.wrapped_dek + sealed.encrypted_secret_blob
        dek_kid = sealed.dek_kid

    binding = ProjectRepoBinding(
        id=binding_id,
        workspace_id=ws_id,
        project_id=proj_id,
        slug="test-ssh-repo",
        remote_url="ssh://git@github.com/org/repo.git",
        default_ref="main",
        access_mode="bare_git_tools",
        credential_ciphertext=ct,
        credential_dek_kid=dek_kid,
        ssh_known_hosts=ssh_known_hosts,
        created_by=uuid.uuid4(),
    )
    return binding, kek_provider


class InspectingFakeRunner(FakeGitCommandRunner):
    """Runner that inspects files referenced in core.sshCommand during execution."""

    def __init__(self, responses: Sequence[GitResult] | None = None) -> None:
        """Initialize InspectingFakeRunner with pre-canned responses."""
        super().__init__(list(responses) if responses is not None else None)
        self.inspected_known_hosts_content: str | None = None
        self.ssh_command_used: str | None = None

    async def run(
        self,
        argv: Sequence[str],
        env: Mapping[str, str],
        timeout_seconds: float = 60.0,
    ) -> GitResult:
        """Execute git command and inspect known_hosts file arguments."""
        for arg in argv:
            if arg.startswith("core.sshCommand="):
                self.ssh_command_used = arg.split("core.sshCommand=", 1)[1]
                match = re.search(r"-o UserKnownHostsFile=([^\s]+)", self.ssh_command_used)
                if match:
                    kh_path = Path(match.group(1))
                    if kh_path.exists():  # noqa: ASYNC240
                        self.inspected_known_hosts_content = kh_path.read_text(  # noqa: ASYNC240
                            encoding="utf-8"
                        )
        return await super().run(argv, env, timeout_seconds=timeout_seconds)


@pytest.mark.asyncio
async def test_mirror_manager_writes_configured_ssh_known_hosts(tmp_path: Path) -> None:
    """Verify admin-configured ssh_known_hosts is written into the ephemeral known_hosts file."""
    runner = InspectingFakeRunner(
        responses=[
            GitResult(0, "cloned\n", ""),
            GitResult(0, "0123456789abcdef0123456789abcdef01234567\n", ""),
        ]
    )
    binding, kek = _create_ssh_binding(ssh_known_hosts=_TEST_KNOWN_HOSTS)

    manager = MirrorManager(
        base_dir=tmp_path / "mirrors",
        runner=runner,
        policy=MirrorPolicy(allow_file_protocol=False),
        kek_provider=kek,
    )

    await manager.clone_or_fetch(
        binding,
        resolver=lambda _h: ["140.82.121.3"],
        pinned_ip="140.82.121.3",
    )

    assert runner.ssh_command_used is not None
    assert "-o StrictHostKeyChecking=yes" in runner.ssh_command_used
    assert "-o BatchMode=yes" in runner.ssh_command_used
    assert runner.inspected_known_hosts_content is not None
    assert _TEST_KNOWN_HOSTS in runner.inspected_known_hosts_content


@pytest.mark.asyncio
async def test_mirror_manager_empty_known_hosts_when_unconfigured(tmp_path: Path) -> None:
    """Verify empty known_hosts file is touched when ssh_known_hosts is not configured."""
    runner = InspectingFakeRunner(
        responses=[
            GitResult(0, "cloned\n", ""),
            GitResult(0, "0123456789abcdef0123456789abcdef01234567\n", ""),
        ]
    )
    binding, kek = _create_ssh_binding(ssh_known_hosts=None)

    manager = MirrorManager(
        base_dir=tmp_path / "mirrors",
        runner=runner,
        policy=MirrorPolicy(allow_file_protocol=False),
        kek_provider=kek,
    )

    await manager.clone_or_fetch(
        binding,
        resolver=lambda _h: ["140.82.121.3"],
        pinned_ip="140.82.121.3",
    )

    assert runner.ssh_command_used is not None
    assert runner.inspected_known_hosts_content == ""
