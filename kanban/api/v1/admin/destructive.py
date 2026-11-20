# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for two-stage destructive lifecycle operations (KB-P4-12, S11.4)."""

from __future__ import annotations

import uuid  # noqa: TC003
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.base import ObjectKind
from database.models.spine import ObjectRecord, Workspace
from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.api.problems import not_found
from kanban.api.v1.schemas.issue_delete import TrashedObjectItem, TrashedObjectList
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.security.permissions import (
    Capability,
    capabilities_to_names,
    evaluate_capabilities,
)
from kanban.services.destructive_lifecycle import (
    execute_delete,
    request_delete,
    restore_object,
)

__all__ = [
    "DestructiveExecuteIn",
    "DestructiveExecuteOut",
    "DestructiveRequestIn",
    "DestructiveRequestOut",
    "DestructiveRestoreIn",
    "DestructiveRestoreOut",
    "api_admin_list_trash",
    "api_admin_restore_by_id",
    "router",
]

router = APIRouter(tags=["admin-destructive"], dependencies=[Depends(require_admin_aal2)])

Caller = Annotated[PrincipalContext, Depends(require_admin_aal2)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]

TargetKindLiteral = Literal["issue", "project", "doc", "page", "sticky", "cycle", "module", "view"]
ModeLiteral = Literal["trash", "permanent_purge"]


class DestructiveRequestIn(BaseModel):
    """Payload for Stage 1 delete request."""

    model_config = ConfigDict(extra="forbid")

    target_kind: TargetKindLiteral
    target: str = Field(min_length=1, max_length=200)
    mode: ModeLiteral = "trash"


class DestructiveRequestOut(BaseModel):
    """Response returned by Stage 1 delete request."""

    model_config = ConfigDict(extra="ignore")

    stage: str
    target: str
    target_kind: str
    target_id: str
    mode: str
    blast_summary: str
    blast_hash: str
    confirm_phrase: str
    confirmation_token: str
    expires_in_sec: int


class DestructiveExecuteIn(BaseModel):
    """Payload for Stage 2 delete execution."""

    model_config = ConfigDict(extra="forbid")

    target_kind: TargetKindLiteral
    target: str = Field(min_length=1, max_length=200)
    mode: ModeLiteral
    confirmation_token: str = Field(min_length=1)
    confirm_phrase: str = Field(min_length=1)
    reason: str = Field(min_length=10, max_length=500)


class DestructiveExecuteOut(BaseModel):
    """Response returned by Stage 2 delete execution."""

    model_config = ConfigDict(extra="ignore")

    status: str
    target: str
    target_kind: str
    target_id: str
    mode: str
    reason: str
    blast_hash: str


class DestructiveRestoreIn(BaseModel):
    """Payload for restore operation."""

    model_config = ConfigDict(extra="forbid")

    target_kind: TargetKindLiteral
    target: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=10, max_length=500)


class DestructiveRestoreOut(BaseModel):
    """Response returned by restore operation."""

    model_config = ConfigDict(extra="ignore")

    status: str
    target: str
    target_kind: str
    target_id: str
    reason: str


@router.post(
    "/admin/destructive:request",
    response_model=DestructiveRequestOut,
    status_code=status.HTTP_200_OK,
    summary="Stage 1: Request destructive delete and mint confirmation token",
)
async def api_destructive_request(
    payload: DestructiveRequestIn,
    caller: Caller,
    session: Session,
) -> DestructiveRequestOut:
    """Compute blast radius and issue a single-use 5m confirmation token."""
    res = await request_delete(
        session=session,
        caller=caller,
        target_kind=payload.target_kind,
        target_ref=payload.target,
        mode=payload.mode,
    )
    return DestructiveRequestOut(
        stage=res.stage,
        target=res.target,
        target_kind=res.target_kind,
        target_id=res.target_id,
        mode=res.mode,
        blast_summary=res.blast_summary,
        blast_hash=res.blast_hash,
        confirm_phrase=res.confirm_phrase,
        confirmation_token=res.confirmation_token,
        expires_in_sec=res.expires_in_sec,
    )


