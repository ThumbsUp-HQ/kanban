# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Service layer for admin link auditor operations and audited purging (KB-P4-11, S12.3)."""

from __future__ import annotations

import base64
import uuid
from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import select, text

from database.models.spine import InvalidObjectLinkAudit
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.link_auditor import (
    InvalidLinkReason,
    LinkAuditListResponse,
    LinkAuditRecordResponse,
    LinkAuditScanResponse,
    LinkPurgeResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

MIN_PURGE_REASON_LEN: Final[int] = 10
MAX_PURGE_REASON_LEN: Final[int] = 500
MAX_PURGE_BATCH_SIZE: Final[int] = 200
DEFAULT_AUDIT_LIMIT: Final[int] = 50
MAX_AUDIT_LIMIT: Final[int] = 100


def _encode_cursor(detected_at: datetime, record_id: uuid.UUID) -> str:
    """Encode keyset pagination cursor."""
    raw = f"{detected_at.isoformat()}|{record_id}"
    return base64.urlsafe_b64encode(raw.encode("ascii")).decode("ascii")


def _decode_cursor(cursor_str: str) -> tuple[datetime, uuid.UUID]:
    """Decode keyset pagination cursor."""
    try:
        raw = base64.urlsafe_b64decode(cursor_str.encode("ascii")).decode("ascii")
        dt_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(dt_str), uuid.UUID(id_str)
    except Exception as exc:
        raise ProblemException(
            code="INVALID_CURSOR",
            status=422,
            title="Validation Error",
            detail="Pagination cursor is invalid or malformed",
        ) from exc


async def run_link_audit(
    session: AsyncSession,
    caller: PrincipalContext,  # noqa: ARG001
    workspace_id: uuid.UUID,
) -> LinkAuditScanResponse:
    """Execute workspace link auditor and return counts grouped across 6 invalidity classes."""
    stmt = text("SELECT audit_id, link_id, reason FROM audit_object_links(:workspace_id)")
    rows = (await session.execute(stmt, {"workspace_id": workspace_id})).all()

    by_reason: dict[str, int] = defaultdict(int)
    for row in rows:
        reason_val = str(row[2])
        by_reason[reason_val] += 1

    return LinkAuditScanResponse(
        flagged_total=len(rows),
        by_reason=dict(by_reason),
    )


async def list_link_audits(  # noqa: PLR0913
    session: AsyncSession,
    caller: PrincipalContext,  # noqa: ARG001
    workspace_id: uuid.UUID,
    *,
    reason_code: str | None = None,
    status: str = "unpurged",
    limit: int = DEFAULT_AUDIT_LIMIT,
    cursor: str | None = None,
) -> LinkAuditListResponse:
    """List paginated link audit records with optional status and reason filters."""
    # Validate status filter
    valid_statuses = {"unpurged", "purged", "resolved", "all"}
    if status not in valid_statuses:
        allowed = ", ".join(sorted(valid_statuses))
        raise ProblemException(
            code="INVALID_STATUS",
            status=422,
            title="Validation Error",
            detail=f"Unknown status filter '{status}'. Valid values: {allowed}",
        )

    # Validate reason_code filter if present
    if reason_code is not None:
        try:
            InvalidLinkReason(reason_code)
        except ValueError as exc:
            raise ProblemException(
                code="INVALID_REASON_CODE",
                status=422,
                title="Validation Error",
                detail=f"Unknown reason_code filter: {reason_code}",
            ) from exc

    page_limit = min(max(limit, 1), MAX_AUDIT_LIMIT)

    query = select(InvalidObjectLinkAudit).where(
        InvalidObjectLinkAudit.workspace_id == workspace_id
    )

    if status == "unpurged":
        query = query.where(
            InvalidObjectLinkAudit.purged_at.is_(None),
            InvalidObjectLinkAudit.resolved_at.is_(None),
        )
    elif status == "purged":
        query = query.where(InvalidObjectLinkAudit.purged_at.is_not(None))
    elif status == "resolved":
        query = query.where(InvalidObjectLinkAudit.resolved_at.is_not(None))

    if reason_code is not None:
        query = query.where(InvalidObjectLinkAudit.reason == reason_code)

    if cursor is not None:
        cursor_dt, cursor_id = _decode_cursor(cursor)
        query = query.where(
            (InvalidObjectLinkAudit.detected_at < cursor_dt)
            | (
                (InvalidObjectLinkAudit.detected_at == cursor_dt)
                & (InvalidObjectLinkAudit.id < cursor_id)
            )
        )

    query = query.order_by(
        InvalidObjectLinkAudit.detected_at.desc(),
        InvalidObjectLinkAudit.id.desc(),
    ).limit(page_limit + 1)

    records = (await session.execute(query)).scalars().all()

    has_more = len(records) > page_limit
    items_to_return = records[:page_limit]

    next_cursor = None
    if has_more and items_to_return:
        last_item = items_to_return[-1]
        next_cursor = _encode_cursor(last_item.detected_at, last_item.id)

    items = [
        LinkAuditRecordResponse(
            id=r.id,
            workspace_id=r.workspace_id,
            link_id=r.link_id,
            reason=str(r.reason),
            detected_at=r.detected_at,
            purged_at=r.purged_at,
            resolved_at=r.resolved_at,
            link_snapshot=r.link_snapshot,
            source_snapshot=r.source_snapshot,
            target_snapshot=r.target_snapshot,
        )
        for r in items_to_return
    ]

    return LinkAuditListResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
    )


