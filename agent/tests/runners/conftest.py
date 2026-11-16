# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Shared pytest fixtures for agent runner tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def bare_git_fixture(tmp_path: Path) -> tuple[Path, str]:
    """Create a bare Git mirror containing secret files, code, and an escaping symlink."""
    workdir = tmp_path / "worktree"
    workdir.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=workdir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Committer"], cwd=workdir, check=True)
    subprocess.run(["git", "config", "user.email", "test@kanban.local"], cwd=workdir, check=True)

    # Populate directory structure
    (workdir / "src").mkdir()
    (workdir / "config").mkdir()
    (workdir / "tls").mkdir()
    (workdir / "certs").mkdir()

    (workdir / "src" / "app.py").write_text("print('hello world')\n", encoding="utf-8")
    (workdir / ".env").write_text("SECRET=master_key\n", encoding="utf-8")
    (workdir / "config" / ".env.local").write_text("LOCAL=test\n", encoding="utf-8")
    key_pem = "-----BEGIN RSA PRIVATE KEY-----\n"
    (workdir / "tls" / "private.key").write_text(key_pem, encoding="utf-8")
    cert_pem = "-----BEGIN CERTIFICATE-----\n"
    (workdir / "certs" / "ca.pem").write_text(cert_pem, encoding="utf-8")

    # Escaping symlink pointing to /etc/passwd
    (workdir / "escape").symlink_to(Path("/etc/passwd"))

    subprocess.run(["git", "add", "-A"], cwd=workdir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init repo with secrets and symlink"],
        cwd=workdir,
        check=True,
        capture_output=True,
    )

    bare_dir = tmp_path / "mirror.git"
    subprocess.run(
        ["git", "clone", "--bare", str(workdir), str(bare_dir)],
        check=True,
        capture_output=True,
    )

    rev_proc = subprocess.run(
        ["git", f"--git-dir={bare_dir}", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    head_commit = rev_proc.stdout.strip()
    return bare_dir, head_commit
