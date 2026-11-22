# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Issue lease and monotonic fencing token concurrency service (KB-CONCURRENCY-01, KAN-69)."""

from __future__ import annotations

import datetime as dt
import uuid  # noqa: TC003
from typing import TYPE_CHECKING, Final

from sqlalchemy import select

from database.models.issue_lease import IssueLease
from database.models.issues import Issue  # noqa: TC001
from kanban.api.problems import ProblemException
from kanban.services.issue_keys import resolve_issue_ref

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

__all__ = [
    "DEFAULT_LEASE_TTL_SECONDS",
    "MAX_LEASE_TTL_SECONDS",
    "MIN_LEASE_TTL_SECONDS",
    "acquire_or_renew_issue_lease",
    "get_active_lease",
    "heartbeat_issue_lease",
    "release_issue_lease",
    "validate_caller_lease_and_fencing",
]

DEFAULT_LEASE_TTL_SECONDS: Final[int] = 900
MIN_LEASE_TTL_SECONDS: Final[int] = 60
MAX_LEASE_TTL_SECONDS: Final[int] = 7200


def _validate_ttl(ttl_seconds: int) -> None:
    """Validate lease time-to-live seconds within [60, 7200]."""
    if ttl_seconds < MIN_LEASE_TTL_SECONDS or ttl_seconds > MAX_LEASE_TTL_SECONDS:
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=(
                f"ttl_seconds must be between {MIN_LEASE_TTL_SECONDS} and {MAX_LEASE_TTL_SECONDS}"
            ),
            field="ttl_seconds",
        )


async def get_active_lease(
    session: AsyncSession,
    issue_id: uuid.UUID,
) -> IssueLease | None:
    """Retrieve unexpired lease for issue if one exists."""
    stmt = (
        select(IssueLease)
        .where(
            IssueLease.issue_id == issue_id,
            IssueLease.expires_at > dt.datetime.now(dt.UTC),
        )
        .limit(1)
    )
    res = await session.execute(stmt)
    return res.scalars().first()


async def acquire_or_renew_issue_lease(
    session: AsyncSession,
    caller: PrincipalContext,
    issue: Issue,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> IssueLease:
    """Atomically acquire or renew exclusive issue lease under row lock and bump fencing token."""
    _validate_ttl(ttl_seconds)
    now = dt.datetime.now(dt.UTC)
    expires_at = now + dt.timedelta(seconds=ttl_seconds)

    # 1. Lock existing lease row for this issue if present
    lease_stmt = select(IssueLease).where(IssueLease.issue_id == issue.id).with_for_update()
    existing_lease = (await session.execute(lease_stmt)).scalars().first()

    if (
        existing_lease is not None
        and existing_lease.expires_at > now
        and existing_lease.principal_id != caller.principal_id
    ):
        raise ProblemException(
            code="LEASE_HELD",
            status=409,
            title="Lease Held",
            detail=(
                f"Issue is actively leased by another principal until "
                f"{existing_lease.expires_at.isoformat()}"
            ),
            extra={
                "lease_id": str(existing_lease.id),
                "held_by": str(existing_lease.principal_id),
                "expires_at": existing_lease.expires_at.isoformat(),
            },
        )

    # 2. Atomically increment issue fencing token
    new_token = issue.fencing_token + 1
    issue.fencing_token = new_token

    # 3. Upsert lease record
    if existing_lease is not None:
        existing_lease.principal_id = caller.principal_id
        existing_lease.fencing_token = new_token
        existing_lease.expires_at = expires_at
        existing_lease.updated_at = now
        existing_lease.heartbeat_at = now
        lease = existing_lease
    else:
        lease = IssueLease(
            workspace_id=caller.workspace_id,
            issue_id=issue.id,
            principal_id=caller.principal_id,
            fencing_token=new_token,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
            heartbeat_at=now,
        )
        session.add(lease)

    await session.flush()
    await session.refresh(lease)
    return lease


async def heartbeat_issue_lease(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
    fencing_token: int | None = None,
) -> IssueLease:
    """Extend lease expiration for active lease held by caller."""
    _validate_ttl(ttl_seconds)
    issue = await resolve_issue_ref(session, caller, issue_ref)
    now = dt.datetime.now(dt.UTC)

    lease_stmt = select(IssueLease).where(IssueLease.issue_id == issue.id).with_for_update()
    lease = (await session.execute(lease_stmt)).scalars().first()

    if lease is None or lease.expires_at <= now:
        raise ProblemException(
            code="LEASE_EXPIRED",
            status=409,
            title="Lease Expired",
            detail="No active unexpired lease found on this issue to heartbeat",
        )

    if lease.principal_id != caller.principal_id:
        raise ProblemException(
            code="LEASE_HELD",
            status=409,
            title="Lease Held",
            detail="Cannot heartbeat lease held by another principal",
        )

    if fencing_token is not None and fencing_token < lease.fencing_token:
        raise ProblemException(
            code="FENCING_TOKEN_STALE",
            status=409,
            title="Fencing Token Stale",
            detail=(
                f"Supplied fencing_token {fencing_token} is older than active lease "
                f"fencing_token {lease.fencing_token}"
            ),
        )

    lease.expires_at = now + dt.timedelta(seconds=ttl_seconds)
    lease.heartbeat_at = now
    lease.updated_at = now

    await session.flush()
    await session.refresh(lease)
    return lease


async def release_issue_lease(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_ref: str,
    fencing_token: int | None = None,
) -> bool:
    """Release active lease on an issue held by caller or admin."""
    issue = await resolve_issue_ref(session, caller, issue_ref)
    lease_stmt = select(IssueLease).where(IssueLease.issue_id == issue.id).with_for_update()
    lease = (await session.execute(lease_stmt)).scalars().first()
    if lease is None:
        return False

    is_admin = bool(
        getattr(caller, "is_server_admin", False)
        or (hasattr(caller, "token_scopes") and "admin" in caller.token_scopes)
        or (
            hasattr(caller, "roles")
            and any(r in ("SERVER_ADMIN", "WORKSPACE_ADMIN") for r in caller.roles)
        )
    )

    if lease.principal_id != caller.principal_id and not is_admin:
        raise ProblemException(
            code="LEASE_HELD",
            status=403,
            title="Forbidden",
            detail="Cannot release lease held by another principal",
        )

    if fencing_token is not None and fencing_token < lease.fencing_token:
        raise ProblemException(
            code="FENCING_TOKEN_STALE",
            status=409,
            title="Fencing Token Stale",
            detail="Supplied fencing_token is stale",
        )

    await session.delete(lease)
    await session.flush()
    return True


async def validate_caller_lease_and_fencing(
    session: AsyncSession,
    caller: PrincipalContext,
    issue: Issue,
    *,
    fencing_token: int | None = None,
    admin_override: bool = False,
) -> None:
    """Verify write safety against stale fencing tokens and unexpired leases held by others."""
    if fencing_token is not None and fencing_token < issue.fencing_token:
        raise ProblemException(
            code="FENCING_TOKEN_STALE",
            status=409,
            title="Fencing Token Stale",
            detail=(
                f"Supplied fencing_token {fencing_token} is older than current issue "
                f"fencing_token {issue.fencing_token}"
            ),
        )

    if not admin_override:
        active_lease = await get_active_lease(session, issue.id)
        if active_lease is not None and active_lease.principal_id != caller.principal_id:
            raise ProblemException(
                code="LEASE_HELD",
                status=409,
                title="Lease Held",
                detail=(
                    f"Issue is leased by another principal until "
                    f"{active_lease.expires_at.isoformat()}"
                ),
            )