async def purge_flagged_links(
    session: AsyncSession,
    caller: PrincipalContext,
    workspace_id: uuid.UUID,
    *,
    audit_ids: list[uuid.UUID],
    reason: str,
) -> LinkPurgeResponse:
    """Execute audited purge of flagged invalid object links."""
    clean_reason = reason.strip()
    if len(clean_reason) < MIN_PURGE_REASON_LEN or len(clean_reason) > MAX_PURGE_REASON_LEN:
        raise ProblemException(
            code="REASON_REQUIRED",
            status=422,
            title="Validation Error",
            detail="Purge reason must be between 10 and 500 characters",
        )

    unique_audit_ids = list(set(audit_ids))
    if len(unique_audit_ids) < 1 or len(unique_audit_ids) > MAX_PURGE_BATCH_SIZE:
        raise ProblemException(
            code="INVALID_AUDIT_BATCH",
            status=422,
            title="Validation Error",
            detail=f"Batch size must be between 1 and {MAX_PURGE_BATCH_SIZE} audit IDs",
        )

    # Pre-check: Verify every requested audit record exists, is within workspace, and is unpurged
    check_stmt = select(
        InvalidObjectLinkAudit.id,
        InvalidObjectLinkAudit.purged_at,
        InvalidObjectLinkAudit.resolved_at,
    ).where(
        InvalidObjectLinkAudit.id.in_(unique_audit_ids),
        InvalidObjectLinkAudit.workspace_id == workspace_id,
    )
    rows = (await session.execute(check_stmt)).all()
    valid_ids = {r[0] for r in rows if r[1] is None and r[2] is None}

    if len(valid_ids) != len(unique_audit_ids):
        raise ProblemException(
            code="LINK_NOT_FLAGGED",
            status=409,
            title="Link Not Flagged",
            detail="One or more audit IDs are not flagged as invalid or are already purged.",
        )

    # Execute audited purge
    purge_stmt = text(
        "SELECT purged_audit_id, purged_link_id, activity_id "
        "FROM purge_invalid_object_links(CAST(:audit_ids AS uuid[]), :actor_id, :reason)"
    )
    purge_res = (
        await session.execute(
            purge_stmt,
            {
                "audit_ids": unique_audit_ids,
                "actor_id": caller.principal_id,
                "reason": clean_reason,
            },
        )
    ).all()

    activity_ids = [str(r[2]) for r in purge_res if r[2] is not None]

    return LinkPurgeResponse(
        purged_count=len(purge_res),
        activity_ids=activity_ids,
    )