@router.post(
    "/admin/destructive:execute",
    response_model=DestructiveExecuteOut,
    status_code=status.HTTP_200_OK,
    summary="Stage 2: Execute destructive delete with confirmation token",
)
async def api_destructive_execute(
    payload: DestructiveExecuteIn,
    caller: Caller,
    session: Session,
) -> DestructiveExecuteOut:
    """Verify confirmation token and blast hash, then execute soft-trash or permanent purge."""
    res = await execute_delete(
        session=session,
        caller=caller,
        target_kind=payload.target_kind,
        target_ref=payload.target,
        mode=payload.mode,
        confirmation_token=payload.confirmation_token,
        confirm_phrase=payload.confirm_phrase,
        reason=payload.reason,
    )
    return DestructiveExecuteOut(
        status=res.status,
        target=res.target,
        target_kind=res.target_kind,
        target_id=res.target_id,
        mode=res.mode,
        reason=res.reason,
        blast_hash=res.blast_hash,
    )


@router.post(
    "/admin/destructive:restore",
    response_model=DestructiveRestoreOut,
    status_code=status.HTTP_200_OK,
    summary="Restore a soft-deleted object from trash",
)
async def api_destructive_restore(
    payload: DestructiveRestoreIn,
    caller: Caller,
    session: Session,
) -> DestructiveRestoreOut:
    """Restore a soft-deleted entity from trash back to active state."""
    res = await restore_object(
        session=session,
        caller=caller,
        target_kind=payload.target_kind,
        target_ref=payload.target,
        reason=payload.reason,
    )
    return DestructiveRestoreOut(
        status=res.status,
        target=res.target,
        target_kind=res.target_kind,
        target_id=res.target_id,
        reason=res.reason,
    )


