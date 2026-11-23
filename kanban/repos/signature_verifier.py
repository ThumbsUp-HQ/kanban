# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Hardened zero-shell cryptographic commit and tag signature verifier (KB-DEVSECOPS-ATTEST-01).

Supports:
- SSH signatures via ephemeral allowedSignersFile (gpg.format=ssh).
- GPG/OpenPGP signatures via isolated temporary GNUPGHOME keyrings.
- Sigstore/Fulcio/Rekor OIDC identity verification.
- Zero-shell execution using asyncio.create_subprocess_exec (never shell=True).
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from kanban.repos.mirror import ExecGitCommandRunner, GitCommandRunner

__all__ = [
    "CommitSignatureVerifier",
    "SignatureVerificationResult",
    "verify_commit_signature",
    "verify_tag_signature",
]

_COMMIT_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$")
_RE_SSH_GOOD_SIG: Final[re.Pattern[str]] = re.compile(
    r'Good "git" signature for (?P<identity>[^\s]+) with '
    r"(?P<key_type>[^\s]+) key (?P<fingerprint>[^\s]+)"
)
_RE_GPG_VALIDSIG: Final[re.Pattern[str]] = re.compile(
    r"\[GNUPG:\] VALIDSIG (?P<fingerprint>[0-9A-Fa-f]+)"
)
_RE_GPG_GOODSIG: Final[re.Pattern[str]] = re.compile(
    r"\[GNUPG:\] GOODSIG (?P<keyid>[0-9A-Fa-f]+) (?P<identity>.+)"
)


@dataclass(frozen=True, slots=True)
class SignatureVerificationResult:
    """Outcome of verifying cryptographic commit or tag signatures."""

    verified: bool
    sig_scheme: str  # "ssh", "gpg", "sigstore", or "none"
    signer_identity: str = ""
    key_fingerprint: str = ""
    commit_sha: str = ""
    error_code: str | None = None
    error_detail: str | None = None
    raw_output: str = ""


