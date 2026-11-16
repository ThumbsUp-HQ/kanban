# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for bare git mirror manager and execution sandboxing (KB-P5-19b, S14.3)."""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from pathlib import Path

import pytest

from database.models.repo_binding import ProjectRepoBinding
from kanban.repos.mirror import (
    ExecGitCommandRunner,
    FakeGitCommandRunner,
    GitExecutionError,
    GitResult,
    MirrorManager,
    MirrorPolicy,
    MirrorSizeLimitError,
    MirrorTimeoutError,
)
from kanban.security.envelope import StaticKekProvider, seal_bound


def _get_test_kek() -> StaticKekProvider:
    return StaticKekProvider(keys={"test-kek-1": b"\xaa" * 32}, current="test-kek-1")


def _create_binding(  # noqa: PLR0913
    *,
    workspace_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    remote_url: str = "https://github.com/example/repo.git",
    default_ref: str = "main",
    access_mode: str = "ro",
    credential_bytes: bytes | None = None,
    kek_provider: StaticKekProvider | None = None,
) -> ProjectRepoBinding:
    """Create a ProjectRepoBinding model instance for testing."""
    ws_id = workspace_id or uuid.uuid4()
    proj_id = project_id or uuid.uuid4()
    binding_id = uuid.uuid4()

    ct: bytes | None = None
    dek_kid: str | None = None
    if credential_bytes and kek_provider:
        aad = f"kanban/repo-binding/v1|{binding_id}|{proj_id}".encode()
        sealed = seal_bound(credential_bytes, aad, kek_provider)
        wrapped_len = len(sealed.wrapped_dek)
        ct = wrapped_len.to_bytes(2, "big") + sealed.wrapped_dek + sealed.encrypted_secret_blob
        dek_kid = sealed.dek_kid

    return ProjectRepoBinding(
        id=binding_id,
        workspace_id=ws_id,
        project_id=proj_id,
        remote_url=remote_url,
        default_ref=default_ref,
        access_mode=access_mode,
        credential_ciphertext=ct,
        credential_dek_kid=dek_kid,
    )


@pytest.mark.asyncio
async def test_fake_runner_records_calls_and_isolated_env(tmp_path: Path) -> None:
    """Fake runner captures exact hardened argv flags and isolated environment."""
    fake_runner = FakeGitCommandRunner(
        responses=[
            GitResult(0, "cloned\n", ""),
            GitResult(0, "0123456789abcdef0123456789abcdef01234567\n", ""),
        ]
    )
    manager = MirrorManager(
        base_dir=tmp_path / "mirrors",
        runner=fake_runner,
        policy=MirrorPolicy(allow_file_protocol=False),
    )

    binding = _create_binding(remote_url="https://github.com/org/repo.git")
    await manager.clone_or_fetch(binding, pinned_ip="140.82.121.3")

    assert len(fake_runner.calls) == 2
    clone_argv, clone_env = fake_runner.calls[0]

    # Verify security flags
    assert "core.hooksPath=/dev/null" in clone_argv
    assert "protocol.file.allow=never" in clone_argv
    assert "protocol.ext.allow=never" in clone_argv
    assert "core.fsmonitor=false" in clone_argv
    assert "submodule.recurse=false" in clone_argv
    assert "transfer.fsckObjects=true" in clone_argv
    assert "http.curloptResolve=github.com:443:140.82.121.3" in clone_argv
    assert "clone" in clone_argv
    assert "--mirror" in clone_argv
    assert "--no-local" in clone_argv
    assert "--no-hardlinks" in clone_argv

    # Verify clean replaced environment (no leakage of OS env)
    assert clone_env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert clone_env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert clone_env["GIT_TERMINAL_PROMPT"] == "0"
    assert clone_env["GIT_ALLOW_PROTOCOL"] == "https:ssh"
    assert "PATH" in clone_env
    assert "HOME" in clone_env

    # Rev-parse call verified
    rev_argv, _ = fake_runner.calls[1]
    assert "rev-parse" in rev_argv
    assert "--verify" in rev_argv
    assert "--end-of-options" in rev_argv
    assert f"{binding.default_ref}^{{commit}}" in rev_argv
    assert binding.last_fetched_commit == "0123456789abcdef0123456789abcdef01234567"
    assert binding.last_fetch_error is None


