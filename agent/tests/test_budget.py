# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and concurrency tests for BudgetEnforcer (KB-P5-05a, S10.2)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agent.budget import (
    CODE_BUDGET_EXCEEDED,
    LOG_BUDGET_OVERAGE,
    BudgetEnforcer,
    BudgetExceeded,
    Reservation,
    get_current_period_dates,
)
from database.models.ai import AITokenLedger
from database.tests.conftest import bootstrap_workspace_admin

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


def _load_cassette_usage(cassette_filename: str) -> int:
    """Load total_tokens count from fixture cassette YAML."""
    fixture_path = (
        Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "ai" / cassette_filename
    )
    raw = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    return int(raw["usage"]["total_tokens"])


async def _setup_provider_and_ledgers(  # noqa: PLR0913
    session: AsyncSession,
    ws_id: uuid.UUID,
    *,
    daily_cap: int = 500,
    monthly_cap: int = 2000,
    daily_used: int = 0,
    monthly_used: int = 0,
    now_dt: datetime | None = None,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create an AIProviderConfig and active daily/monthly AITokenLedger rows."""
    cfg_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO ai_provider_configs ("
            "  id, workspace_id, provider_kind, display_name, model_allowlist, residency_tier"
            ") VALUES ("
            "  :id, :ws_id, 'fixture', 'Test Provider', ARRAY['m1'], 'default'"
            ")"
        ),
        {"id": cfg_id, "ws_id": ws_id},
    )

    daily_date, monthly_date = get_current_period_dates(now_dt)

    daily_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO ai_token_ledgers ("
            "  id, workspace_id, project_id, provider_config_id, period_kind, period_start, "
            "  token_cap, tokens_reserved, tokens_used"
            ") VALUES ("
            "  :id, :ws_id, NULL, :cfg_id, 'daily', :p_start, :cap, 0, :used"
            ")"
        ),
        {
            "id": daily_id,
            "ws_id": ws_id,
            "cfg_id": cfg_id,
            "p_start": daily_date,
            "cap": daily_cap,
            "used": daily_used,
        },
    )

    monthly_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO ai_token_ledgers ("
            "  id, workspace_id, project_id, provider_config_id, period_kind, period_start, "
            "  token_cap, tokens_reserved, tokens_used"
            ") VALUES ("
            "  :id, :ws_id, NULL, :cfg_id, 'monthly', :p_start, :cap, 0, :used"
            ")"
        ),
        {
            "id": monthly_id,
            "ws_id": ws_id,
            "cfg_id": cfg_id,
            "p_start": monthly_date,
            "cap": monthly_cap,
            "used": monthly_used,
        },
    )

    return cfg_id, daily_id, monthly_id


@pytest.mark.asyncio
async def test_06_budget_positive_reserve_and_settle(db_session: AsyncSession) -> None:
    """Test Case 6: Reserve 64, settle 48 -> tokens_used=48, tokens_reserved=0."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    actual_tokens = _load_cassette_usage("budget_usage_48_tokens.yaml")
    assert actual_tokens == 48

    cfg_id, daily_id, monthly_id = await _setup_provider_and_ledgers(
        db_session,
        ws_id,
        daily_cap=1000,
        monthly_cap=5000,
    )

    enforcer = BudgetEnforcer(db_session)

    # 1. Reserve 64 tokens
    reservation = await enforcer.reserve(
        workspace_id=ws_id,
        project_id=None,
        provider_config_id=cfg_id,
        estimate_tokens=64,
    )
    assert reservation.estimate_tokens == 64
    assert len(reservation.reserved_ledger_ids) == 2

    # Verify reservation state
    res_daily = await db_session.get(AITokenLedger, daily_id)
    assert res_daily is not None
    assert res_daily.tokens_reserved == 64
    assert res_daily.tokens_used == 0

    # 2. Settle 48 tokens from cassette
    await enforcer.settle(reservation, actual_tokens)

    # Verify final state: used=48, reserved=0 on both ledgers
    await db_session.refresh(res_daily)
    assert res_daily.tokens_used == 48
    assert res_daily.tokens_reserved == 0

    res_monthly = await db_session.get(AITokenLedger, monthly_id)
    assert res_monthly is not None
    assert res_monthly.tokens_used == 48
    assert res_monthly.tokens_reserved == 0


@pytest.mark.asyncio
async def test_07_budget_negative_rollback_on_monthly_exhaustion(db_session: AsyncSession) -> None:
    """Test Case 7: Reserve 11 against remaining 10 raises BudgetExceeded; daily unchanged."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)

    # Daily cap 500 (plenty), Monthly cap 100 with used=90 (remaining: 10)
    cfg_id, daily_id, monthly_id = await _setup_provider_and_ledgers(
        db_session,
        ws_id,
        daily_cap=500,
        monthly_cap=100,
        monthly_used=90,
    )

    enforcer = BudgetEnforcer(db_session)

    # Attempting to reserve 11 exceeds monthly cap (90 + 11 = 101 > 100)
    with pytest.raises(BudgetExceeded) as exc_info:
        await enforcer.reserve(
            workspace_id=ws_id,
            project_id=None,
            provider_config_id=cfg_id,
            estimate_tokens=11,
        )

    assert exc_info.value.code == CODE_BUDGET_EXCEEDED
    assert exc_info.value.period == "monthly"

    # Transaction rolled back: daily ledger tokens_reserved remains strictly 0
    daily_row = await db_session.get(AITokenLedger, daily_id)
    assert daily_row is not None
    assert daily_row.tokens_reserved == 0
    assert daily_row.tokens_used == 0

    monthly_row = await db_session.get(AITokenLedger, monthly_id)
    assert monthly_row is not None
    assert monthly_row.tokens_reserved == 0
    assert monthly_row.tokens_used == 90


@pytest.mark.committed_db
@pytest.mark.asyncio
async def test_08_concurrency_fifty_workers_twenty_succeed(
    committed_db_session: AsyncSession,
    pg_worker_db: AsyncEngine,
) -> None:
    """Test Case 8: Concurrency: 50 concurrent reserve(10) against cap 200 -> exactly 20 succeed."""
    ws_id, _ = await bootstrap_workspace_admin(committed_db_session)
    cfg_id, daily_id, _ = await _setup_provider_and_ledgers(
        committed_db_session,
        ws_id,
        daily_cap=200,
        monthly_cap=2000,
    )
    await committed_db_session.commit()

    enforcer = BudgetEnforcer()
    success_count = 0
    failure_count = 0
    results_lock = asyncio.Lock()

    async def worker(_worker_idx: int) -> None:
        nonlocal success_count, failure_count
        async with AsyncSession(pg_worker_db, expire_on_commit=False) as session:
            try:
                await enforcer.reserve(
                    workspace_id=ws_id,
                    project_id=None,
                    provider_config_id=cfg_id,
                    estimate_tokens=10,
                    session=session,
                )
                await session.commit()
                async with results_lock:
                    success_count += 1
            except BudgetExceeded:
                await session.rollback()
                async with results_lock:
                    failure_count += 1

    tasks = [worker(i) for i in range(50)]
    await asyncio.gather(*tasks)

    # Read final ledger totals under committed session
    await committed_db_session.commit()
    final_ledger = await committed_db_session.get(AITokenLedger, daily_id)
    assert final_ledger is not None

    total_allocated = final_ledger.tokens_used + final_ledger.tokens_reserved

    # Print results for concurrency-proof.txt capture
    print(  # noqa: T201
        f"\n[CONCURRENCY PROOF] workers=50 successes={success_count} "
        f"failures={failure_count} total_reserved={final_ledger.tokens_reserved} "
        f"total_used={final_ledger.tokens_used} total_allocated={total_allocated}"
    )

    assert success_count == 20
    assert failure_count == 30
    assert total_allocated == 200
    assert final_ledger.tokens_reserved == 200


@pytest.mark.asyncio
async def test_09_fault_release_and_overage_logging(
    db_session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test Case 9: Release resets reserved to 0; overage logs AI_BUDGET_OVERAGE."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    cfg_id, daily_id, _ = await _setup_provider_and_ledgers(
        db_session,
        ws_id,
        daily_cap=500,
        monthly_cap=2000,
    )

    enforcer = BudgetEnforcer(db_session)

    # 1. Fault release: provider error resets reserved to 0
    res1 = await enforcer.reserve(
        workspace_id=ws_id,
        project_id=None,
        provider_config_id=cfg_id,
        estimate_tokens=64,
    )
    daily_row = await db_session.get(AITokenLedger, daily_id)
    assert daily_row is not None
    assert daily_row.tokens_reserved == 64

    await enforcer.release(res1)
    await db_session.refresh(daily_row)
    assert daily_row.tokens_reserved == 0
    assert daily_row.tokens_used == 0

    # 2. Overage cassette: actual 120 exceeds estimate 64
    overage_tokens = _load_cassette_usage("budget_usage_overage.yaml")
    assert overage_tokens == 120

    res2 = await enforcer.reserve(
        workspace_id=ws_id,
        project_id=None,
        provider_config_id=cfg_id,
        estimate_tokens=64,
    )

    with caplog.at_level(logging.WARNING, logger="agent.budget"):
        await enforcer.settle(res2, overage_tokens)

    # Verify AI_BUDGET_OVERAGE log presence
    assert any(LOG_BUDGET_OVERAGE in record.message for record in caplog.records)

    # Verify final totals: reserved=0, used=120
    await db_session.refresh(daily_row)
    assert daily_row.tokens_reserved == 0
    assert daily_row.tokens_used == 120


@pytest.mark.asyncio
async def test_10_boundary_exact_cap_and_midnight_rollover(db_session: AsyncSession) -> None:
    """Test Case 10: Exact cap succeeds; cap+1 fails; midnight rollover uses new daily row."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    dt_day1 = datetime(2026, 11, 12, 23, 59, 59, tzinfo=UTC)
    dt_day2 = datetime(2026, 11, 13, 0, 0, 0, tzinfo=UTC)

    # Setup day 1 ledgers with cap=100
    cfg_id, day1_daily_id, _ = await _setup_provider_and_ledgers(
        db_session,
        ws_id,
        daily_cap=100,
        monthly_cap=500,
        now_dt=dt_day1,
    )

    enforcer = BudgetEnforcer(db_session)

    # 1. Reserving exactly to cap (100) succeeds
    res_exact = await enforcer.reserve(
        workspace_id=ws_id,
        project_id=None,
        provider_config_id=cfg_id,
        estimate_tokens=100,
        now_dt=dt_day1,
    )
    assert res_exact.estimate_tokens == 100

    day1_row = await db_session.get(AITokenLedger, day1_daily_id)
    assert day1_row is not None
    assert day1_row.tokens_reserved == 100

    # 2. Reserving cap+1 (even 1 more token) fails with BudgetExceeded
    with pytest.raises(BudgetExceeded) as exc_info:
        await enforcer.reserve(
            workspace_id=ws_id,
            project_id=None,
            provider_config_id=cfg_id,
            estimate_tokens=1,
            now_dt=dt_day1,
        )
    assert exc_info.value.period == "daily"

    # 3. Settle exact reservation
    await enforcer.settle(res_exact, 100)
    await db_session.refresh(day1_row)
    assert day1_row.tokens_used == 100
    assert day1_row.tokens_reserved == 0

    # 4. Period rollover at 00:00:00Z uses a new daily row
    # Provision day 2 daily ledger row
    day2_daily_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO ai_token_ledgers ("
            "  id, workspace_id, project_id, provider_config_id, period_kind, period_start, "
            "  token_cap, tokens_reserved, tokens_used"
            ") VALUES ("
            "  :id, :ws_id, NULL, :cfg_id, 'daily', :p_start, 100, 0, 0"
            ")"
        ),
        {
            "id": day2_daily_id,
            "ws_id": ws_id,
            "cfg_id": cfg_id,
            "p_start": dt_day2.date(),
        },
    )

    # Day 2 reservation succeeds because day 2 has a fresh 100-token cap
    res_day2 = await enforcer.reserve(
        workspace_id=ws_id,
        project_id=None,
        provider_config_id=cfg_id,
        estimate_tokens=50,
        now_dt=dt_day2,
    )
    assert res_day2.estimate_tokens == 50

    day2_row = await db_session.get(AITokenLedger, day2_daily_id)
    assert day2_row is not None
    assert day2_row.tokens_reserved == 50
    assert day2_row.tokens_used == 0


