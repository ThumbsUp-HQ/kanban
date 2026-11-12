# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for Argon2id hashing, HMAC pepper isolation, DoS concurrency, and NFKC (KB-P2-04)."""

from __future__ import annotations

import base64
from typing import Final

import pytest
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError

from kanban.api.problems import ProblemException
from kanban.auth.local.hashing import (
    _normalize_and_pepper,
    get_argon2_semaphore,
    get_auth_pepper,
    hash_password,
    hash_password_sync,
    needs_rehash,
    reset_argon2_semaphore,
    verify_password,
    verify_password_sync,
)

PEPPER_P1: Final[bytes] = b"1" * 32
PEPPER_P2: Final[bytes] = b"2" * 32


@pytest.mark.asyncio
async def test_case_2_argon2id_parameters() -> None:
    """Test Case 2: Produced hash string contains $argon2id$v=19$m=65536,t=3,p=4$."""
    password = "CorrectHorseBatteryStaple123"
    sync_hash = hash_password_sync(password, PEPPER_P1)
    async_hash = await hash_password(password, PEPPER_P1)

    expected_prefix = "$argon2id$v=19$m=65536,t=3,p=4$"
    assert sync_hash.startswith(expected_prefix)
    assert async_hash.startswith(expected_prefix)
    assert needs_rehash(sync_hash) is False
    assert needs_rehash(async_hash) is False


@pytest.mark.asyncio
async def test_case_3_pepper_security_and_raw_isolation() -> None:
    """Test Case 3: Hash under pepper P1 fails under pepper P2, and raw Argon2 verify raises."""
    password = "SensitiveAdminPassword456"
    stored_hash = await hash_password(password, PEPPER_P1)

    # 1. Verification succeeds under identical pepper P1
    assert await verify_password(stored_hash, password, PEPPER_P1) is True

    # 2. Verification fails when checked under different pepper P2
    assert await verify_password(stored_hash, password, PEPPER_P2) is False

    # 3. Direct verification without HMAC pepper step fails
    raw_hasher = PasswordHasher()
    with pytest.raises(VerifyMismatchError):
        raw_hasher.verify(stored_hash, password)


@pytest.mark.asyncio
async def test_case_8_cost_dos_concurrency_bounding() -> None:
    """Test Case 8: When concurrency semaphore is saturated, timeout raises 503 AUTH_BUSY."""
    reset_argon2_semaphore()
    sem = get_argon2_semaphore(concurrency=1)

    # Acquire the single available permit to simulate full capacity
    await sem.acquire()
    try:
        # Second attempt should time out and raise RFC 7807 503 AUTH_BUSY
        with pytest.raises(ProblemException) as exc_info:
            await verify_password(
                "$argon2id$v=19$m=65536,t=3,p=4$dummy",
                "SomePassword123",
                PEPPER_P1,
                timeout_seconds=0.05,
            )

        problem = exc_info.value
        assert problem.status == 503
        assert problem.code == "AUTH_BUSY"
        assert problem.headers is not None
        assert problem.headers.get("Retry-After") == "2"
    finally:
        sem.release()
        reset_argon2_semaphore()


@pytest.mark.asyncio
async def test_case_9_boundary_lengths_and_nfkc_normalization() -> None:
    """Test Case 9: Bounds [8, 1024], rejection work, and NFKC full-width equivalence."""
    valid_password = "StandardPassword789"
    stored_hash = hash_password_sync(valid_password, PEPPER_P1)

    # 1. 7-byte password rejected during verify (returns False without exception)
    seven_bytes = "1234567"
    assert len(seven_bytes.encode("utf-8")) == 7
    assert verify_password_sync(stored_hash, seven_bytes, PEPPER_P1) is False

    # 7-byte password rejected during hash_password_sync (raises ValueError)
    with pytest.raises(ValueError, match="between 8 and 1024"):
        hash_password_sync(seven_bytes, PEPPER_P1)

    # 2. 1025-byte password rejected during verify (returns False)
    too_long = "a" * 1025
    assert len(too_long.encode("utf-8")) == 1025
    assert verify_password_sync(stored_hash, too_long, PEPPER_P1) is False

    with pytest.raises(ValueError, match="between 8 and 1024"):
        hash_password_sync(too_long, PEPPER_P1)

    # 3. Exactly 1024-byte password accepted and verified
    max_password = "k" * 1024
    max_hash = hash_password_sync(max_password, PEPPER_P1)
    assert verify_password_sync(max_hash, max_password, PEPPER_P1) is True

    # 4. NFKC full-width character normalization equivalence
    ascii_password = "Password123"
    fullwidth_password = "Ｐａｓｓｗｏｒｄ１２３"  # noqa: RUF001
    nfkc_hash = hash_password_sync(ascii_password, PEPPER_P1)
    assert verify_password_sync(nfkc_hash, fullwidth_password, PEPPER_P1) is True


@pytest.mark.asyncio
async def test_case_10_rehash_upgrade_from_t2_to_t3() -> None:
    """Test Case 10: Legacy hash with t=2 verifies and triggers needs_rehash upgrade to t=3."""
    password = "RehashTargetPassword999"

    # Create legacy hash with t=2
    hasher_t2 = PasswordHasher(
        time_cost=2,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        salt_len=16,
        type=Type.ID,
    )
    b64_mac = _normalize_and_pepper(password, PEPPER_P1)
    legacy_hash = hasher_t2.hash(b64_mac)

    assert legacy_hash.startswith("$argon2id$v=19$m=65536,t=2,p=4$")
    assert needs_rehash(legacy_hash) is True

    # Legacy hash successfully verifies
    assert verify_password_sync(legacy_hash, password, PEPPER_P1) is True

    # Rehash produces t=3 hash
    upgraded_hash = hash_password_sync(password, PEPPER_P1)
    assert upgraded_hash.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert needs_rehash(upgraded_hash) is False
    assert verify_password_sync(upgraded_hash, password, PEPPER_P1) is True


def test_get_auth_pepper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_auth_pepper resolution from keyring and environment fallback."""
    pepper_bytes = b"k" * 32
    b64_pepper = base64.urlsafe_b64encode(pepper_bytes).decode("ascii")

    class MockKeyMaterial:
        auth_pepper = pepper_bytes

    # 1. Key material load success
    monkeypatch.setattr("kanban.auth.local.hashing.load_key_material", MockKeyMaterial)
    assert get_auth_pepper() == pepper_bytes

    # 2. Key material failure with environment variable fallback
    def raise_err() -> None:
        msg = "No keyring file"
        raise RuntimeError(msg)

    monkeypatch.setattr("kanban.auth.local.hashing.load_key_material", raise_err)
    monkeypatch.setenv("KB_AUTH_PEPPER", b64_pepper)
    assert get_auth_pepper() == pepper_bytes

    # 3. Key material failure with missing environment variable
    monkeypatch.delenv("KB_AUTH_PEPPER", raising=False)
    monkeypatch.delenv("KANBAN_AUTH_PEPPER", raising=False)
    with pytest.raises(ValueError, match="Authentication pepper"):
        get_auth_pepper()
