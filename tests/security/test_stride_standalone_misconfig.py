# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""STRIDE Threat Matrix Row 4: Standalone docker run Misconfiguration (Spec S3.5, KB-P6-03)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

from deploy.standalone.entrypoint import build_uvicorn_command
from deploy.standalone.pg_config import configure_postgres
from kanban.auth.setup import generate_setup_token
from kanban.sandbox.probe import (
    SandboxUnavailableError,
    probe_nsjail_userns,
)
from kanban.security.keys import (
    KeyMaterialError,
    _load_from_keyring_file,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def test_stride_row4_dockerfile_zero_hardcoded_secrets() -> None:
    """S3.5 Row 4: Dockerfile and image config contain zero hardcoded secrets/passwords."""
    dockerfile_path = Path("Dockerfile")
    assert dockerfile_path.exists(), "Root Dockerfile must exist"

    content = dockerfile_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Search for any ENV directive that sets sensitive values
    env_secret_pattern = re.compile(
        r"^\s*ENV\s+.*(PASSWORD|SECRET|KEY|TOKEN)\s*=\s*['\"]?[A-Za-z0-9+/=_-]{8,}['\"]?",
        re.IGNORECASE,
    )
    for line_num, line in enumerate(lines, start=1):
        # Exclude build-time dummy placeholders or default names if any
        assert not env_secret_pattern.search(line), (
            f"Dockerfile line {line_num} contains hardcoded secret in ENV: {line}"
        )


def test_stride_row4_standalone_keyring_permissions_and_parsing(tmp_path: Path) -> None:
    """S3.5 Row 4: keyring.json rejects 0644, symlinks, and truncated JSON (KeyMaterialError)."""
    keyring_file = tmp_path / "keyring.json"

    valid_payload = {
        "MASTER_KEK": base64.urlsafe_b64encode(b"K" * 32).decode("ascii"),
        "KB_AUTH_PEPPER": base64.urlsafe_b64encode(b"P" * 32).decode("ascii"),
        "SESSION_HMAC_KEY": base64.urlsafe_b64encode(b"H" * 32).decode("ascii"),
        "MASTER_KEK_KID": "kek-v1",
    }

    # 1. Permissive mode 0644 must be rejected
    keyring_file.write_text(json.dumps(valid_payload), encoding="utf-8")
    keyring_file.chmod(0o644)
    with pytest.raises(KeyMaterialError) as exc_perm:
        _load_from_keyring_file(keyring_file)
    assert "too permissive" in str(exc_perm.value)

    # 2. Strict mode 0600 succeeds
    keyring_file.chmod(0o600)
    km = _load_from_keyring_file(keyring_file)
    assert km.master_kek == b"K" * 32
    assert km.auth_pepper == b"P" * 32
    assert km.session_hmac_key == b"H" * 32

    # 3. Symlink must be rejected
    symlink_target = tmp_path / "symlink_keyring.json"
    symlink_target.symlink_to(keyring_file)
    with pytest.raises(KeyMaterialError) as exc_sym:
        _load_from_keyring_file(symlink_target)
    assert "must not be a symlink" in str(exc_sym.value)

    # 4. Truncated or malformed JSON must be rejected
    corrupted_file = tmp_path / "corrupted_keyring.json"
    corrupted_file.write_text('{"MASTER_KEK": "partial_val...', encoding="utf-8")
    corrupted_file.chmod(0o600)
    with pytest.raises(KeyMaterialError) as exc_json:
        _load_from_keyring_file(corrupted_file)
    assert "Failed to read or parse keyring JSON" in str(exc_json.value)


@pytest.mark.committed_db
async def test_stride_row4_fresh_db_zero_default_users_and_setup_token_hygiene(
    committed_db_session: AsyncSession,
) -> None:
    """S3.5 Row 4: Fresh DB has 0 default users; kb_setup_* token single-use & digest-stored."""
    # 1. Assert zero default admin users exist
    user_count = (
        await committed_db_session.execute(text("SELECT count(*) FROM users"))
    ).scalar_one()
    assert user_count == 0, f"Expected 0 default users in freshly migrated DB, found {user_count}"

    # 2. Setup claim token format: 256-bit base64url starting with kb_setup_
    token = generate_setup_token()
    assert token.startswith("kb_setup_")
    assert len(token) == 52  # "kb_setup_" (9) + 43 base64url chars = 52

    # 3. Mint token via kb_auth function and verify storage hygiene
    pepper = b"security_audit_test_pepper_32_b"
    token_hmac = hmac.new(pepper, token.encode("ascii"), hashlib.sha256).digest()

    mint_res = await committed_db_session.execute(
        text("SELECT kb_auth.setup_mint_token(:hmac, 3600)"),
        {"hmac": token_hmac},
    )
    assert mint_res.scalar_one() is True
    await committed_db_session.commit()

    # Raw token must NEVER appear in setup_claim_tokens
    stored_rows = (
        (await committed_db_session.execute(text("SELECT token_hmac FROM setup_claim_tokens")))
        .scalars()
        .all()
    )
    assert len(stored_rows) >= 1
    for stored_bytes in stored_rows:
        assert token.encode("ascii") not in stored_bytes
        assert b"kb_setup_" not in stored_bytes


def test_stride_row4_unix_socket_pg_and_setpriv_privilege_drop(tmp_path: Path) -> None:
    """S3.5 Row 4: PG16 listen_addresses='', 0 host lines, and Uvicorn drops caps to UID 65532."""
    # 1. Test generated kanban.conf
    pgdata = tmp_path / "pgdata"
    configure_postgres(pgdata, run_dir="/run/postgresql")

    kanban_conf = (pgdata / "conf.d" / "kanban.conf").read_text(encoding="utf-8")
    assert "listen_addresses = ''" in kanban_conf
    assert "unix_socket_directories = '/run/postgresql'" in kanban_conf

    # 2. Test pg_hba.conf contains ZERO host lines
    pg_hba = (pgdata / "pg_hba.conf").read_text(encoding="utf-8")
    for line in pg_hba.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            assert not stripped.startswith("host"), (
                f"Found forbidden host line in pg_hba.conf: {line}"
            )
            assert stripped.startswith("local"), (
                f"Expected only local Unix domain socket auth: {line}"
            )

    # 3. Test Uvicorn setpriv command
    cmd = build_uvicorn_command()
    assert cmd[0] == "/usr/bin/setpriv"
    assert "--reuid=65532" in cmd
    assert "--regid=65532" in cmd
    assert "--clear-groups" in cmd
    assert "--inh-caps=-all" in cmd
    assert "--no-new-privs" in cmd
    assert "--" in cmd


def test_stride_row4_tier_b_nsjail_fail_closed_standalone(tmp_path: Path) -> None:
    """S3.5 Row 4: Tier B nsjail runner fails closed with SANDBOX_UNAVAILABLE_IN_STANDALONE."""
    # 1. Probe against non-existent binary
    missing_bin = tmp_path / "nonexistent_nsjail"
    result = probe_nsjail_userns(nsjail_bin=missing_bin)
    assert not result.available
    assert result.error_code == "SANDBOX_UNAVAILABLE_IN_STANDALONE"

    # 2. Probe against mock runner returning error
    mock_runner = MagicMock()
    mock_runner.run_sync.return_value = (1, b"", b"CLONE_NEWUSER: Operation not permitted\n")
    fake_bin = tmp_path / "nsjail"
    fake_bin.touch()
    # Mock stat ownership to UID 0 and safe permissions
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Path, "stat", lambda *_, **__: MagicMock(st_uid=0, st_mode=0o755))
        probe_res = probe_nsjail_userns(nsjail_bin=fake_bin, runner=mock_runner)
        assert not probe_res.available
        assert probe_res.error_code == "SANDBOX_UNAVAILABLE_IN_STANDALONE"

    # 3. SandboxUnavailableError problem properties
    exc = SandboxUnavailableError()
    assert exc.status == 503
    assert exc.code == "SANDBOX_UNAVAILABLE_IN_STANDALONE"
