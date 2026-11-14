# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""AI token budget enforcer: atomic reservation, settlement, and overage tracking (KB-P5-05a)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("agent.budget")

CODE_BUDGET_EXCEEDED: Final[str] = "AI_BUDGET_EXCEEDED"
LOG_BUDGET_OVERAGE: Final[str] = "AI_BUDGET_OVERAGE"


class BudgetExceeded(Exception):  # noqa: N818
    """Raised when an active token budget cap is exhausted for daily or monthly periods."""

    def __init__(
        self,
        period: str,
        message: str | None = None,
        code: str = CODE_BUDGET_EXCEEDED,
    ) -> None:
        """Initialize BudgetExceeded with exhausted period and standardized error code."""
        default_msg = f"Token budget cap exceeded for period '{period}'"
        super().__init__(message or default_msg)
        self.code = code
        self.period = period
        self.message = message or default_msg


@dataclass(frozen=True)
class Reservation:
    """Immutable reservation receipt tracking token allocations across active ledger rows."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    provider_config_id: uuid.UUID
    estimate_tokens: int
    reserved_ledger_ids: tuple[uuid.UUID, ...]


def get_current_period_dates(now_dt: datetime | None = None) -> tuple[date, date]:
    """Compute (daily_period_start, monthly_period_start) in UTC."""
    current_utc = (
        now_dt.astimezone(UTC)
        if now_dt is not None
        else datetime.now(UTC)
    )
    daily_start = current_utc.date()
    monthly_start = date(current_utc.year, current_utc.month, 1)
    return daily_start, monthly_start


class BudgetEnforcer:
    """Atomic token budget enforcer implementing the single-statement reserve/settle protocol."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        session_factory: object | None = None,
    ) -> None:
        """Initialize enforcer with an optional session or session factory."""
        self._session = session
        self._session_factory = session_factory

    def _resolve_session(self, session: AsyncSession | None) -> AsyncSession:
        """Resolve database session from arguments, instance attribute, or raise error."""
        if session is not None:
            return session
        if self._session is not None:
            return self._session
        msg = "BudgetEnforcer requires an active AsyncSession to execute database operations"
        raise ValueError(msg)

    async def reserve(  # noqa: PLR0913
        self,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID | None,
        provider_config_id: uuid.UUID,
        estimate_tokens: int,
        *,
        session: AsyncSession | None = None,
        now_dt: datetime | None = None,
    ) -> Reservation:
        """Atomically reserve tokens against daily and monthly ledger caps."""
        if estimate_tokens <= 0:
            msg = f"estimate_tokens must be greater than zero (got {estimate_tokens})"
            raise ValueError(msg)

        sess = self._resolve_session(session)
        daily_start, monthly_start = get_current_period_dates(now_dt)

        # Query active ledger rows matching the provider and period windows
        query_sql = text(
            "SELECT id, period_kind, token_cap, tokens_reserved, tokens_used "
            "FROM ai_token_ledgers "
            "WHERE workspace_id = :ws_id "
            "  AND (project_id IS NOT DISTINCT FROM :proj_id) "
            "  AND provider_config_id = :cfg_id "
            "  AND ( "
            "      (period_kind = 'daily' AND period_start = :daily_start) "
            "      OR "
            "      (period_kind = 'monthly' AND period_start = :monthly_start) "
            "  ) "
            "ORDER BY period_kind ASC"
        )
        params = {
            "ws_id": workspace_id,
            "proj_id": project_id,
            "cfg_id": provider_config_id,
            "daily_start": daily_start,
            "monthly_start": monthly_start,
        }

        res = await sess.execute(query_sql, params)
        rows = res.mappings().all()

        if not rows:
            # Missing ledger rows for both periods explicitly indicate no caps configured
            return Reservation(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                project_id=project_id,
                provider_config_id=provider_config_id,
                estimate_tokens=estimate_tokens,
                reserved_ledger_ids=(),
            )

        # Execute atomic updates within a savepoint/transaction to ensure all-or-nothing rollback
        reserved_ids: list[uuid.UUID] = []

        async with sess.begin_nested() if sess.in_transaction() else sess.begin():
            for row in rows:
                ledger_id = row["id"]
                p_kind = row["period_kind"]

                # Atomic single-statement reservation update
                update_sql = text(
                    "UPDATE ai_token_ledgers "
                    "SET tokens_reserved = tokens_reserved + :tokens "
                    "WHERE id = :lid "
                    "  AND tokens_used + tokens_reserved + :tokens <= token_cap "
                    "RETURNING id"
                )
                up_res = await sess.execute(
                    update_sql,
                    {"lid": ledger_id, "tokens": estimate_tokens},
                )
                matched = up_res.first()

                if matched is None:
                    # Cap exceeded for this period -> rolls back savepoint/transaction
                    msg = (
                        f"AI token budget exceeded for period '{p_kind}': "
                        f"estimate={estimate_tokens} tokens cannot be reserved under cap"
                    )
                    raise BudgetExceeded(period=p_kind, message=msg)

                reserved_ids.append(ledger_id)

        return Reservation(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            project_id=project_id,
            provider_config_id=provider_config_id,
            estimate_tokens=estimate_tokens,
            reserved_ledger_ids=tuple(reserved_ids),
        )

    async def settle(
        self,
        reservation: Reservation,
        actual_tokens: int,
        *,
        session: AsyncSession | None = None,
    ) -> None:
        """Settle a reservation, moving tokens from reserved to used and handling overages."""
        if actual_tokens < 0:
            msg = f"actual_tokens must be non-negative (got {actual_tokens})"
            raise ValueError(msg)

        if not reservation.reserved_ledger_ids:
            return

        sess = self._resolve_session(session)
        estimate = reservation.estimate_tokens

        if actual_tokens > estimate:
            overage = actual_tokens - estimate
            logger.warning(
                "%s: reservation=%s estimate=%d actual=%d overage=%d",
                LOG_BUDGET_OVERAGE,
                reservation.id,
                estimate,
                actual_tokens,
                overage,
            )

        async with sess.begin_nested() if sess.in_transaction() else sess.begin():
            for ledger_id in reservation.reserved_ledger_ids:
                # Deduct estimate from reserved and add actual to used.
                # Expand token_cap if overage exceeds old cap so accounting is never blocked.
                settle_sql = text(
                    "UPDATE ai_token_ledgers "
                    "SET tokens_reserved = GREATEST(0, tokens_reserved - :estimate), "
                    "    tokens_used = tokens_used + :actual, "
                    "    token_cap = GREATEST(token_cap, tokens_used + :actual) "
                    "WHERE id = :lid"
                )
                await sess.execute(
                    settle_sql,
                    {
                        "lid": ledger_id,
                        "estimate": estimate,
                        "actual": actual_tokens,
                    },
                )

    async def release(
        self,
        reservation: Reservation,
        *,
        session: AsyncSession | None = None,
    ) -> None:
        """Release a reservation on provider failure, restoring tokens_reserved to 0."""
        if not reservation.reserved_ledger_ids:
            return

        sess = self._resolve_session(session)
        estimate = reservation.estimate_tokens

        async with sess.begin_nested() if sess.in_transaction() else sess.begin():
            for ledger_id in reservation.reserved_ledger_ids:
                release_sql = text(
                    "UPDATE ai_token_ledgers "
                    "SET tokens_reserved = GREATEST(0, tokens_reserved - :estimate) "
                    "WHERE id = :lid"
                )
                await sess.execute(
                    release_sql,
                    {"lid": ledger_id, "estimate": estimate},
                )
