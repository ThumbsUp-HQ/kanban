# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, TC003
"""Feature unit tests for Git commit signature status in repo_git_log (KB-DEVSECOPS-ATTEST-01, KAN-76)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agent.tools.repo_tools import BareGitRepoToolkit


@pytest.fixture
def signed_and_unsigned_bare_repo(tmp_path: Path) -> tuple[Path, str, str, Path]:
    """Create a bare Git repo containing an unsigned commit and an SSH-signed commit.

    Returns:
        (bare_mirror_path, unsigned_sha, signed_sha, allowed_signers_file)

    """
    work = tmp_path / "work"
    work.mkdir()

    # Generate Ed25519 SSH keypair
    key_path = tmp_path / "id_ed25519"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key_path), "-C", "signer@example.com"],
        check=True,
        capture_output=True,
        text=True,
    )
    pub_key = (tmp_path / "id_ed25519.pub").read_text(encoding="utf-8").strip()

    allowed_signers = tmp_path / "allowed_signers"
    allowed_signers.write_text(f"signer@example.com {pub_key}\n", encoding="utf-8")

    def run_git(*args: str) -> str:
        res = subprocess.run(
            ["git", *args],
            cwd=work,
            check=True,
            capture_output=True,
            text=True,
        )
        return str(res.stdout).strip()

    run_git("init")
    run_git("config", "user.name", "Test Committer")
    run_git("config", "user.email", "signer@example.com")
    run_git("config", "commit.gpgsign", "false")

    # 1. Unsigned commit
    file1 = work / "file1.txt"
    file1.write_text("unsigned content\n", encoding="utf-8")
    run_git("add", "file1.txt")
    run_git("commit", "-m", "Unsigned commit 1")
    unsigned_sha = run_git("rev-parse", "HEAD")

    # 2. Signed commit using SSH
    run_git("config", "gpg.format", "ssh")
    run_git("config", "user.signingkey", str(key_path))
    run_git("config", "gpg.ssh.allowedSignersFile", str(allowed_signers))
    run_git("config", "commit.gpgsign", "true")

    file2 = work / "file2.txt"
    file2.write_text("signed content\n", encoding="utf-8")
    run_git("add", "file2.txt")
    run_git("commit", "-m", "Signed commit 2")
    signed_sha = run_git("rev-parse", "HEAD")

    # Clone bare mirror
    bare_path = tmp_path / "repo.git"
    subprocess.run(
        ["git", "clone", "--bare", str(work), str(bare_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    # Configure bare mirror truststore for git verify-commit / git log %G?
    subprocess.run(
        ["git", "-C", str(bare_path), "config", "gpg.format", "ssh"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(bare_path),
            "config",
            "gpg.ssh.allowedSignersFile",
            str(allowed_signers),
        ],
        check=True,
        capture_output=True,
    )

    return bare_path, unsigned_sha, signed_sha, allowed_signers


@pytest.mark.asyncio
async def test_repo_git_log_includes_signature_metadata(
    signed_and_unsigned_bare_repo: tuple[Path, str, str, Path],
) -> None:
    """BareGitRepoToolkit.repo_git_log returns signature status (%G?), signer (%GS), and key (%GK)."""
    bare_path, unsigned_sha, signed_sha, _ = signed_and_unsigned_bare_repo

    toolkit = BareGitRepoToolkit(mirror_path=bare_path, head_commit=signed_sha)

    log_output = await toolkit.repo_git_log(max_commits=5)
    lines = [ln for ln in log_output.strip().splitlines() if ln]
    assert len(lines) == 2

    # Line 1: Signed commit (signed_sha)
    parts_signed = lines[0].split("\t")
    assert len(parts_signed) >= 5
    assert parts_signed[0] == signed_sha
    assert parts_signed[3] == "Signed commit 2"
    # %G? signature status: 'G' for good valid signature
    assert parts_signed[4] == "G"

    # Line 2: Unsigned commit (unsigned_sha)
    parts_unsigned = lines[1].split("\t")
    assert len(parts_unsigned) >= 5
    assert parts_unsigned[0] == unsigned_sha
    assert parts_unsigned[3] == "Unsigned commit 1"
    # %G? signature status: 'N' for no signature
    assert parts_unsigned[4] == "N"


@pytest.mark.asyncio
async def test_repo_git_log_with_path_filter_and_signatures(
    signed_and_unsigned_bare_repo: tuple[Path, str, str, Path],
) -> None:
    """Filtering repo_git_log by path retains signature metadata on matching commits."""
    bare_path, _, signed_sha, _ = signed_and_unsigned_bare_repo

    toolkit = BareGitRepoToolkit(mirror_path=bare_path, head_commit=signed_sha)

    # Filter by file2.txt (only present in signed commit)
    log_output = await toolkit.repo_git_log(path="file2.txt", max_commits=5)
    lines = [ln for ln in log_output.strip().splitlines() if ln]
    assert len(lines) == 1
    parts = lines[0].split("\t")
    assert parts[0] == signed_sha
    assert parts[4] == "G"
