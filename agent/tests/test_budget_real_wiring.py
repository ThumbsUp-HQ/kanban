# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for real BudgetEnforcer wiring and cap preservation (KAN-71).

Covers:
  - Real UUID parameter forwarding in InAppSdkHarness.run().
  - Zero token_cap expansion in BudgetEnforcer.settle().
  - Out of budget rejection: BudgetExceeded halts execution cleanly.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from agent.budget import BudgetEnforcer, BudgetExceeded, get_current_period_dates
from agent.context.transition_context import RenderedContext
from agent.harnesses.in_app_sdk import InAppSdkHarness
from agent.testing.fixtures import FixtureLLMProvider
from database.tests.conftest import bootstrap_workspace_admin

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.committed_db


async def test_settle_preserves_strict_cap(db_session: AsyncSession) -> None:
    """Verify settle() does NOT expand token_cap when actual tokens exceed estimate."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    cfg_id = uuid.uuid4()
    d_start, _ = get_current_period_dates()

    # Create provider config and daily ledger row with strict cap=100
    await db_session.execute(
        text(
            "INSERT INTO ai_provider_configs "
            "(id, workspace_id, provider_kind, display_name, residency_tier, model_allowlist) "
            "VALUES (:id, :ws_id, 'fixture', 'Test Provider', 'default', ARRAY['fixture-model'])"
        ),
        {"id": cfg_id, "ws_id": ws_id},
    )
    ledger_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO ai_token_ledgers "
            "(id, workspace_id, provider_config_id, period_kind, "
            "period_start, token_cap, tokens_reserved, tokens_used) "
            "VALUES (:id, :ws_id, :cfg_id, 'daily', :p_start, 100, 0, 0)"
        ),
        {"id": ledger_id, "ws_id": ws_id, "cfg_id": cfg_id, "p_start": d_start},
    )
    await db_session.commit()

    enforcer = BudgetEnforcer(session=db_session)
    # Reserve 50 tokens
    reservation = await enforcer.reserve(
        workspace_id=ws_id,
        project_id=None,
        provider_config_id=cfg_id,
        estimate_tokens=50,
        session=db_session,
    )
    assert len(reservation.reserved_ledger_ids) == 1

    # Settle 80 tokens (overage beyond estimate 50, but cap must stay at 100)
    await enforcer.settle(reservation, actual_tokens=80, session=db_session)
    await db_session.commit()

    res = await db_session.execute(
        text("SELECT token_cap, tokens_reserved, tokens_used FROM ai_token_ledgers WHERE id = :id"),
        {"id": ledger_id},
    )
    row = res.mappings().one()
    # token_cap must remain strictly 100 (NOT expanded to higher values)
    assert row["token_cap"] == 100
    assert row["tokens_reserved"] == 0
    assert row["tokens_used"] == 80


async def test_in_app_sdk_harness_real_budget_wiring(db_session: AsyncSession) -> None:
    """Verify InAppSdkHarness uses real IDs and respects budget bounds."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    cfg_id = uuid.uuid4()
    d_start, _ = get_current_period_dates()

    await db_session.execute(
        text(
            "INSERT INTO ai_provider_configs "
            "(id, workspace_id, provider_kind, display_name, residency_tier, model_allowlist) "
            "VALUES (:id, :ws_id, 'fixture', 'Real Provider', 'default', ARRAY['fixture-model'])"
        ),
        {"id": cfg_id, "ws_id": ws_id},
    )
    # Set low cap of 10 tokens
    await db_session.execute(
        text(
            "INSERT INTO ai_token_ledgers "
            "(id, workspace_id, provider_config_id, period_kind, "
            "period_start, token_cap, tokens_reserved, tokens_used) "
            "VALUES (:id, :ws_id, :cfg_id, 'daily', :p_start, 10, 0, 0)"
        ),
        {"id": uuid.uuid4(), "ws_id": ws_id, "cfg_id": cfg_id, "p_start": d_start},
    )
    await db_session.commit()

    enforcer = BudgetEnforcer(session=db_session)
    provider = FixtureLLMProvider([])
    harness = InAppSdkHarness(provider=provider, budget_enforcer=enforcer, session=db_session)

    agent_spec = {
        "slug": "test-agent",
        "workspace_id": ws_id,
        "provider_config_id": cfg_id,
        "timeout_ms": 10000,
    }
    dummy_ctx = RenderedContext(
        yaml_bytes=b"ticket: {}",
        sha256="test",
        delimiter="---",
        verdict_nonce="nonce-123",
        ephemeral_token=bytearray(b"dummy"),
        allowed_mutable_fields=frozenset(),
    )

    # Reserving default estimate (1500 tokens) exceeds cap of 10 -> raises BudgetExceeded
    with pytest.raises(BudgetExceeded):
        await harness.run(dummy_ctx, agent_spec)