@pytest.mark.asyncio
async def test_budget_enforcer_validation_and_no_cap(db_session: AsyncSession) -> None:
    """Verify input validation and behavior when no ledger caps are configured."""
    ws_id, _ = await bootstrap_workspace_admin(db_session)
    enforcer = BudgetEnforcer(db_session)
    cfg_id = uuid.uuid4()

    # 1. estimate_tokens <= 0 rejected
    with pytest.raises(ValueError, match="estimate_tokens must be greater than zero"):
        await enforcer.reserve(ws_id, None, cfg_id, 0)
    with pytest.raises(ValueError, match="estimate_tokens must be greater than zero"):
        await enforcer.reserve(ws_id, None, cfg_id, -10)

    # 2. actual_tokens < 0 rejected
    dummy_res = Reservation(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        project_id=None,
        provider_config_id=cfg_id,
        estimate_tokens=50,
        reserved_ledger_ids=(),
    )
    with pytest.raises(ValueError, match="actual_tokens must be non-negative"):
        await enforcer.settle(dummy_res, -5)

    # 3. Missing session raises ValueError
    unbound_enforcer = BudgetEnforcer()
    with pytest.raises(ValueError, match="BudgetEnforcer requires an active AsyncSession"):
        await unbound_enforcer.reserve(ws_id, None, cfg_id, 10)

    # 4. No ledgers configured -> returns Reservation with empty reserved_ledger_ids
    no_cap_res = await enforcer.reserve(ws_id, None, cfg_id, 100)
    assert no_cap_res.reserved_ledger_ids == ()
    # settle and release on empty reservation are safe no-ops
    await enforcer.settle(no_cap_res, 100)
    await enforcer.release(no_cap_res)
