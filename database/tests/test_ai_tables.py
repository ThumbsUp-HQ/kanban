# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Database-tier tests for ai_provider_configs and ai_token_ledgers (KB-P5-05a, S10.1, S10.2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.models.ai import AITokenLedger
from database.tests.conftest import bind_ctx, bootstrap_workspace_admin

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_01_ai_provider_secret_security_definer(
    db_session: AsyncSession,
) -> None:
    """Test Case 1 (DB tier): ai_provider_secret returns secret columns under workspace scope."""
    ws_id, admin_id = await bootstrap_workspace_admin(db_session)
    cfg_id = uuid.uuid4()

    fake_ciphertext = b"\x01\x02\x03\x04encrypted-api-key"
    fake_nonce = b"123456789012"
    fake_wrapped_dek = b"\x01dek-wrapped-data"
    fake_kid = "kek-v1"

    await db_session.execute(
        text(
            "INSERT INTO ai_provider_configs ("
            "  id, workspace_id, provider_kind, display_name, model_allowlist, residency_tier,"
            "  wrapped_api_key, api_key_nonce, wrapped_dek, dek_kid, is_enabled"
            ") VALUES ("
            "  :id, :ws_id, 'openai', 'DB Test OpenAI', ARRAY['gpt-4o'], 'default',"
            "  :key, :nonce, :dek, :kid, TRUE"
            ")"
        ),
        {
            "id": cfg_id,
            "ws_id": ws_id,
            "key": fake_ciphertext,
            "nonce": fake_nonce,
            "dek": fake_wrapped_dek,
            "kid": fake_kid,
        },
    )

    # 1. Bind caller to workspace and invoke security definer function
    await bind_ctx(db_session, principal_id=admin_id, workspace_id=ws_id)
    fn_res = await db_session.execute(
        text(
            "SELECT wrapped_api_key, api_key_nonce, wrapped_dek, dek_kid "
            "FROM ai_provider_secret(:cid)"
        ),
        {"cid": cfg_id},
    )
    row = fn_res.mappings().first()
    assert row is not None
    assert bytes(row["wrapped_api_key"]) == fake_ciphertext
    assert bytes(row["api_key_nonce"]) == fake_nonce
    assert bytes(row["wrapped_dek"]) == fake_wrapped_dek
    assert row["dek_kid"] == fake_kid

    # 2. Cross-workspace caller sees 0 rows from ai_provider_secret
    other_ws_id = uuid.uuid4()
    await bind_ctx(db_session, principal_id=admin_id, workspace_id=other_ws_id)
    other_res = await db_session.execute(
        text("SELECT * FROM ai_provider_secret(:cid)"),
        {"cid": cfg_id},
    )
    assert other_res.mappings().first() is None


@pytest.mark.asyncio
async def test_02_column_level_revoke_and_non_admin_rls(
    db_session: AsyncSession,
) -> None:
    """Test Case 2: kanban_app SELECT wrapped_api_key fails closed; non-admin sees 0 rows."""
    ws_id, admin_id = await bootstrap_workspace_admin(db_session)
    cfg_id = uuid.uuid4()

    await db_session.execute(
        text(
            "INSERT INTO ai_provider_configs ("
            "  id, workspace_id, provider_kind, display_name, model_allowlist, residency_tier,"
            "  wrapped_api_key, api_key_nonce, wrapped_dek, dek_kid, is_enabled"
            ") VALUES ("
            "  :id, :ws_id, 'ollama', 'Local Ollama DDL', ARRAY['llama3.1:8b'], 'on-prem',"
            "  :key, :nonce, :dek, 'kek-v1', TRUE"
            ")"
        ),
        {
            "id": cfg_id,
            "ws_id": ws_id,
            "key": b"ciphertext",
            "nonce": b"nonce12bytes",
            "dek": b"dekbytes",
        },
    )

    # Provision a non-admin regular user with no role bindings
    regular_user_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
            "VALUES (:id, :ws_id, 'USER', 'Regular User')"
        ),
        {"id": regular_user_id, "ws_id": ws_id},
    )

    # Switch session authorization to least-privilege kanban_app
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))

    # Part A: kanban_app attempting SELECT wrapped_api_key directly triggers permission denied
    await bind_ctx(db_session, principal_id=admin_id, workspace_id=ws_id)
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT wrapped_api_key FROM ai_provider_configs WHERE id = :id"),
                {"id": cfg_id},
            )
    assert "permission denied" in str(exc_info.value).lower()

    # Part B: Non-admin principal sees 0 rows due to RLS admin predicate
    await bind_ctx(db_session, principal_id=regular_user_id, workspace_id=ws_id)
    res = await db_session.execute(
        text("SELECT id FROM ai_provider_configs WHERE workspace_id = :ws"),
        {"ws": ws_id},
    )
    rows = res.scalars().all()
    assert len(rows) == 0

    # Part C: Admin principal sees the config row (excluding revoked secret columns)
    await bind_ctx(db_session, principal_id=admin_id, workspace_id=ws_id)
    admin_res = await db_session.execute(
        text("SELECT id, display_name FROM ai_provider_configs WHERE workspace_id = :ws"),
        {"ws": ws_id},
    )
    admin_rows = admin_res.all()
    assert len(admin_rows) == 1
    assert admin_rows[0][0] == cfg_id


