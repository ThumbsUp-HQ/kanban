# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Issue subscriptions API endpoints (S7.2 8l, S3.4; KB-P3-06)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession  # Required by FastAPI dependency injection

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.notifications import (
    SubscriptionPatch,
    SubscriptionPut,
    SubscriptionResponse,
)
from kanban.services import subscriptions as svc

router = APIRouter(tags=["subscriptions"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


@router.get(
    "/issues/{issue_ref}/subscription",
    status_code=200,
    response_model=SubscriptionResponse,
    summary="Get subscription status for an issue",
)
async def get_subscription(
    issue_ref: str,
    caller: Caller,
    session: Session,
) -> SubscriptionResponse:
    """Return the caller's subscription status and muted event types for an issue."""
    return await svc.get_subscription(session, caller, issue_ref)


@router.put(
    "/issues/{issue_ref}/subscription",
    status_code=200,
    response_model=SubscriptionResponse,
    summary="Subscribe to an issue",
)
async def subscribe_issue(
    issue_ref: str,
    caller: Caller,
    session: Session,
    body: SubscriptionPut | None = None,
) -> SubscriptionResponse:
    """Idempotently subscribe the caller to an issue (VIEW required)."""
    async with timing_floor(floor_ms=25.0):
        return await svc.subscribe_issue(session, caller, issue_ref, body)


@router.patch(
    "/issues/{issue_ref}/subscription",
    status_code=200,
    response_model=SubscriptionResponse,
    summary="Update muted event types for an issue subscription",
)
async def patch_subscription(
    issue_ref: str,
    body: SubscriptionPatch,
    caller: Caller,
    session: Session,
) -> SubscriptionResponse:
    """Update the caller's muted event types on an active subscription (VIEW required)."""
    async with timing_floor(floor_ms=25.0):
        return await svc.patch_subscription(session, caller, issue_ref, body)


@router.delete(
    "/issues/{issue_ref}/subscription",
    status_code=204,
    summary="Unsubscribe from an issue",
)
async def unsubscribe_issue(
    issue_ref: str,
    caller: Caller,
    session: Session,
) -> Response:
    """Idempotently unsubscribe the caller from an issue with a tombstone (VIEW required)."""
    async with timing_floor(floor_ms=25.0):
        await svc.unsubscribe_issue(session, caller, issue_ref)
        return Response(status_code=204)
