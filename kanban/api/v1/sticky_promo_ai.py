# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API endpoints for Sticky -> Doc AI structuring preview (KB-P5-26, S8.2)."""

from __future__ import annotations

import importlib
import uuid  # noqa: TC003  # Required at runtime by FastAPI path parameter parsing
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ObjectRecord, ResourceAclEntry, Sticky
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException, not_found
from kanban.api.timing import timing_floor
from kanban.api.v1.schemas.stickies import StickyPromotePreviewResponse
from kanban.security.access_manifest import build_access_manifest
from kanban.security.permissions import Capability, require_capability

router = APIRouter(tags=["stickies-ai"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]

_MAX_STICKY_BYTES: int = 131_072  # 128 KiB cap


def _get_structurer_and_router(
    request: Request,
    workspace_id: uuid.UUID,
) -> tuple[Any, Any]:
    """Dynamically resolve structuring pipeline and router without violating module layers."""
    custom_structurer = getattr(request.app.state, "sticky_structurer", None)
    if custom_structurer is not None:
        return custom_structurer, None

    structurer_mod = importlib.import_module("agent.sticky_promo.structurer")
    structure_fn = structurer_mod.structure_sticky_to_doc_proposal

    app_router = getattr(request.app.state, "provider_router", None)
    if app_router is not None:
        return structure_fn, app_router

    router_mod = importlib.import_module("agent.providers.router")
    provider_router_cls = router_mod.ProviderRouter
    candidates = getattr(request.app.state, "sparkle_route_candidates", ())
    air_gap = getattr(request.app.state, "air_gap_mode", False)
    router_inst = provider_router_cls(
        workspace_id=workspace_id,
        candidates=candidates,
        air_gap_mode=air_gap,
    )
    return structure_fn, router_inst


@router.post(
    "/stickies/{sticky_id}/promote-preview",
    status_code=200,
    response_model=StickyPromotePreviewResponse,
    summary="Preview AI-structured Doc proposal for a sticky scratchpad",
)
async def preview_sticky_promotion(
    sticky_id: uuid.UUID,
    request: Request,
    caller: Caller,
    session: Session,
) -> StickyPromotePreviewResponse:
    """Generate read-only preview of an AI-structured Doc proposal without writing database rows."""
    async with timing_floor(floor_ms=25.0):
        # 1. Fetch sticky and verify workspace scope
        stmt = (
            select(Sticky, ObjectRecord)
            .join(ObjectRecord, ObjectRecord.id == Sticky.id)
            .where(
                Sticky.id == sticky_id,
                Sticky.workspace_id == caller.workspace_id,
                ObjectRecord.deleted_at.is_(None),
            )
        )
        row = (await session.execute(stmt)).first()
        if row is None:
            not_found()

        sticky, _ = row

        # 2. Permission checks: must have VIEW and EDIT on the sticky
        await require_capability(session, caller, sticky.id, Capability.VIEW)
        await require_capability(session, caller, sticky.id, Capability.EDIT)

        # 3. Status checks: already promoted or oversized
        if sticky.promoted_to_doc_id is not None:
            raise ProblemException(
                code="ALREADY_PROMOTED",
                status=409,
                title="Sticky Already Promoted",
                detail="This sticky has already been promoted to a document",
            )

        raw_bytes = sticky.body_markdown.encode("utf-8")
        if len(raw_bytes) > _MAX_STICKY_BYTES:
            msg = f"Sticky body ({len(raw_bytes)} bytes) exceeds cap of {_MAX_STICKY_BYTES} bytes"
            raise ProblemException(
                code="STICKY_TOO_LARGE",
                status=413,
                title="Sticky Too Large",
                detail=msg,
            )

        # 4. Read-only ACL preview: access manifest + direct entries count
        manifest = await build_access_manifest(session, caller, sticky.id)
        direct_acls_stmt = select(ResourceAclEntry).where(ResourceAclEntry.object_id == sticky.id)
        direct_acls = (await session.execute(direct_acls_stmt)).scalars().all()
        acl_preview: dict[str, Any] = {
            "manifest": manifest.model_dump(),
            "direct_entries_count": len(direct_acls),
            "will_copy_verbatim": True,
        }

        # 5. Invoke AI structuring pipeline
        structure_fn, router_inst = _get_structurer_and_router(request, caller.workspace_id)
        if router_inst is not None:
            res = await structure_fn(
                body_markdown=sticky.body_markdown,
                router=router_inst,
                caller_workspace_id=caller.workspace_id,
                caller_project_id=sticky.project_id,
            )
        else:
            res = await structure_fn(
                body_markdown=sticky.body_markdown,
                caller_workspace_id=caller.workspace_id,
                caller_project_id=sticky.project_id,
            )

        # Invariant: Zero writes executed (only return computed proposal and preview)
        sha_hex = (
            sticky.body_sha256.hex()
            if isinstance(sticky.body_sha256, (bytes, bytearray, memoryview))
            else str(sticky.body_sha256)
        )
        return StickyPromotePreviewResponse(
            proposal=res.proposal.model_dump(),
            rendered_markdown=res.rendered_markdown,
            original_sha256=sha_hex,
            warnings=res.warnings,
            acl_preview=acl_preview,
        )
