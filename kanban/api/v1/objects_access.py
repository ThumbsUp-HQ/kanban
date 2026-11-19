"""Object access manifest and agent kill-switch endpoints (S3.4)."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import exists, select, text
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from database.models import EffectiveResourceAccess, ObjectRecord, Principal, ResourceAclEntry
from kanban.admin import acl_service, principal_service
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException, not_found
from kanban.api.timing import timing_floor
from kanban.security.access_manifest import AccessManifest, build_access_manifest
from kanban.security.permissions import Capability, evaluate_capabilities
from kanban.services.object_ref import resolve_object_ref

router = APIRouter(prefix="/objects", tags=["objects-access"])


@router.get(
    "/{object_id}/access",
    response_model=AccessManifest,
    summary="Get anti-enumeration access manifest for an object",
)
async def get_object_access_manifest(
    object_id: str,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> AccessManifest:
    """Retrieve structured access sharing metadata for an object under S3.4 rules."""
    async with timing_floor(floor_ms=25.0):
        obj = await resolve_object_ref(session, object_id)
        if obj is None:
            not_found()
        return await build_access_manifest(session, caller, obj.id)


@router.post(
    "/{object_id}/access/agent-kill-switch",
    response_model=AccessManifest,
    summary="Revoke access for all automated agents on an object",
)
async def agent_kill_switch(
    object_id: str,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> AccessManifest:
    """Instantly revoke access for all active agents on an object by upserting DENY Capability.ALL.

    Requires Capability.SHARE or Capability.ADMIN on the target object.
    Appends an immutable AGENT_ACCESS_KILLED entry to the activity ledger and returns
    the refreshed AccessManifest.
    """
    resolved_obj = await resolve_object_ref(session, object_id)
    if resolved_obj is None:
        not_found()
    resolved_id = resolved_obj.id

    # 1. Require SHARE or ADMIN capability on object
    caps = await evaluate_capabilities(session, caller, resolved_id)
    if Capability.VIEW not in caps:
        not_found()

    has_kill_privilege = (Capability.SHARE in caps) or (Capability.ADMIN in caps)
    if not has_kill_privilege:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail=None,
        )

    # 2. Fetch object record
    object_rec = await session.get(ObjectRecord, resolved_id)
    if object_rec is None:
        not_found()

    # 3. Find all active agents holding access on object
    agent_types = ("AGENT", "SERVICE_PRINCIPAL")
    era_has_access = exists().where(
        EffectiveResourceAccess.object_id == resolved_id,
        EffectiveResourceAccess.principal_id == Principal.id,
        EffectiveResourceAccess.allow_mask > 0,
    )

    stmt = select(Principal.id).where(
        Principal.workspace_id == object_rec.workspace_id,
        Principal.status == "ACTIVE",
        Principal.principal_type.in_(agent_types),
        era_has_access,
    )
    killed_ids = list((await session.execute(stmt)).scalars().all())

    # Include agents with direct ALLOW ACLs on object
    acl_stmt = (
        select(ResourceAclEntry.principal_id)
        .join(Principal, Principal.id == ResourceAclEntry.principal_id)
        .where(
            ResourceAclEntry.object_id == resolved_id,
            ResourceAclEntry.effect == "ALLOW",
            Principal.status == "ACTIVE",
            Principal.principal_type.in_(agent_types),
        )
    )
    for p_id in (await session.execute(acl_stmt)).scalars().all():
        if p_id not in killed_ids:
            killed_ids.append(p_id)

    # 4. Upsert explicit DENY ALL on object for each agent
    for agent_id in killed_ids:
        await session.execute(
            text("""
                INSERT INTO resource_acl_entries (
                    workspace_id, object_id, principal_id, effect, capability_mask, created_by_id
                ) VALUES (
                    :ws_id, :obj_id, :agent_id, 'DENY', 255, :caller_id
                )
                ON CONFLICT (object_id, principal_id, effect)
                DO UPDATE SET capability_mask = 255, created_by_id = :caller_id
            """),
            {
                "ws_id": object_rec.workspace_id,
                "obj_id": resolved_id,
                "agent_id": agent_id,
                "caller_id": caller.principal_id,
            },
        )

    # 5. Rebuild effective resource access for workspace
    await session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws_id)"),
        {"ws_id": object_rec.workspace_id},
    )

    # 6. Append immutable activity ledger record
    payload = json.dumps(
        {
            "killed_agent_ids": [str(a) for a in killed_ids],
            "object_id": str(resolved_id),
        }
    )
    await session.execute(
        text("""
            SELECT append_activity(
                :ws_id,
                :obj_id,
                CAST(:obj_type AS object_kind),
                :caller_id,
                'AGENT_ACCESS_KILLED',
                CAST(:payload AS jsonb)
            )
        """),
        {
            "ws_id": object_rec.workspace_id,
            "obj_id": resolved_id,
            "obj_type": (
                object_rec.object_type.value
                if hasattr(object_rec.object_type, "value")
                else str(object_rec.object_type)
            ),
            "caller_id": caller.principal_id,
            "payload": payload,
        },
    )

    await session.flush()

    # 7. Return refreshed AccessManifest
    return await build_access_manifest(session, caller, resolved_id)


class ObjectAclGrantRequest(BaseModel):
    """Payload for granting or replacing an object capability ACL entry."""

    model_config = ConfigDict(extra="forbid")

    principal_id: str = Field(description="Subject principal UUID or handle")
    effect: Literal["ALLOW", "DENY"] = Field(description="ALLOW or DENY")
    capabilities: list[str] = Field(min_length=1, max_length=8, description="Capability tokens")


class ObjectAclRevokeRequest(BaseModel):
    """Payload for revoking an object capability ACL entry."""

    model_config = ConfigDict(extra="forbid")

    principal_id: str = Field(description="Subject principal UUID or handle")
    effect: Literal["ALLOW", "DENY"] = Field(description="ALLOW or DENY")


@router.post(
    "/{object_id}/access/entries",
    response_model=AccessManifest,
    summary="Grant or replace ACL entry on an object",
)
async def grant_object_acl_entry(
    object_id: str,
    body: ObjectAclGrantRequest,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> AccessManifest:
    """Grant or replace an ALLOW or DENY capability access control entry on target object.

    Requires Capability.SHARE or Capability.ADMIN on the target object.
    """
    async with timing_floor(floor_ms=25.0):
        resolved_obj = await resolve_object_ref(session, object_id)
        if resolved_obj is None:
            not_found()
        caps = await evaluate_capabilities(session, caller, resolved_obj.id)
        if Capability.VIEW not in caps:
            not_found()
        if Capability.SHARE not in caps and Capability.ADMIN not in caps:
            raise ProblemException(
                code="INSUFFICIENT_CAPABILITY",
                status=403,
                title="Insufficient Capability",
                detail="Operation requires SHARE or ADMIN capability on the target object.",
            )
        await acl_service.grant_acl_entry(
            session,
            caller.workspace_id,
            caller,
            object_id=resolved_obj.id,
            principal_id=body.principal_id,
            effect=body.effect,
            capabilities=body.capabilities,
        )
        return await build_access_manifest(session, caller, resolved_obj.id)


@router.delete(
    "/{object_id}/access/entries",
    response_model=AccessManifest,
    summary="Revoke ACL entry on an object",
)
async def revoke_object_acl_entry(
    object_id: str,
    body: ObjectAclRevokeRequest,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> AccessManifest:
    """Revoke an explicit ALLOW or DENY capability access control entry on target object.

    Requires Capability.SHARE or Capability.ADMIN on the target object.
    """
    async with timing_floor(floor_ms=25.0):
        resolved_obj = await resolve_object_ref(session, object_id)
        if resolved_obj is None:
            not_found()
        caps = await evaluate_capabilities(session, caller, resolved_obj.id)
        if Capability.VIEW not in caps:
            not_found()
        if Capability.SHARE not in caps and Capability.ADMIN not in caps:
            raise ProblemException(
                code="INSUFFICIENT_CAPABILITY",
                status=403,
                title="Insufficient Capability",
                detail="Operation requires SHARE or ADMIN capability on the target object.",
            )
        await acl_service.revoke_acl_entry(
            session,
            caller.workspace_id,
            caller,
            object_id=resolved_obj.id,
            principal_id=body.principal_id,
            effect=body.effect,
        )
        return await build_access_manifest(session, caller, resolved_obj.id)


@router.get(
    "/{object_id}/access/principals",
    summary="Search workspace principals eligible for object ACL assignment",
)
async def list_object_acl_principals(  # noqa: PLR0913, PLR0917
    object_id: str,
    caller: Annotated[PrincipalContext, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    q: Annotated[str, Query(description="Search filter substring")] = "",
    type_filter: Annotated[str | None, Query(alias="type")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, object]]:
    """List searchable workspace principals (Users, Groups, Agents) for managing access."""
    async with timing_floor(floor_ms=25.0):
        resolved_obj = await resolve_object_ref(session, object_id)
        if resolved_obj is None:
            not_found()
        caps = await evaluate_capabilities(session, caller, resolved_obj.id)
        if Capability.VIEW not in caps:
            not_found()
        if Capability.SHARE not in caps and Capability.ADMIN not in caps:
            raise ProblemException(
                code="INSUFFICIENT_CAPABILITY",
                status=403,
                title="Insufficient Capability",
                detail="Operation requires SHARE or ADMIN capability on the target object.",
            )
        clean_filter = type_filter.strip() if type_filter and type_filter.strip() else None
        if clean_filter and clean_filter.upper() == "ALL":
            clean_filter = None
        all_principals = await principal_service.list_principals(
            session,
            caller.workspace_id,
            filter_type=clean_filter,
            limit=limit,
        )
        if not q.strip():
            return all_principals
        query_norm = q.strip().lower()
        return [
            p
            for p in all_principals
            if query_norm in str(p.get("display_name", "")).lower()
            or query_norm in str(p.get("handle", "")).lower()
            or query_norm in str(p.get("name", "")).lower()
        ]
