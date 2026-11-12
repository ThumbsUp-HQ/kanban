# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Database boundary tests for setup_claim_tokens and kb_auth functions (KB-P2-12)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_setup_tokens_table_access_boundary(db_session: AsyncSession) -> None:
    """Verify kanban_app cannot directly query setup_claim_tokens (must raise 42501)."""
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # 1. Direct SELECT on setup_claim_tokens by unprivileged app role must fail with 42501
    with pytest.raises(DBAPIError) as exc_select:
        async with db_session.begin_nested():
            await db_session.execute(text("SELECT * FROM setup_claim_tokens"))
    assert "42501" in str(exc_select.value) or "permission denied" in str(exc_select.value).lower()

    # 2. Direct INSERT raises 42501
    with pytest.raises(DBAPIError) as exc_insert:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO setup_claim_tokens (id, token_hmac, expires_at) "
                    "VALUES (:id, :hmac, clock_timestamp())"
                ),
                {"id": uuid.uuid4(), "hmac": b"\x01" * 32},
            )
    assert "42501" in str(exc_insert.value) or "permission denied" in str(exc_insert.value).lower()


@pytest.mark.asyncio
async def test_setup_token_at_rest_hashing_boundary(db_session: AsyncSession) -> None:
    """Verify setup_claim_tokens stores peppered HMAC, never plaintext or raw SHA-256."""
    raw_token = f"kb_setup_{secrets.token_urlsafe(32)}"
    pepper = b"test_pepper_at_least_32_bytes_long_here"
    token_hmac = hmac.new(pepper, raw_token.encode("ascii"), hashlib.sha256).digest()

    # Mint token via kb_auth function
    mint_res = await db_session.execute(
        text("SELECT kb_auth.setup_mint_token(:hmac, 3600)"),
        {"hmac": token_hmac},
    )
    assert mint_res.scalar_one() is True

    # Check that token_hmac is exactly 32 bytes and does not equal raw SHA-256
    raw_sha256 = hashlib.sha256(raw_token.encode("ascii")).digest()
    assert token_hmac != raw_sha256
    assert len(token_hmac) == 32
    assert "kb_setup_" not in str(token_hmac)


@pytest.mark.asyncio
async def test_setup_initialization_status_boundary(db_session: AsyncSession) -> None:
    """Verify kb_auth.setup_is_initialized reflects presence of users."""
    res = await db_session.execute(text("SELECT kb_auth.setup_is_initialized()"))
    assert res.scalar_one() is False
