# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Access policy and ACL administration service (KB-P4-09b, S11.4, S3.2, S3.4)."""

from __future__ import annotations

import logging
import re
import uuid
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import unquote

from sqlalchemy import delete, select

from database.models.principals import (
    Principal,
    ResourceAclEntry,
)
from kanban.admin.principal_service import resolve_principal_id
from kanban.api.deps import PrincipalContext
from kanban.api.problems import FieldError, ProblemException, not_found
from kanban.security.access_manifest import AccessManifest, build_access_manifest
from kanban.security.permissions import (
    Capability,
    capabilities_to_names,
    evaluate_capabilities,
)
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.object_ref import resolve_object_ref

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_RFC4122_UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_VALID_CAPABILITIES = {
    "VIEW": Capability.VIEW,
    "COMMENT": Capability.COMMENT,
    "EDIT": Capability.EDIT,
    "TRANSITION": Capability.TRANSITION,
    "LINK": Capability.LINK,
    "SHARE": Capability.SHARE,
    "ADMIN": Capability.ADMIN,
    "DELETE": Capability.DELETE,
}


_MAX_CAPABILITIES_COUNT: Final[int] = 8


def parse_capability_mask(capabilities: list[str]) -> int:
    """Parse list of capability strings into integer bitmask."""
    if not capabilities:
        msg = "capabilities list cannot be empty"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="capabilities", message=msg)],
        )

    if len(capabilities) > _MAX_CAPABILITIES_COUNT:
        msg = f"capabilities list cannot exceed {_MAX_CAPABILITIES_COUNT} items"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="capabilities", message=msg)],
        )

    mask = 0
    for cap_name in capabilities:
        norm = cap_name.strip().upper()
        if norm not in _VALID_CAPABILITIES:
            msg = f"Invalid capability '{cap_name}'. Allowed: {sorted(_VALID_CAPABILITIES.keys())}"
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail=msg,
                errors=[FieldError(path="capabilities", message=msg)],
            )
        mask |= _VALID_CAPABILITIES[norm]
    return mask


async def resolve_target_object_id(  # noqa: RET503
    session: AsyncSession,
    workspace_id: uuid.UUID,
    object_ref: str | uuid.UUID,
) -> uuid.UUID:
    """Resolve an object reference (UUID, issue key, project identifier, or canonical key)."""
    if isinstance(object_ref, uuid.UUID):
        return object_ref
    r = unquote(str(object_ref).strip())
    if _RFC4122_UUID_REGEX.match(r):
        return uuid.UUID(r)
    obj = await resolve_object_ref(session, r)
    if obj is not None and obj.workspace_id == workspace_id:
        return obj.id
    not_found()


async def _assert_admin_on_object(
    session: AsyncSession,
    actor_ctx: PrincipalContext,
    object_id: uuid.UUID,
) -> None:
    """Verify caller holds SHARE or ADMIN capability on object; return 404 if not viewable."""
    caps = await evaluate_capabilities(session, actor_ctx, object_id)
    if Capability.VIEW not in caps:
        not_found()

    if Capability.ADMIN not in caps and Capability.SHARE not in caps:
        raise ProblemException(
            code="INSUFFICIENT_PERMISSION",
            status=403,
            title="Insufficient Permission",
            detail="Caller requires SHARE or ADMIN capability on target object",
        )


async def _get_effective_capabilities(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    principal_id: uuid.UUID,
    object_id: uuid.UUID,
) -> list[str]:
    """Retrieve recomputed effective capability names for a principal on an object."""
    target_ctx = PrincipalContext(
        principal_id=principal_id,
        workspace_id=workspace_id,
        token_scopes=("session",),
    )
    eff_cap = await evaluate_capabilities(session, target_ctx, object_id)
    return capabilities_to_names(eff_cap)