@pytest.mark.asyncio
async def test_fetch_called_when_mirror_head_exists(tmp_path: Path) -> None:
    """When mirror HEAD exists, fetch --prune --no-tags origin is invoked."""
    fake_runner = FakeGitCommandRunner(
        responses=[
            GitResult(0, "fetched\n", ""),
            GitResult(0, "abcdef0123456789abcdef0123456789abcdef01\n", ""),
        ]
    )
    manager = MirrorManager(
        base_dir=tmp_path / "mirrors",
        runner=fake_runner,
        policy=MirrorPolicy(allow_file_protocol=False),
    )

    binding = _create_binding(remote_url="https://github.com/org/repo.git")
    mirror_dir = manager.mirror_path(binding)
    mirror_dir.mkdir(parents=True, exist_ok=True)
    (mirror_dir / "HEAD").write_text("ref: refs/heads/main\n")

    await manager.clone_or_fetch(binding, pinned_ip="140.82.121.4")

    assert len(fake_runner.calls) == 2
    fetch_argv, _ = fake_runner.calls[0]
    assert "fetch" in fetch_argv
    assert "--prune" in fetch_argv
    assert "--no-tags" in fetch_argv
    assert "origin" in fetch_argv
    assert f"--git-dir={mirror_dir}" in fetch_argv


@pytest.mark.asyncio
async def test_credential_decryption_and_zeroization_https(tmp_path: Path) -> None:
    """HTTPS bearer token is written to 0600 file and zeroized/unlinked in finally block."""
    kek = _get_test_kek()
    fake_runner = FakeGitCommandRunner()
    manager = MirrorManager(
        base_dir=tmp_path / "mirrors",
        runner=fake_runner,
        kek_provider=kek,
    )

    binding = _create_binding(
        remote_url="https://github.com/secret/repo.git",
        credential_bytes=b"ghp_secret_access_token_12345",
        kek_provider=kek,
    )

    await manager.clone_or_fetch(binding, pinned_ip="140.82.121.5")
    argv, _ = fake_runner.calls[0]
    include_flag = next((arg for arg in argv if "include.path=" in arg), None)
    assert include_flag is not None
    conf_path = Path(include_flag.split("include.path=")[1])
    # The temporary credential file must be deleted upon exit
    assert not conf_path.exists()  # noqa: ASYNC240


@pytest.mark.asyncio
async def test_credential_decryption_and_zeroization_ssh(tmp_path: Path) -> None:
    """SSH private deploy key is written to 0600 file and deleted upon completion."""
    kek = _get_test_kek()
    fake_runner = FakeGitCommandRunner()
    manager = MirrorManager(
        base_dir=tmp_path / "mirrors",
        runner=fake_runner,
        kek_provider=kek,
    )

    binding = _create_binding(
        remote_url="git@github.com:secret/repo.git",
        credential_bytes=(
            b"-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----"
        ),
        kek_provider=kek,
    )

    await manager.clone_or_fetch(binding, pinned_ip="140.82.121.6")
    argv, _ = fake_runner.calls[0]
    ssh_flag = next((arg for arg in argv if "core.sshCommand=" in arg), None)
    assert ssh_flag is not None
    assert "-o BatchMode=yes" in ssh_flag
    assert "-o StrictHostKeyChecking=yes" in ssh_flag


@pytest.mark.asyncio
async def test_git_execution_failure_records_error(tmp_path: Path) -> None:
    """Non-zero return code raises GitExecutionError and records error snip on binding."""
    fake_runner = FakeGitCommandRunner(
        responses=[GitResult(128, "", "fatal: repository not found\n")]
    )
    manager = MirrorManager(
        base_dir=tmp_path / "mirrors",
        runner=fake_runner,
    )

    binding = _create_binding(remote_url="https://github.com/nonexistent/repo.git")
    with pytest.raises(GitExecutionError) as exc_info:
        await manager.clone_or_fetch(binding, pinned_ip="140.82.121.7")

    assert "fatal: repository not found" in str(exc_info.value)
    assert binding.last_fetch_error is not None
    assert "GIT_EXIT_128" in binding.last_fetch_error