@pytest.mark.asyncio
async def test_03_ai_token_ledgers_ddl_and_constraints(
    db_session: AsyncSession,
) -> None:
    """Test Case 3 (DB tier): ai_token_ledgers check constraints and unique constraints."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    cfg_id = uuid.uuid4()

    await db_session.execute(
        text(
            "INSERT INTO ai_provider_configs ("
            "  id, workspace_id, provider_kind, display_name, model_allowlist, residency_tier"
            ") VALUES ("
            "  :id, :ws_id, 'fixture', 'Ledger Provider', ARRAY['m1'], 'default'"
            ")"
        ),
        {"id": cfg_id, "ws_id": ws_id},
    )

    today = datetime.now(UTC).date()
    ledger_id = uuid.uuid4()

    # 1. Valid insert with cap 100
    await db_session.execute(
        text(
            "INSERT INTO ai_token_ledgers ("
            "  id, workspace_id, project_id, provider_config_id, period_kind, period_start, "
            "  token_cap, tokens_reserved, tokens_used"
            ") VALUES ("
            "  :id, :ws_id, NULL, :cfg_id, 'daily', :p_start, 100, 20, 30"
            ")"
        ),
        {"id": ledger_id, "ws_id": ws_id, "cfg_id": cfg_id, "p_start": today},
    )

    ledger_row = await db_session.get(AITokenLedger, ledger_id)
    assert ledger_row is not None
    assert ledger_row.token_cap == 100
    assert ledger_row.tokens_reserved == 20
    assert ledger_row.tokens_used == 30

    # 2. Check constraint: tokens_used + tokens_reserved <= token_cap
    with pytest.raises(DBAPIError) as exc_cap:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE ai_token_ledgers "
                    "SET tokens_reserved = 80 WHERE id = :id"
                ),
                {"id": ledger_id},
            )
    assert "check constraint" in str(exc_cap.value).lower()

    # 3. Check constraint: negative tokens_reserved rejected
    with pytest.raises(DBAPIError) as exc_neg:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE ai_token_ledgers SET tokens_reserved = -1 WHERE id = :id"),
                {"id": ledger_id},
            )
    assert "check constraint" in str(exc_neg.value).lower()

    # 4. Duplicate period row for same key rejected by UNIQUE constraint
    with pytest.raises(DBAPIError) as exc_dup:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO ai_token_ledgers ("
                    "  id, workspace_id, project_id, provider_config_id, "
                    "  period_kind, period_start, token_cap"
                    ") VALUES ("
                    "  :id, :ws_id, NULL, :cfg_id, 'daily', :p_start, 200"
                    ")"
                ),
                {"id": uuid.uuid4(), "ws_id": ws_id, "cfg_id": cfg_id, "p_start": today},
            )
    assert "unique" in str(exc_dup.value).lower()
