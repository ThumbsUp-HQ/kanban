"""Typed object links, canonical URL helper, and restricted-target masking endpoints.

Traceability: Spec S7.2 8m, S12.1.
"""

from __future__ import annotations

import uuid  # noqa: TC003
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from kanban.api.deps import PrincipalContext, get_principal, get_rls_session, get_settings
from kanban.api.problems import not_found
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.links import (
    CanonicalUrlResponse,
    LinkCreateRequest,
    LinksListResponse,
    OutboundLinkOut,
)
from kanban.security.permissions import Capability, evaluate_capabilities
from kanban.services.links import (
    build_canonical_url,
    create_object_link,
    delete_object_link,
    list_object_links,
)
from kanban.services.object_ref import resolve_object_ref
from kanban.settings import Settings  # noqa: TC001

__all__ = ["router"]

router: Final[APIRouter] = APIRouter(tags=["links"])


@router.get(
    "/objects/{object_ref}/links",
    response_model=LinksListResponse,
    summary="List inbound and outbound typed object links with restricted-target masking",
)
async def get_object_links_endpoint(
    object_ref: str,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> LinksListResponse:
    """List directed links for an object, masking unreadable far endpoints."""
    async with timing_floor(floor_ms=25.0):
        obj = await resolve_object_ref(session, object_ref)
        if obj is None:
            not_found()

        caps = await evaluate_capabilities(session, caller, obj.id)
        if Capability.VIEW not in caps:
            not_found()

        return await list_object_links(session, caller, obj)


@router.post(
    "/objects/{object_ref}/links",
    response_model=OutboundLinkOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a directed typed object link",
)
async def create_object_link_endpoint(
    object_ref: str,
    req: LinkCreateRequest,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> OutboundLinkOut:
    """Validate and insert a typed link between two Universal Object Graph nodes."""
    async with timing_floor(floor_ms=25.0):
        source = await resolve_object_ref(session, object_ref)
        if source is None:
            not_found()

        return await create_object_link(session, caller, source, req)


@router.delete(
    "/links/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a typed object link",
)
async def delete_object_link_endpoint(
    link_id: uuid.UUID,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> Response:
    """Delete an object link with anti-enumeration protection on unreadable sources."""
    async with timing_floor(floor_ms=25.0):
        await delete_object_link(session, caller, link_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/objects/{object_ref}/canonical-url",
    response_model=CanonicalUrlResponse,
    summary="Get server-authoritative canonical URL and safe Markdown link",
)
async def get_canonical_url_endpoint(
    object_ref: str,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CanonicalUrlResponse:
    """Generate canonical URL and escaped Markdown link using settings.public_base_url."""
    async with timing_floor(floor_ms=25.0):
        obj = await resolve_object_ref(session, object_ref)
        if obj is None:
            not_found()

        caps = await evaluate_capabilities(session, caller, obj.id)
        if Capability.VIEW not in caps:
            not_found()

        return build_canonical_url(settings, obj)