@router.get(
    "/admin/trash",
    response_model=TrashedObjectList,
    status_code=status.HTTP_200_OK,
    summary="List soft-trashed objects in workspace",
)
async def api_admin_list_trash(  # noqa: C901, PLR0912
    caller: Caller,
    session: Session,
    kind: Annotated[
        str,
        Query(description="Filter by kind: all, project, issue, doc, page, sticky, cycle, module"),
    ] = "all",
    project_id: Annotated[uuid.UUID | None, Query(description="Filter by project ID")] = None,
    q: Annotated[str | None, Query(description="Search term for title or key")] = None,
) -> TrashedObjectList:
    """List soft-trashed objects in caller's workspace.

    Protected by require_admin_aal2.
    Filtered strictly through RLSContext and evaluate_capabilities so restricted private
    items with an explicit ACL DENY are never leaked to Workspace Admins,
    and Project Admins see only items from projects they administer.
    """
    # 1. Determine admin scope (Server Admin, Workspace Admin, or Project Admin)
    is_server_admin = bool(
        (
            await session.execute(
                text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
            )
        ).scalar_one()
    )
    is_workspace_admin = bool(
        (
            await session.execute(
                text("SELECT app_principal_has_role(NULL, ARRAY['WORKSPACE_ADMIN'])")
            )
        ).scalar_one()
    )

    admin_project_ids: set[uuid.UUID] = set()
    if not is_server_admin and not is_workspace_admin:
        # Caller is a PROJECT_ADMIN only
        proj_res = await session.execute(
            text(
                "SELECT project_id FROM role_bindings "
                "WHERE principal_id = :p_id AND role = 'PROJECT_ADMIN' AND scope_type = 'project' "
                "  AND workspace_id = :ws_id AND project_id IS NOT NULL"
            ),
            {"p_id": caller.principal_id, "ws_id": caller.workspace_id},
        )
        admin_project_ids = set(proj_res.scalars().all())
        if not admin_project_ids:
            return TrashedObjectList(items=[], retention_days=30, total=0)

    # 2. Query workspace retention
    ws = await session.get(Workspace, caller.workspace_id)
    retention_days = (ws.trash_retention_days if ws and ws.trash_retention_days else None) or 30
    now_ts = datetime.now(UTC)

    # 3. Build query on ObjectRecord
    stmt = select(ObjectRecord).where(
        ObjectRecord.workspace_id == caller.workspace_id,
        ObjectRecord.deleted_at.is_not(None),
    )

    if not is_server_admin and not is_workspace_admin:
        stmt = stmt.where(
            (ObjectRecord.project_id.in_(admin_project_ids))
            | (ObjectRecord.id.in_(admin_project_ids))
        )

    if project_id is not None:
        if not is_server_admin and not is_workspace_admin and project_id not in admin_project_ids:
            return TrashedObjectList(items=[], retention_days=retention_days, total=0)
        stmt = stmt.where((ObjectRecord.project_id == project_id) | (ObjectRecord.id == project_id))

    kind_clean = kind.lower().strip() if kind else "all"
    if kind_clean != "all":
        matching_kinds = [k for k in ObjectKind if k.value.lower() == kind_clean]
        if matching_kinds:
            stmt = stmt.where(ObjectRecord.object_type == matching_kinds[0])
        else:
            return TrashedObjectList(items=[], retention_days=retention_days, total=0)

    if q and q.strip():
        search_pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            (ObjectRecord.canonical_key.ilike(search_pattern))
            | (ObjectRecord.display_title.ilike(search_pattern))
        )

    stmt = stmt.order_by(ObjectRecord.deleted_at.desc()).limit(500)
    rows = (await session.execute(stmt)).scalars().all()

    # 4. Strict capability filter: Capability.VIEW and (Capability.DELETE or Capability.ADMIN)
    items: list[TrashedObjectItem] = []
    for obj in rows:
        if obj.deleted_at is None:
            continue
        caps = await evaluate_capabilities(session, caller, obj.id)
        if Capability.VIEW not in caps:
            continue
        if Capability.DELETE not in caps and Capability.ADMIN not in caps:
            continue

        purge_after = obj.deleted_at + timedelta(days=retention_days)
        remaining_sec = (purge_after - now_ts).total_seconds()
        remaining_days = max(0, int(remaining_sec // 86400))

        items.append(
            TrashedObjectItem(
                id=obj.id,
                key=obj.canonical_key or str(obj.id),
                kind=obj.object_type.value.lower(),
                title=obj.display_title or obj.canonical_key or str(obj.id),
                deleted_at=obj.deleted_at,
                purge_after=purge_after,
                remaining_days=remaining_days,
                capabilities=capabilities_to_names(caps),
                project_id=obj.project_id,
            )
        )

    return TrashedObjectList(items=items, retention_days=retention_days, total=len(items))


@router.post(
    "/admin/trash/{target_id}:restore",
    response_model=DestructiveRestoreOut,
    status_code=status.HTTP_200_OK,
    summary="Restore a soft-deleted object from trash by ID",
)
async def api_admin_restore_by_id(
    target_id: uuid.UUID,
    caller: Caller,
    session: Session,
    reason: Annotated[str, Query(min_length=10, max_length=500)] = "Restored from trash studio",
) -> DestructiveRestoreOut:
    """Restore soft-deleted object by UUID."""
    obj = await session.get(ObjectRecord, target_id)
    if obj is None:
        not_found()
    kind = obj.object_type.value.lower()
    res = await restore_object(
        session=session,
        caller=caller,
        target_kind=kind,
        target_ref=str(target_id),
        reason=reason,
    )
    return DestructiveRestoreOut(
        status=res.status,
        target=res.target,
        target_kind=res.target_kind,
        target_id=res.target_id,
        reason=res.reason,
    )