@pytest.mark.asyncio
async def test_git_timeout_handling(tmp_path: Path) -> None:
    """Operation exceeding timeout raises MirrorTimeoutError and records MIRROR_TIMEOUT."""
    fake_runner = FakeGitCommandRunner()
    fake_runner.raise_timeout = True
    manager = MirrorManager(
        base_dir=tmp_path / "mirrors",
        runner=fake_runner,
    )

    binding = _create_binding(remote_url="https://github.com/slow/repo.git")
    with pytest.raises(MirrorTimeoutError):
        await manager.clone_or_fetch(binding, pinned_ip="140.82.121.8")

    assert binding.last_fetch_error == "MIRROR_TIMEOUT"


@pytest.mark.asyncio
async def test_mirror_size_limit_enforcement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror exceeding size limit threshold is deleted and raises MirrorSizeLimitError."""
    fake_runner = FakeGitCommandRunner(
        responses=[
            GitResult(0, "cloned\n", ""),
        ]
    )
    manager = MirrorManager(
        base_dir=tmp_path / "mirrors",
        runner=fake_runner,
    )

    # Monkeypatch _calculate_dir_size to simulate > 2 GiB
    monkeypatch.setattr(manager, "_calculate_dir_size", lambda _p: 3 * 1024 * 1024 * 1024)

    binding = _create_binding(remote_url="https://github.com/huge/repo.git")
    mirror_dir = manager.mirror_path(binding)
    mirror_dir.mkdir(parents=True, exist_ok=True)
    (mirror_dir / "large_pack").write_bytes(b"data")

    with pytest.raises(MirrorSizeLimitError):
        await manager.clone_or_fetch(binding, pinned_ip="140.82.121.9")

    assert binding.last_fetch_error == "MIRROR_SIZE_LIMIT"
    assert not mirror_dir.exists()


def test_real_git_clone_and_fetch_with_canary_hook_defense(tmp_path: Path) -> None:
    """Real git clone & fetch works with local repo; hooks in repo are never executed."""
    # 1. Create upstream repo with git
    upstream_dir = tmp_path / "upstream"
    upstream_dir.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(upstream_dir)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(upstream_dir), "config", "user.name", "Test User"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(upstream_dir), "config", "user.email", "test@example.com"],
        check=True,
    )

    (upstream_dir / "README.md").write_text("Hello git mirror\n")
    subprocess.run(["git", "-C", str(upstream_dir), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(upstream_dir), "commit", "-m", "Initial commit"], check=True)

    canary_marker = tmp_path / "canary_pwned.txt"
    hooks_dir = upstream_dir / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    malicious_hook = hooks_dir / "post-checkout"
    malicious_hook.write_text(f"#!/bin/sh\necho PWNED > {canary_marker}\n")
    malicious_hook.chmod(0o755)

    policy = MirrorPolicy(allow_file_protocol=True)
    runner = ExecGitCommandRunner()
    manager = MirrorManager(
        base_dir=tmp_path / "mirrors",
        policy=policy,
        runner=runner,
    )

    binding = _create_binding(
        remote_url=f"file://{upstream_dir}",
        default_ref="main",
    )

    # Clone
    asyncio.run(manager.clone_or_fetch(binding))
    assert binding.last_fetch_error is None
    assert binding.last_fetched_commit is not None
    assert len(binding.last_fetched_commit) == 40
    # Canary hook was NEVER executed
    assert not canary_marker.exists()

    initial_commit = binding.last_fetched_commit

    # Add second commit upstream
    (upstream_dir / "file2.txt").write_text("Second file\n")
    subprocess.run(["git", "-C", str(upstream_dir), "add", "file2.txt"], check=True)
    subprocess.run(["git", "-C", str(upstream_dir), "commit", "-m", "Second commit"], check=True)

    # Fetch
    asyncio.run(manager.clone_or_fetch(binding))
    assert binding.last_fetch_error is None
    assert binding.last_fetched_commit is not None
    assert binding.last_fetched_commit != initial_commit
    # Canary hook still was NEVER executed
    assert not canary_marker.exists()
