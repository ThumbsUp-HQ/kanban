"""Typed object links, canonical URL helper, and restricted-target masking endpoints.

Traceability: Spec S7.2 8m, S12.1.
"""

from __future__ import annotations

import uuid  # noqa: TC003
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from database.models import ObjectRecord
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session, get_settings
from kanban.api.problems import not_found
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.links import (
    CanonicalUrlResponse,
    DirectLinkCreateRequest,
    LinkCreateRequest,
    LinksListResponse,
    OutboundLinkOut,
    UnrestrictedEndpointOut,
)
from kanban.security.permissions import Capability, evaluate_capabilities
from kanban.security.read_taint import (
    TaintGuard,
    TaintRecorder,
    get_taint_guard,
    get_taint_recorder,
)
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
    taint_recorder: Annotated[TaintRecorder, Depends(get_taint_recorder)],
) -> LinksListResponse:
    """List directed links for an object, masking unreadable far endpoints."""
    async with timing_floor(floor_ms=25.0):
        obj = await resolve_object_ref(session, object_ref)
        if obj is None:
            not_found()

        caps = await evaluate_capabilities(session, caller, obj.id)
        if Capability.VIEW not in caps:
            not_found()

        links_res = await list_object_links(session, caller, obj)
        proj_ids: set[uuid.UUID] = set()
        if obj.project_id:
            proj_ids.add(obj.project_id)
        elif obj.object_type.value == "project":
            proj_ids.add(obj.id)

        visible_ids = {
            link.target.id
            for link in links_res.outbound
            if isinstance(link.target, UnrestrictedEndpointOut)
        } | {
            link.source.id
            for link in links_res.inbound
            if isinstance(link.source, UnrestrictedEndpointOut)
        }
        if visible_ids:
            stmt = select(ObjectRecord.id, ObjectRecord.project_id, ObjectRecord.object_type).where(
                ObjectRecord.id.in_(visible_ids)
            )
            for r in (await session.execute(stmt)).all():
                if r[1]:
                    proj_ids.add(r[1])
                elif r[2].value == "project":
                    proj_ids.add(r[0])
        if proj_ids:
            await taint_recorder.record_project_ids(proj_ids)
        return links_res


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
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
) -> OutboundLinkOut:
    """Validate and insert a typed link between two Universal Object Graph nodes."""
    async with timing_floor(floor_ms=25.0):
        source = await resolve_object_ref(session, object_ref)
        if source is None:
            not_found()

        target = await resolve_object_ref(session, req.target)
        source_proj = source.project_id or (
            source.id if source.object_type.value == "project" else None
        )
        target_proj = (target.project_id if target else None) or (
            target.id if (target and target.object_type.value == "project") else None
        )
        check_projs = [p for p in (source_proj, target_proj) if p is not None]
        if check_projs:
            await taint_guard.check_write(check_projs, tool_name="link_objects")

        return await create_object_link(session, caller, source, req)


@router.post(
    "/links",
    response_model=OutboundLinkOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a typed link between source and target objects",
)
async def create_link_direct(
    req: DirectLinkCreateRequest,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    taint_guard: Annotated[TaintGuard, Depends(get_taint_guard)],
) -> OutboundLinkOut:
    """Create an object link using source and target identifiers in request body."""
    async with timing_floor(floor_ms=25.0):
        source = await resolve_object_ref(session, req.source_id)
        if source is None:
            not_found()

        target = await resolve_object_ref(session, req.target_id)
        source_proj = source.project_id or (
            source.id if source.object_type.value == "project" else None
        )
        target_proj = (target.project_id if target else None) or (
            target.id if (target and target.object_type.value == "project") else None
        )
        check_projs = [p for p in (source_proj, target_proj) if p is not None]
        if check_projs:
            await taint_guard.check_write(check_projs, tool_name="link_objects")

        return await create_object_link(
            session,
            caller,
            source,
            LinkCreateRequest(target=req.target_id, link_type=req.link_type),
        )


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