async def grant_acl_entry(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    workspace_id: uuid.UUID,
    actor_ctx: PrincipalContext,
    object_id: uuid.UUID | str,
    principal_id: uuid.UUID | str,
    effect: str,
    capabilities: list[str],
) -> dict[str, Any]:
    """Grant or replace an ALLOW/DENY ACL entry for an object."""
    target_obj_id = await resolve_target_object_id(session, workspace_id, object_id)
    if isinstance(principal_id, uuid.UUID):
        target_p_id = principal_id
    else:
        target_p_id = await resolve_principal_id(session, workspace_id, str(principal_id))

    await _assert_admin_on_object(session, actor_ctx, target_obj_id)

    # Verify target principal belongs to workspace
    p_stmt = select(Principal).where(
        Principal.id == target_p_id,
        Principal.workspace_id == workspace_id,
        Principal.principal_type != "SCRIPT_EPHEMERAL",
    )
    principal = (await session.execute(p_stmt)).scalar_one_or_none()
    if principal is None:
        not_found()

    eff = effect.strip().upper()
    if eff not in ("ALLOW", "DENY"):
        msg = f"Invalid effect '{effect}'. Must be ALLOW or DENY"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="effect", message=msg)],
        )

    cap_mask = parse_capability_mask(capabilities)

    # Upsert entry
    existing_stmt = select(ResourceAclEntry).where(
        ResourceAclEntry.object_id == target_obj_id,
        ResourceAclEntry.principal_id == target_p_id,
        ResourceAclEntry.effect == eff,
    )
    entry = (await session.execute(existing_stmt)).scalar_one_or_none()
    if entry is not None:
        entry.capability_mask = cap_mask
        entry.created_by_id = actor_ctx.principal_id
    else:
        entry = ResourceAclEntry(
            workspace_id=workspace_id,
            object_id=target_obj_id,
            principal_id=target_p_id,
            effect=eff,
            capability_mask=cap_mask,
            created_by_id=actor_ctx.principal_id,
        )
        session.add(entry)

    await session.flush()

    await record_activity(
        session,
        workspace_id=workspace_id,
        actor_principal_id=actor_ctx.principal_id,
        event_type=ActivityEventType.ACL_ENTRY_GRANTED,
        payload={
            "object_id": str(target_obj_id),
            "principal_id": str(target_p_id),
            "effect": eff,
            "capabilities": [c.upper() for c in capabilities],
            "capability_mask": cap_mask,
        },
    )

    eff_caps = await _get_effective_capabilities(session, workspace_id, target_p_id, target_obj_id)

    return {
        "status": "granted",
        "object_id": str(target_obj_id),
        "principal_id": str(target_p_id),
        "effect": eff,
        "capabilities": [c.upper() for c in capabilities],
        "effective_capabilities": eff_caps,
    }


async def revoke_acl_entry(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    workspace_id: uuid.UUID,
    actor_ctx: PrincipalContext,
    object_id: uuid.UUID | str,
    principal_id: uuid.UUID | str,
    effect: str,
) -> dict[str, Any]:
    """Revoke an ALLOW/DENY ACL entry for an object."""
    target_obj_id = await resolve_target_object_id(session, workspace_id, object_id)
    if isinstance(principal_id, uuid.UUID):
        target_p_id = principal_id
    else:
        target_p_id = await resolve_principal_id(session, workspace_id, str(principal_id))

    await _assert_admin_on_object(session, actor_ctx, target_obj_id)

    # Verify target principal belongs to workspace
    p_stmt = select(Principal).where(
        Principal.id == target_p_id,
        Principal.workspace_id == workspace_id,
        Principal.principal_type != "SCRIPT_EPHEMERAL",
    )
    principal = (await session.execute(p_stmt)).scalar_one_or_none()
    if principal is None:
        not_found()

    eff = effect.strip().upper()
    if eff not in ("ALLOW", "DENY"):
        msg = f"Invalid effect '{effect}'. Must be ALLOW or DENY"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="effect", message=msg)],
        )

    del_stmt = delete(ResourceAclEntry).where(
        ResourceAclEntry.object_id == target_obj_id,
        ResourceAclEntry.principal_id == target_p_id,
        ResourceAclEntry.effect == eff,
    )
    res = await session.execute(del_stmt)
    await session.flush()

    if res.rowcount and res.rowcount > 0:
        await record_activity(
            session,
            workspace_id=workspace_id,
            actor_principal_id=actor_ctx.principal_id,
            event_type=ActivityEventType.ACL_ENTRY_REVOKED,
            payload={
                "object_id": str(target_obj_id),
                "principal_id": str(target_p_id),
                "effect": eff,
            },
        )

    eff_caps = await _get_effective_capabilities(session, workspace_id, target_p_id, target_obj_id)

    return {
        "status": "revoked",
        "object_id": str(target_obj_id),
        "principal_id": str(target_p_id),
        "effect": eff,
        "effective_capabilities": eff_caps,
    }


async def inspect_access_manifest(
    session: AsyncSession,
    actor_ctx: PrincipalContext,
    object_id: uuid.UUID | str,
) -> AccessManifest:
    """Inspect access manifest for an object enforcing anti-enumeration."""
    target_obj_id = await resolve_target_object_id(session, actor_ctx.workspace_id, object_id)
    await _assert_admin_on_object(session, actor_ctx, target_obj_id)
    return await build_access_manifest(session, actor_ctx, target_obj_id)
