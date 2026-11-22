# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for administrative outbound webhook management (KB-DEVSECOPS-BUS-01)."""

from __future__ import annotations

import logging
import secrets
import urllib.parse
import uuid
from datetime import datetime  # noqa: TC003
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.webhooks import WebhookDelivery, WebhookSubscription
from database.models.workspace_settings import WorkspaceSettings
from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.api.problems import ProblemException, not_found
from kanban.api.timing import timing_floor
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.security.envelope import KekProvider, StaticKekProvider, seal_bound
from kanban.security.ssrf import SSRFBlockedError, resolve_and_select_pinned_ip

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/webhooks",
    tags=["admin-webhooks"],
    dependencies=[Depends(require_admin_aal2)],
)

Caller = Annotated[PrincipalContext, Depends(require_admin_aal2)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


def _get_kek(request: Request) -> KekProvider:
    """Retrieve KEK provider from app state or return fallback."""
    kek: KekProvider | None = getattr(request.app.state, "kek_provider", None)
    if kek is not None:
        return kek
    key_material = getattr(request.app.state, "key_material", None)
    if key_material is not None:
        fallback = StaticKekProvider(
            {key_material.master_kek_kid: key_material.master_kek},
            current=key_material.master_kek_kid,
        )
    else:
        fallback = StaticKekProvider({"kek-v1": b"k" * 32}, current="kek-v1")
    request.app.state.kek_provider = fallback
    return fallback


class WebhookSubscriptionCreateRequest(BaseModel):
    """Request payload to create a new outbound webhook subscription."""

    model_config = ConfigDict(extra="forbid")

    target_url: str = Field(max_length=2048, description="Target HTTP/HTTPS webhook URL")
    events: list[str] = Field(
        min_length=1,
        description="List of event topic patterns to subscribe to",
    )
    project_id: uuid.UUID | None = Field(default=None, description="Optional scoped project ID")
    secret: str | None = Field(default=None, max_length=256, description="Optional signing secret")
    is_active: bool = Field(default=True, description="Whether subscription is enabled")


class WebhookSubscriptionUpdateRequest(BaseModel):
    """Request payload to update an existing outbound webhook subscription."""

    model_config = ConfigDict(extra="forbid")

    target_url: str | None = Field(default=None, max_length=2048)
    events: list[str] | None = Field(default=None, min_length=1)
    project_id: uuid.UUID | None = None
    secret: str | None = Field(default=None, max_length=256)
    is_active: bool | None = None


class WebhookSubscriptionResponse(BaseModel):
    """Response representing an outbound webhook subscription."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    target_url: str
    events: list[str]
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    secret: str | None = None


class WebhookDeliveryResponse(BaseModel):
    """Response representing an outbound webhook delivery attempt."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    workspace_id: uuid.UUID
    subscription_id: uuid.UUID
    event_id: uuid.UUID | None
    event_topic: str
    payload_json: dict[str, Any]
    attempt_count: int
    status: str
    status_code: int | None
    error_message: str | None
    created_at: datetime
    delivered_at: datetime | None


async def _validate_target_url(
    target_url: str,
    workspace_id: uuid.UUID,
    session: AsyncSession,
    request: Request,
) -> None:
    """Validate target URL scheme, air gap policy, and SSRF restrictions."""
    parsed = urllib.parse.urlsplit(target_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ProblemException(
            code="INVALID_TARGET_URL",
            status=400,
            title="Invalid Target URL",
            detail="target_url must be a valid http or https URL with a hostname",
        )

    ws_stmt = select(WorkspaceSettings.air_gap_mode).where(
        WorkspaceSettings.workspace_id == workspace_id
    )
    air_gap = (await session.execute(ws_stmt)).scalar_one_or_none() or False
    if air_gap:
        raise ProblemException(
            code="AIR_GAP_RESTRICTION",
            status=400,
            title="Air-Gap Restriction",
            detail="Outbound webhooks are disabled under air-gap mode",
        )

    dns_resolver = getattr(request.app.state, "git_dns_resolver", None)
    try:
        await resolve_and_select_pinned_ip(parsed.hostname, resolver=dns_resolver)
    except SSRFBlockedError as exc:
        raise ProblemException(
            code="SSRF_TARGET_BLOCKED",
            status=400,
            title="SSRF Target Blocked",
            detail=str(exc),
        ) from exc


@router.get(
    "",
    response_model=list[WebhookSubscriptionResponse],
    summary="List outbound webhook subscriptions",
)
async def list_subscriptions(
    caller: Caller,
    session: Session,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[WebhookSubscriptionResponse]:
    """List webhook subscriptions in the workspace."""
    async with timing_floor(floor_ms=25.0):
        stmt = select(WebhookSubscription).where(
            WebhookSubscription.workspace_id == caller.workspace_id
        )
        if project_id is not None:
            stmt = stmt.where(WebhookSubscription.project_id == project_id)
        stmt = stmt.order_by(WebhookSubscription.created_at.desc())
        rows = list((await session.execute(stmt)).scalars().all())

        return [
            WebhookSubscriptionResponse(
                id=r.id,
                workspace_id=r.workspace_id,
                project_id=r.project_id,
                target_url=r.target_url,
                events=r.events,
                is_active=r.is_active,
                created_by=r.created_by,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=WebhookSubscriptionResponse,
    summary="Create an outbound webhook subscription",
)
async def create_subscription(
    body: WebhookSubscriptionCreateRequest,
    caller: Caller,
    session: Session,
    request: Request,
) -> WebhookSubscriptionResponse:
    """Create a new outbound webhook subscription with envelope-encrypted secret."""
    async with timing_floor(floor_ms=25.0):
        await _validate_target_url(body.target_url, caller.workspace_id, session, request)

        sub_id = uuid.uuid4()
        secret_plaintext = body.secret or secrets.token_hex(24)
        kek = _get_kek(request)
        aad = f"kanban/webhook-sub/v1|{sub_id}|{caller.workspace_id}".encode()
        sealed = seal_bound(secret_plaintext.encode("utf-8"), aad, kek)
        wrapped_len = len(sealed.wrapped_dek).to_bytes(2, "big")
        secret_ct = wrapped_len + sealed.wrapped_dek + sealed.encrypted_secret_blob

        sub = WebhookSubscription(
            id=sub_id,
            workspace_id=caller.workspace_id,
            project_id=body.project_id,
            target_url=body.target_url,
            events=body.events,
            secret_ciphertext=secret_ct,
            secret_dek_kid=sealed.dek_kid,
            is_active=body.is_active,
            created_by=caller.principal_id,
        )
        session.add(sub)
        await session.flush()

        return WebhookSubscriptionResponse(
            id=sub.id,
            workspace_id=sub.workspace_id,
            project_id=sub.project_id,
            target_url=sub.target_url,
            events=sub.events,
            is_active=sub.is_active,
            created_by=sub.created_by,
            created_at=sub.created_at,
            updated_at=sub.updated_at,
            secret=secret_plaintext,
        )


@router.get(
    "/{subscription_id}",
    response_model=WebhookSubscriptionResponse,
    summary="Get an outbound webhook subscription",
)
async def get_subscription(
    subscription_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> WebhookSubscriptionResponse:
    """Get single outbound webhook subscription."""
    async with timing_floor(floor_ms=25.0):
        stmt = select(WebhookSubscription).where(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.workspace_id == caller.workspace_id,
        )
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if sub is None:
            not_found()

        return WebhookSubscriptionResponse(
            id=sub.id,
            workspace_id=sub.workspace_id,
            project_id=sub.project_id,
            target_url=sub.target_url,
            events=sub.events,
            is_active=sub.is_active,
            created_by=sub.created_by,
            created_at=sub.created_at,
            updated_at=sub.updated_at,
        )


@router.patch(
    "/{subscription_id}",
    response_model=WebhookSubscriptionResponse,
    summary="Update an outbound webhook subscription",
)
async def update_subscription(
    subscription_id: uuid.UUID,
    body: WebhookSubscriptionUpdateRequest,
    caller: Caller,
    session: Session,
    request: Request,
) -> WebhookSubscriptionResponse:
    """Update outbound webhook subscription settings."""
    async with timing_floor(floor_ms=25.0):
        stmt = select(WebhookSubscription).where(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.workspace_id == caller.workspace_id,
        )
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if sub is None:
            not_found()

        if body.target_url is not None:
            await _validate_target_url(body.target_url, caller.workspace_id, session, request)
            sub.target_url = body.target_url

        if body.events is not None:
            sub.events = body.events

        if body.project_id is not None:
            sub.project_id = body.project_id

        if body.is_active is not None:
            sub.is_active = body.is_active

        returned_secret: str | None = None
        if body.secret is not None:
            kek = _get_kek(request)
            aad = f"kanban/webhook-sub/v1|{sub.id}|{caller.workspace_id}".encode()
            sealed = seal_bound(body.secret.encode("utf-8"), aad, kek)
            wrapped_len = len(sealed.wrapped_dek).to_bytes(2, "big")
            sub.secret_ciphertext = wrapped_len + sealed.wrapped_dek + sealed.encrypted_secret_blob
            sub.secret_dek_kid = sealed.dek_kid
            returned_secret = body.secret

        await session.flush()

        return WebhookSubscriptionResponse(
            id=sub.id,
            workspace_id=sub.workspace_id,
            project_id=sub.project_id,
            target_url=sub.target_url,
            events=sub.events,
            is_active=sub.is_active,
            created_by=sub.created_by,
            created_at=sub.created_at,
            updated_at=sub.updated_at,
            secret=returned_secret,
        )


@router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an outbound webhook subscription",
)
async def delete_subscription(
    subscription_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> Response:
    """Delete an outbound webhook subscription."""
    async with timing_floor(floor_ms=25.0):
        stmt = select(WebhookSubscription).where(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.workspace_id == caller.workspace_id,
        )
        sub = (await session.execute(stmt)).scalar_one_or_none()
        if sub is None:
            not_found()

        await session.delete(sub)
        await session.flush()
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{subscription_id}/deliveries",
    response_model=list[WebhookDeliveryResponse],
    summary="List delivery attempts for a webhook subscription",
)
async def list_deliveries(
    subscription_id: uuid.UUID,
    caller: Caller,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[WebhookDeliveryResponse]:
    """List historical delivery attempts and status for subscription."""
    async with timing_floor(floor_ms=25.0):
        # Verify subscription belongs to caller workspace
        sub_stmt = select(WebhookSubscription.id).where(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.workspace_id == caller.workspace_id,
        )
        if (await session.execute(sub_stmt)).scalar_one_or_none() is None:
            not_found()

        stmt = (
            select(WebhookDelivery)
            .where(
                WebhookDelivery.subscription_id == subscription_id,
                WebhookDelivery.workspace_id == caller.workspace_id,
            )
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
        )
        rows = list((await session.execute(stmt)).scalars().all())

        return [
            WebhookDeliveryResponse(
                id=d.id,
                workspace_id=d.workspace_id,
                subscription_id=d.subscription_id,
                event_id=d.event_id,
                event_topic=d.event_topic,
                payload_json=d.payload_json,
                attempt_count=d.attempt_count,
                status=d.status,
                status_code=d.status_code,
                error_message=d.error_message,
                created_at=d.created_at,
                delivered_at=d.delivered_at,
            )
            for d in rows
        ]