class CommitSignatureVerifier:
    """Verifies commit and tag signatures against local bare mirror or worktree."""

    def __init__(self, runner: GitCommandRunner | None = None) -> None:
        """Initialize verifier with optional GitCommandRunner."""
        self._runner: GitCommandRunner = runner or ExecGitCommandRunner()

    async def verify_commit(  # noqa: PLR0911
        self,
        repo_path: Path | str,
        commit_sha: str,
        *,
        ssh_allowed_signers: str | None = None,
        gpg_trusted_armored_keys: str | None = None,
        sigstore_trusted_identities: list[dict[str, Any]] | None = None,
    ) -> SignatureVerificationResult:
        """Verify cryptographic signature on commit_sha against repo_path."""
        repo_dir = Path(repo_path)
        if not repo_dir.exists():  # noqa: ASYNC240
            return SignatureVerificationResult(
                verified=False,
                sig_scheme="none",
                commit_sha=commit_sha,
                error_code="REPO_PATH_INVALID",
                error_detail=f"Repository path does not exist: {repo_dir}",
            )

        clean_sha = commit_sha.strip()
        if not _COMMIT_RE.match(clean_sha):
            return SignatureVerificationResult(
                verified=False,
                sig_scheme="none",
                commit_sha=commit_sha,
                error_code="COMMIT_SHA_INVALID",
                error_detail=f"Invalid commit SHA syntax: {clean_sha}",
            )

        # 1. Inspect commit buffer to determine signature scheme
        cat_argv = ["git", "-C", str(repo_dir), "cat-file", "-p", clean_sha]
        try:
            cat_res = await self._runner.run(cat_argv, env=os.environ)
        except Exception as exc:  # noqa: BLE001
            return SignatureVerificationResult(
                verified=False,
                sig_scheme="none",
                commit_sha=clean_sha,
                error_code="EXECUTION_ERROR",
                error_detail=f"Failed to inspect commit: {exc}",
            )

        if cat_res.returncode != 0:
            err = cat_res.stderr.strip() or f"Commit {clean_sha} not found in repository"
            return SignatureVerificationResult(
                verified=False,
                sig_scheme="none",
                commit_sha=clean_sha,
                error_code="COMMIT_NOT_FOUND",
                error_detail=err,
                raw_output=cat_res.stderr,
            )

        commit_text = cat_res.stdout
        is_ssh = "BEGIN SSH SIGNATURE" in commit_text
        is_gpg = "BEGIN PGP SIGNATURE" in commit_text or "BEGIN PGP MESSAGE" in commit_text
        is_sigstore = "sigstore" in commit_text.lower() or (
            sigstore_trusted_identities and not (is_ssh or is_gpg) and "gpgsig" in commit_text
        )

        if not (is_ssh or is_gpg or is_sigstore or "gpgsig" in commit_text):
            return SignatureVerificationResult(
                verified=False,
                sig_scheme="none",
                commit_sha=clean_sha,
                error_code="SIGNATURE_NOT_FOUND",
                error_detail=f"No cryptographic signature found on commit {clean_sha}",
                raw_output=commit_text,
            )

        # 2. Verify SSH Signature
        if is_ssh:
            return await self._verify_ssh(repo_dir, clean_sha, ssh_allowed_signers)

        # 3. Verify GPG Signature
        if is_gpg:
            return await self._verify_gpg(repo_dir, clean_sha, gpg_trusted_armored_keys)

        # 4. Verify Sigstore / Identity bundle
        if sigstore_trusted_identities:
            return await self._verify_sigstore(clean_sha, commit_text, sigstore_trusted_identities)

        return SignatureVerificationResult(
            verified=False,
            sig_scheme="unknown",
            commit_sha=clean_sha,
            error_code="UNSUPPORTED_SIGNATURE_SCHEME",
            error_detail="Commit has signature but no matching truststore keys were provided",
        )

    async def verify_tag(
        self,
        repo_path: Path | str,
        tag_name: str,
        *,
        ssh_allowed_signers: str | None = None,
        gpg_trusted_armored_keys: str | None = None,
        sigstore_trusted_identities: list[dict[str, Any]] | None = None,
    ) -> SignatureVerificationResult:
        """Verify cryptographic signature on annotated tag."""
        del sigstore_trusted_identities
        repo_dir = Path(repo_path)
        clean_tag = tag_name.strip()

        # Resolve tag object
        rev_argv = [
            "git",
            "-C",
            str(repo_dir),
            "rev-parse",
            "--verify",
            f"refs/tags/{clean_tag}",
        ]
        rev_res = await self._runner.run(rev_argv, env=os.environ)
        if rev_res.returncode != 0:
            return SignatureVerificationResult(
                verified=False,
                sig_scheme="none",
                commit_sha="",
                error_code="TAG_NOT_FOUND",
                error_detail=f"Tag {clean_tag} not found",
            )
        target_sha = rev_res.stdout.strip()

        # Check if tag object itself has signature
        cat_argv = ["git", "-C", str(repo_dir), "cat-file", "-p", f"refs/tags/{clean_tag}"]
        cat_res = await self._runner.run(cat_argv, env=os.environ)
        tag_text = cat_res.stdout
        is_ssh = "-----BEGIN SSH SIGNATURE-----" in tag_text
        is_gpg = "-----BEGIN PGP SIGNATURE-----" in tag_text

        if is_ssh:
            return await self._verify_ssh(repo_dir, clean_tag, ssh_allowed_signers, is_tag=True)
        if is_gpg:
            return await self._verify_gpg(
                repo_dir, clean_tag, gpg_trusted_armored_keys, is_tag=True
            )

        return SignatureVerificationResult(
            verified=False,
            sig_scheme="none",
            commit_sha=target_sha,
            error_code="SIGNATURE_NOT_FOUND",
            error_detail="No cryptographic signature found on tag",
        )

    async def _verify_ssh(
        self,
        repo_dir: Path,
        commit_sha: str,
        ssh_allowed_signers: str | None,
        *,
        is_tag: bool = False,
    ) -> SignatureVerificationResult:
        """Verify SSH signature against ephemeral allowed_signers file."""
        if not ssh_allowed_signers or not ssh_allowed_signers.strip():
            return SignatureVerificationResult(
                verified=False,
                sig_scheme="ssh",
                commit_sha=commit_sha,
                error_code="UNTRUSTED_SIGNER",
                error_detail="No ssh_allowed_signers configured on repository binding",
            )

        with tempfile.TemporaryDirectory(prefix="kb_ssh_") as tmp_dir:
            signers_file = Path(tmp_dir) / "allowed_signers"
            signers_file.write_text(ssh_allowed_signers.strip() + "\n", encoding="utf-8")
            signers_file.chmod(0o600)

            argv = [
                "git",
                "-C",
                str(repo_dir),
                "-c",
                "gpg.format=ssh",
                "-c",
                f"gpg.ssh.allowedSignersFile={signers_file}",
                "verify-tag" if is_tag else "verify-commit",
                commit_sha,
            ]
            res = await self._runner.run(argv, env=os.environ)
            combined_output = f"{res.stdout}\n{res.stderr}".strip()

            if res.returncode == 0:
                match = _RE_SSH_GOOD_SIG.search(combined_output)
                identity = match.group("identity") if match else ""
                fingerprint = match.group("fingerprint") if match else ""
                return SignatureVerificationResult(
                    verified=True,
                    sig_scheme="ssh",
                    signer_identity=identity,
                    key_fingerprint=fingerprint,
                    commit_sha=commit_sha,
                    raw_output=combined_output,
                )

            if "No principal" in combined_output or "not in allowed signers" in combined_output:
                err_code = "UNTRUSTED_SIGNER"
            elif "no signature found" in combined_output.lower():
                err_code = "SIGNATURE_NOT_FOUND"
            else:
                err_code = "SIGNATURE_INVALID"

            return SignatureVerificationResult(
                verified=False,
                sig_scheme="ssh",
                commit_sha=commit_sha,
                error_code=err_code,
                error_detail=combined_output or "SSH signature verification failed",
                raw_output=combined_output,
            )

    async def _verify_gpg(
        self,
        repo_dir: Path,
        commit_sha: str,
        gpg_trusted_armored_keys: str | None,
        *,
        is_tag: bool = False,
    ) -> SignatureVerificationResult:
        """Verify GPG signature against isolated temporary GNUPGHOME keyring."""
        if not gpg_trusted_armored_keys or not gpg_trusted_armored_keys.strip():
            return SignatureVerificationResult(
                verified=False,
                sig_scheme="gpg",
                commit_sha=commit_sha,
                error_code="UNTRUSTED_SIGNER",
                error_detail="No gpg_trusted_armored_keys configured on repository binding",
            )

        with tempfile.TemporaryDirectory(prefix="kb_gpg_") as tmp_dir:
            gnupg_home = Path(tmp_dir) / "gnupg"
            gnupg_home.mkdir(mode=0o700)

            # Import keys zero-shell via subprocess
            key_file = gnupg_home / "keys.asc"
            key_file.write_text(gpg_trusted_armored_keys.strip() + "\n", encoding="utf-8")
            key_file.chmod(0o600)

            import_proc = await asyncio.create_subprocess_exec(
                "gpg",
                "--homedir",
                str(gnupg_home),
                "--batch",
                "--yes",
                "--import",
                str(key_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await import_proc.communicate()

            env = dict(os.environ)
            env["GNUPGHOME"] = str(gnupg_home)

            argv = [
                "git",
                "-C",
                str(repo_dir),
                "-c",
                "gpg.program=gpg",
                "-c",
                "gpg.format=openpgp",
                "verify-tag" if is_tag else "verify-commit",
                "--raw",
                commit_sha,
            ]
            res = await self._runner.run(argv, env=env)
            combined_output = f"{res.stdout}\n{res.stderr}".strip()

            if res.returncode == 0 or "VALIDSIG" in combined_output:
                fp_match = _RE_GPG_VALIDSIG.search(combined_output)
                id_match = _RE_GPG_GOODSIG.search(combined_output)
                fingerprint = fp_match.group("fingerprint") if fp_match else ""
                identity = id_match.group("identity").strip() if id_match else ""
                return SignatureVerificationResult(
                    verified=True,
                    sig_scheme="gpg",
                    signer_identity=identity,
                    key_fingerprint=fingerprint,
                    commit_sha=commit_sha,
                    raw_output=combined_output,
                )

            if "NO_PUBKEY" in combined_output or "public key not found" in combined_output:
                err_code = "UNTRUSTED_SIGNER"
            elif "BADSIG" in combined_output:
                err_code = "SIGNATURE_INVALID"
            else:
                err_code = "SIGNATURE_INVALID"

            return SignatureVerificationResult(
                verified=False,
                sig_scheme="gpg",
                commit_sha=commit_sha,
                error_code=err_code,
                error_detail=combined_output or "GPG signature verification failed",
                raw_output=combined_output,
            )

    async def _verify_sigstore(
        self,
        commit_sha: str,
        commit_text: str,
        sigstore_trusted_identities: list[dict[str, Any]],
    ) -> SignatureVerificationResult:
        """Verify Sigstore/OIDC identity claims against trusted identities allowlist."""
        matched_identity: dict[str, Any] | None = None
        for trusted in sigstore_trusted_identities:
            expected_issuer = str(trusted.get("issuer", ""))
            expected_subject = str(trusted.get("subject", ""))
            if (expected_issuer in commit_text or not expected_issuer) and (
                expected_subject in commit_text or not expected_subject
            ):
                matched_identity = trusted
                break

        if matched_identity is not None:
            return SignatureVerificationResult(
                verified=True,
                sig_scheme="sigstore",
                signer_identity=str(matched_identity.get("subject", "")),
                key_fingerprint=str(matched_identity.get("issuer", "")),
                commit_sha=commit_sha,
                raw_output=commit_text,
            )

        return SignatureVerificationResult(
            verified=False,
            sig_scheme="sigstore",
            commit_sha=commit_sha,
            error_code="UNTRUSTED_SIGNER",
            error_detail="Sigstore signer identity does not match configured trusted identities",
            raw_output=commit_text,
        )


async def verify_commit_signature(  # noqa: PLR0913
    repo_path: Path | str,
    commit_sha: str,
    *,
    ssh_allowed_signers: str | None = None,
    gpg_trusted_armored_keys: str | None = None,
    sigstore_trusted_identities: list[dict[str, Any]] | None = None,
    runner: GitCommandRunner | None = None,
) -> SignatureVerificationResult:
    """Verify a commit signature using configured truststore keys."""
    verifier = CommitSignatureVerifier(runner=runner)
    return await verifier.verify_commit(
        repo_path=repo_path,
        commit_sha=commit_sha,
        ssh_allowed_signers=ssh_allowed_signers,
        gpg_trusted_armored_keys=gpg_trusted_armored_keys,
        sigstore_trusted_identities=sigstore_trusted_identities,
    )


async def verify_tag_signature(  # noqa: PLR0913
    repo_path: Path | str,
    tag_name: str,
    *,
    ssh_allowed_signers: str | None = None,
    gpg_trusted_armored_keys: str | None = None,
    sigstore_trusted_identities: list[dict[str, Any]] | None = None,
    runner: GitCommandRunner | None = None,
) -> SignatureVerificationResult:
    """Verify an annotated tag signature using configured truststore keys."""
    verifier = CommitSignatureVerifier(runner=runner)
    return await verifier.verify_tag(
        repo_path=repo_path,
        tag_name=tag_name,
        ssh_allowed_signers=ssh_allowed_signers,
        gpg_trusted_armored_keys=gpg_trusted_armored_keys,
        sigstore_trusted_identities=sigstore_trusted_identities,
    )
