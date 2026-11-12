# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Notifications API endpoints (S7.2 8l, S3.4; KB-P3-06)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Required at runtime by FastAPI path parameter resolution
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession  # Required by FastAPI dependency injection

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.notifications import (
    MarkAllReadResponse,
    NotificationListResponse,
)
from kanban.services import notifications as svc

router = APIRouter(tags=["notifications"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.get(
    "/notifications",
    status_code=200,
    response_model=NotificationListResponse,
    summary="List caller's notifications",
)
async def list_notifications(
    caller: Caller,
    session: Session,
    *,
    unread: Annotated[bool, Query(description="Filter for unread notifications only")] = False,
    cursor: Annotated[str | None, Query(description="Keyset pagination cursor")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Page limit (1..100)")] = 30,
) -> NotificationListResponse:
    """Return paginated notifications for the calling user."""
    return await svc.list_notifications(session, caller, unread=unread, cursor=cursor, limit=limit)


@router.post(
    "/notifications/{notification_id}/read",
    status_code=204,
    summary="Mark a notification as read",
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> Response:
    """Mark an individual notification as read (self only)."""
    async with timing_floor(floor_ms=25.0):
        await svc.mark_notification_read(session, caller, notification_id)
        return Response(status_code=204)


@router.post(
    "/notifications/read-all",
    status_code=200,
    response_model=MarkAllReadResponse,
    summary="Mark all unread notifications as read",
)
async def mark_all_read(
    caller: Caller,
    session: Session,
) -> MarkAllReadResponse:
    """Mark all unread notifications for the calling user as read."""
    async with timing_floor(floor_ms=25.0):
        marked = await svc.mark_all_read(session, caller)
        return MarkAllReadResponse(marked=marked)
