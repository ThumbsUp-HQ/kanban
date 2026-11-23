# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, TRY003, EM101, TC003, ARG002, D413, ANN401
"""Feature unit tests for CommitSignatureVerifier (KB-DEVSECOPS-ATTEST-01).

Covers:
- SSH commit and tag signature verification with ephemeral allowedSignersFile.
- GPG commit signature verification with isolated GNUPGHOME.
- Sigstore OIDC identity allowlist verification.
- Detection of unsigned commits, untrusted signers, and invalid signatures.
- Zero-shell subprocess execution and strict path validation.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from kanban.repos.mirror import FakeGitCommandRunner, GitResult
from kanban.repos.signature_verifier import (
    CommitSignatureVerifier,
    verify_commit_signature,
    verify_tag_signature,
)


@pytest.fixture
def ssh_git_repo_fixture(tmp_path: Path) -> tuple[Path, str, str, str, str]:
    """Create a hermetic Git repository with real Ed25519 SSH signed and unsigned commits.

    Returns:
        (repo_path, signed_commit_sha, unsigned_commit_sha, tag_name, allowed_signers_content)
    """
    key_dir = tmp_path / "ssh_keys"
    key_dir.mkdir(mode=0o700)
    key_path = key_dir / "id_ed25519"

    # Generate an unencrypted Ed25519 test key
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", "", "-C", "secops@example.com"],
        check=True,
        capture_output=True,
    )
    pub_key_content = (key_dir / "id_ed25519.pub").read_text(encoding="utf-8").strip()
    allowed_signers_content = f"secops@example.com {pub_key_content}\n"

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    def git(*args: str, env_extra: dict[str, str] | None = None) -> str:
        env = dict(os.environ)
        if env_extra:
            env.update(env_extra)
        res = subprocess.run(
            ["git", *args],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return res.stdout.strip()

    git("init")
    git("config", "user.name", "Security Architect")
    git("config", "user.email", "secops@example.com")
    git("config", "gpg.format", "ssh")
    git("config", "user.signingkey", str(key_path))

    # Commit 1: Signed commit
    (repo_dir / "README.md").write_text("# Signed Project\n", encoding="utf-8")
    git("add", "README.md")
    git("commit", "-S", "-m", "feat: signed initial commit")
    signed_sha = git("rev-parse", "HEAD")

    # Create signed tag
    git("tag", "-s", "-m", "v1.0.0-signed", "v1.0.0")

    # Commit 2: Unsigned commit
    (repo_dir / "docs.txt").write_text("Unsigned docs\n", encoding="utf-8")
    git("add", "docs.txt")
    git("commit", "--no-gpg-sign", "-m", "docs: unsigned commit")
    unsigned_sha = git("rev-parse", "HEAD")

    return repo_dir, signed_sha, unsigned_sha, "v1.0.0", allowed_signers_content


@pytest.mark.asyncio
async def test_ssh_commit_signature_verified(
    ssh_git_repo_fixture: tuple[Path, str, str, str, str],
) -> None:
    """Commit signed with valid SSH key in ssh_allowed_signers verifies successfully."""
    repo_dir, signed_sha, _, _, allowed_signers = ssh_git_repo_fixture
    verifier = CommitSignatureVerifier()

    res = await verifier.verify_commit(
        repo_path=repo_dir,
        commit_sha=signed_sha,
        ssh_allowed_signers=allowed_signers,
    )

    assert res.verified is True
    assert res.sig_scheme == "ssh"
    assert res.signer_identity == "secops@example.com"
    assert res.key_fingerprint.startswith("SHA256:")
    assert res.commit_sha == signed_sha
    assert res.error_code is None


@pytest.mark.asyncio
async def test_ssh_tag_signature_verified(
    ssh_git_repo_fixture: tuple[Path, str, str, str, str],
) -> None:
    """Annotated tag signed with SSH key verifies via verify_tag."""
    repo_dir, _, _, tag_name, allowed_signers = ssh_git_repo_fixture

    res = await verify_tag_signature(
        repo_path=repo_dir,
        tag_name=tag_name,
        ssh_allowed_signers=allowed_signers,
    )

    assert res.verified is True
    assert res.sig_scheme == "ssh"
    assert res.signer_identity == "secops@example.com"


@pytest.mark.asyncio
async def test_ssh_signature_untrusted_signer(
    ssh_git_repo_fixture: tuple[Path, str, str, str, str],
) -> None:
    """Commit signed with key not present in allowed_signers fails UNTRUSTED_SIGNER."""
    repo_dir, signed_sha, _, _, _ = ssh_git_repo_fixture
    verifier = CommitSignatureVerifier()

    # Pass different key as allowed signers
    foreign_allowed = "other@example.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI0000000000000000000000000000000000000000000 other\n"
    res = await verifier.verify_commit(
        repo_path=repo_dir,
        commit_sha=signed_sha,
        ssh_allowed_signers=foreign_allowed,
    )

    assert res.verified is False
    assert res.sig_scheme == "ssh"
    assert res.error_code == "UNTRUSTED_SIGNER"


@pytest.mark.asyncio
async def test_unsigned_commit_rejected(
    ssh_git_repo_fixture: tuple[Path, str, str, str, str],
) -> None:
    """Unsigned commit fails closed with SIGNATURE_NOT_FOUND."""
    repo_dir, _, unsigned_sha, _, allowed_signers = ssh_git_repo_fixture

    res = await verify_commit_signature(
        repo_path=repo_dir,
        commit_sha=unsigned_sha,
        ssh_allowed_signers=allowed_signers,
    )

    assert res.verified is False
    assert res.sig_scheme == "none"
    assert res.error_code == "SIGNATURE_NOT_FOUND"
    assert "No cryptographic signature found" in str(res.error_detail)


@pytest.mark.asyncio
async def test_path_and_sha_syntax_boundaries(tmp_path: Path) -> None:
    """Invalid repository path, commit SHA syntax, or missing commit fail cleanly."""
    verifier = CommitSignatureVerifier()

    # 1. Non-existent repo directory
    res_repo = await verifier.verify_commit(tmp_path / "nonexistent", "a" * 40)
    assert res_repo.verified is False
    assert res_repo.error_code == "REPO_PATH_INVALID"

    # 2. Malformed SHA syntax
    existing = tmp_path / "exist"
    existing.mkdir()
    res_sha = await verifier.verify_commit(existing, "invalid_sha_123")
    assert res_sha.verified is False
    assert res_sha.error_code == "COMMIT_SHA_INVALID"

    # 3. Missing tag
    fake_runner = FakeGitCommandRunner(
        responses=[GitResult(returncode=1, stdout="", stderr="fatal: Not a valid object name")]
    )
    v_tag = CommitSignatureVerifier(runner=fake_runner)
    res_tag = await v_tag.verify_tag(existing, "v999.0.0")
    assert res_tag.verified is False
    assert res_tag.error_code == "TAG_NOT_FOUND"


@pytest.mark.asyncio
async def test_gpg_signature_verification_flows(tmp_path: Path) -> None:
    """GPG verify flow handles GOODSIG/VALIDSIG and bad signatures via fake runner."""
    repo_dir = tmp_path / "gpg_repo"
    repo_dir.mkdir()

    # 1. Successful GPG verification
    gpg_cat_out = "tree 1111\ngpgsig -----BEGIN PGP SIGNATURE-----\nVersion: GnuPG\n...\n-----END PGP SIGNATURE-----\n"
    gpg_raw_good = (
        "[GNUPG:] GOODSIG 1234567890ABCDEF Core Lead <lead@example.com>\n"
        "[GNUPG:] VALIDSIG 99887766554433221100FFEEDDCCBBAA 2026-11-22 ...\n"
    )
    runner_good = FakeGitCommandRunner(
        responses=[
            GitResult(returncode=0, stdout=gpg_cat_out, stderr=""),
            GitResult(returncode=0, stdout=gpg_raw_good, stderr=""),
        ]
    )
    v_gpg = CommitSignatureVerifier(runner=runner_good)
    res_good = await v_gpg.verify_commit(
        repo_path=repo_dir,
        commit_sha="b" * 40,
        gpg_trusted_armored_keys="-----BEGIN PGP PUBLIC KEY BLOCK-----\nkeydata\n-----END PGP PUBLIC KEY BLOCK-----\n",
    )
    assert res_good.verified is True
    assert res_good.sig_scheme == "gpg"
    assert res_good.signer_identity == "Core Lead <lead@example.com>"
    assert res_good.key_fingerprint == "99887766554433221100FFEEDDCCBBAA"

    # 2. Missing armored keys
    runner_no_keys = FakeGitCommandRunner(
        responses=[
            GitResult(returncode=0, stdout=gpg_cat_out, stderr=""),
        ]
    )
    v_no_keys = CommitSignatureVerifier(runner=runner_no_keys)
    res_no_keys = await v_no_keys.verify_commit(
        repo_path=repo_dir,
        commit_sha="b" * 40,
        gpg_trusted_armored_keys=None,
    )
    assert res_no_keys.verified is False
    assert res_no_keys.error_code == "UNTRUSTED_SIGNER"

    # 3. BADSIG corrupted signature
    gpg_raw_bad = "[GNUPG:] BADSIG 1234567890ABCDEF Core Lead <lead@example.com>\n"
    runner_bad = FakeGitCommandRunner(
        responses=[
            GitResult(returncode=0, stdout=gpg_cat_out, stderr=""),
            GitResult(returncode=1, stdout=gpg_raw_bad, stderr="bad signature"),
        ]
    )
    v_bad = CommitSignatureVerifier(runner=runner_bad)
    res_bad = await v_bad.verify_commit(
        repo_path=repo_dir,
        commit_sha="b" * 40,
        gpg_trusted_armored_keys="-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----\n",
    )
    assert res_bad.verified is False
    assert res_bad.error_code == "SIGNATURE_INVALID"


@pytest.mark.asyncio
async def test_sigstore_oidc_identity_verification(tmp_path: Path) -> None:
    """Sigstore verification matches OIDC issuer and subject claims in commit header."""
    repo_dir = tmp_path / "sigstore_repo"
    repo_dir.mkdir()

    commit_payload = (
        "tree 2222\n"
        "gpgsig -----BEGIN SIGSTORE BUNDLE-----\n"
        "issuer: https://token.actions.githubusercontent.com\n"
        "subject: https://github.com/example/kanban/.github/workflows/ci.yml@refs/heads/main\n"
        "-----END SIGSTORE BUNDLE-----\n"
    )

    trusted = [
        {
            "issuer": "https://token.actions.githubusercontent.com",
            "subject": "https://github.com/example/kanban/.github/workflows/ci.yml@refs/heads/main",
        }
    ]

    # 1. Matching identity
    runner_match = FakeGitCommandRunner(
        responses=[GitResult(returncode=0, stdout=commit_payload, stderr="")]
    )
    v_match = CommitSignatureVerifier(runner=runner_match)
    res_match = await v_match.verify_commit(
        repo_path=repo_dir,
        commit_sha="c" * 40,
        sigstore_trusted_identities=trusted,
    )
    assert res_match.verified is True
    assert res_match.sig_scheme == "sigstore"
    assert "github.com/example/kanban" in res_match.signer_identity

    # 2. Untrusted identity
    untrusted = [{"issuer": "https://token.actions.githubusercontent.com", "subject": "malicious"}]
    runner_untrusted = FakeGitCommandRunner(
        responses=[GitResult(returncode=0, stdout=commit_payload, stderr="")]
    )
    v_untrusted = CommitSignatureVerifier(runner=runner_untrusted)
    res_untrusted = await v_untrusted.verify_commit(
        repo_path=repo_dir,
        commit_sha="c" * 40,
        sigstore_trusted_identities=untrusted,
    )
    assert res_untrusted.verified is False
    assert res_untrusted.error_code == "UNTRUSTED_SIGNER"


@pytest.mark.asyncio
async def test_signature_verifier_boundary_error_branches(tmp_path: Path) -> None:
    """Verifier handles runner exceptions, missing commits, and unsupported signature schemes."""
    repo_dir = tmp_path / "boundary_repo"
    repo_dir.mkdir()

    # 1. Commit cat-file failure -> COMMIT_NOT_FOUND
    runner_not_found = FakeGitCommandRunner(
        responses=[GitResult(returncode=1, stdout="", stderr="fatal: Not a valid object name")]
    )
    v_nf = CommitSignatureVerifier(runner=runner_not_found)
    res_nf = await v_nf.verify_commit(repo_dir, "d" * 40)
    assert res_nf.verified is False
    assert res_nf.error_code == "COMMIT_NOT_FOUND"

    # 2. Runner exception -> EXECUTION_ERROR
    class RaisingRunner:
        async def run(self, *args: Any, **kw: Any) -> GitResult:
            raise OSError("Subprocess spawn error")

    v_err = CommitSignatureVerifier(runner=RaisingRunner())
    res_err = await v_err.verify_commit(repo_dir, "d" * 40)
    assert res_err.verified is False
    assert res_err.error_code == "EXECUTION_ERROR"

    # 3. gpgsig present but no matching truststore keys -> UNSUPPORTED_SIGNATURE_SCHEME
    runner_unsupported = FakeGitCommandRunner(
        responses=[GitResult(returncode=0, stdout="tree 1111\ngpgsig some_custom_sig\n", stderr="")]
    )
    v_unsupp = CommitSignatureVerifier(runner=runner_unsupported)
    res_unsupp = await v_unsupp.verify_commit(repo_dir, "d" * 40)
    assert res_unsupp.verified is False
    assert res_unsupp.error_code == "UNSUPPORTED_SIGNATURE_SCHEME"

    # 4. Unsigned annotated tag object -> SIGNATURE_NOT_FOUND
    runner_unsigned_tag = FakeGitCommandRunner(
        responses=[
            GitResult(returncode=0, stdout="e" * 40 + "\n", stderr=""),  # rev-parse
            GitResult(
                returncode=0, stdout="object 111\ntype commit\ntag v1.0\n", stderr=""
            ),  # cat-file
        ]
    )
    v_tag_unsig = CommitSignatureVerifier(runner=runner_unsigned_tag)
    res_tag_unsig = await v_tag_unsig.verify_tag(repo_dir, "v1.0")
    assert res_tag_unsig.verified is False
    assert res_tag_unsig.error_code == "SIGNATURE_NOT_FOUND"

    # 5. GPG signed tag object -> verified via verify_tag
    gpg_tag_cat = (
        "object 111\ntype commit\ntag v2.0\n-----BEGIN PGP SIGNATURE-----\nVersion: GnuPG\n"
    )
    gpg_raw_good = (
        "[GNUPG:] GOODSIG 1234567890ABCDEF Release Bot <bot@example.com>\n"
        "[GNUPG:] VALIDSIG 99887766554433221100FFEEDDCCBBAA 2026-11-22 ...\n"
    )
    runner_gpg_tag = FakeGitCommandRunner(
        responses=[
            GitResult(returncode=0, stdout="f" * 40 + "\n", stderr=""),  # rev-parse
            GitResult(returncode=0, stdout=gpg_tag_cat, stderr=""),  # cat-file
            GitResult(returncode=0, stdout=gpg_raw_good, stderr=""),  # verify-tag
        ]
    )
    v_gpg_tag = CommitSignatureVerifier(runner=runner_gpg_tag)
    res_gpg_tag = await v_gpg_tag.verify_tag(
        repo_dir,
        "v2.0",
        gpg_trusted_armored_keys="-----BEGIN PGP PUBLIC KEY BLOCK-----\nkey\n-----END PGP PUBLIC KEY BLOCK-----\n",
    )
    assert res_gpg_tag.verified is True
    assert res_gpg_tag.sig_scheme == "gpg"

    # 6. SSH verification with "no signature found" stderr
    cat_ssh = "tree 1111\nBEGIN SSH SIGNATURE\n"
    runner_no_ssh = FakeGitCommandRunner(
        responses=[
            GitResult(returncode=0, stdout=cat_ssh, stderr=""),
            GitResult(returncode=1, stdout="", stderr="error: no signature found"),
        ]
    )
    v_no_ssh = CommitSignatureVerifier(runner=runner_no_ssh)
    res_no_ssh = await v_no_ssh.verify_commit(
        repo_dir,
        "d" * 40,
        ssh_allowed_signers="sec@example.com ssh-ed25519 AAAAC3 dummy sec@example.com\n",
    )
    assert res_no_ssh.verified is False
    assert res_no_ssh.error_code == "SIGNATURE_NOT_FOUND"
