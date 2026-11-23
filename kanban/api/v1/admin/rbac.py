# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for Granular RBAC Role and Permission Administration.

(KB-GRANULAR-RBAC, KAN-83).
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    PrincipalRoleLabel,
    RbacRoleModel,
    RbacRolePermission,
)
from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.api.problems import ProblemException
from kanban.api.v1.admin.workspace_settings import require_workspace_or_server_admin
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.security.granular_permissions import (
    ALL_PERMISSIONS,
    DEFAULT_BUILTIN_ROLE_PERMISSIONS,
    WORKSPACE_PERMISSIONS,
    GranularPermission,
    require_permissions,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/rbac",
    tags=["admin-rbac"],
    dependencies=[Depends(require_admin_aal2), Depends(require_workspace_or_server_admin)],
)

Caller = Annotated[PrincipalContext, Depends(require_workspace_or_server_admin)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


class CreateRbacRoleRequest(BaseModel):
    """Request payload for creating a custom RBAC role."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100, description="Display name for the role")
    slug: str | None = Field(default=None, max_length=100, description="URL-safe slug")
    color_hex: str = Field(
        default="#3b82f6",
        pattern=r"^#[0-9a-fA-F]{6}$",
        description="Hex color code for role pill badge",
    )
    description: str | None = Field(default=None, max_length=500, description="Role purpose")
    scope_tier: Literal["workspace", "project"] = Field(
        default="workspace", description="Tier scope of the role"
    )
    project_id: uuid.UUID | None = Field(default=None, description="Optional project binding")
    clone_from_role_id: uuid.UUID | None = Field(
        default=None, description="Optional role ID to copy permissions from"
    )


class UpdateRbacRoleRequest(BaseModel):
    """Request payload for updating an existing RBAC role."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    color_hex: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    description: str | None = Field(default=None, max_length=500)


class SetRolePermissionsRequest(BaseModel):
    """Request payload for setting role permissions."""

    model_config = ConfigDict(extra="forbid")

    permissions: list[str] = Field(description="Complete set of permissions to assign")


class BatchUpdatePermissionsRequest(BaseModel):
    """Request payload for toggling a single permission across multiple roles."""

    model_config = ConfigDict(extra="forbid")

    role_ids: list[uuid.UUID] = Field(min_length=1, description="Roles to update")
    permission_key: str = Field(description="Granular permission key")
    granted: bool = Field(description="Whether permission should be enabled or disabled")


class RbacRoleResponse(BaseModel):
    """Response model for an RBAC role."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    slug: str
    name: str
    color_hex: str
    description: str | None
    is_system: bool
    system_role: str | None
    scope_tier: str
    base_capability_mask: int
    project_id: uuid.UUID | None
    permissions: list[str] = []
    created_at: datetime
    updated_at: datetime


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:100] or "custom-role"


async def _is_server_admin_caller(session: AsyncSession, caller: PrincipalContext) -> bool:
    if getattr(caller, "is_server_admin", False):
        return True
    try:
        stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
        res = await session.execute(stmt)
        return bool(res.scalar_one())
    except Exception:  # noqa: BLE001
        return False


async def _role_has_workspace_perms(session: AsyncSession, role_id: uuid.UUID) -> bool:
    stmt = select(RbacRolePermission).where(
        RbacRolePermission.role_id == role_id,
        RbacRolePermission.permission_key.like("workspace:%"),
        RbacRolePermission.effect == "ALLOW",
    )
    return (await session.execute(stmt)).first() is not None


@router.get(
    "/roles",
    response_model=list[RbacRoleResponse],
    summary="List RBAC roles for workspace",
)
async def list_roles_endpoint(
    caller: Caller,
    session: Session,
    _project_id: Annotated[uuid.UUID | None, Query(alias="project_id")] = None,
) -> list[RbacRoleResponse]:
    """List all system and custom RBAC roles in workspace with their assigned permissions."""
    stmt = (
        select(RbacRoleModel)
        .where(
            RbacRoleModel.workspace_id == caller.workspace_id,
        )
        .order_by(RbacRoleModel.is_system.desc(), RbacRoleModel.name.asc())
    )
    roles = (await session.execute(stmt)).scalars().all()

    # Load permissions for each role
    role_ids = [r.id for r in roles]
    p_stmt = select(RbacRolePermission).where(
        RbacRolePermission.role_id.in_(role_ids),
        RbacRolePermission.effect == "ALLOW",
    )
    perms_by_role: dict[uuid.UUID, list[str]] = {r.id: [] for r in roles}
    for p in (await session.execute(p_stmt)).scalars().all():
        perms_by_role[p.role_id].append(p.permission_key)

    # For system roles, fall back to built-in defaults if permissions table is sparse
    results: list[RbacRoleResponse] = []
    for r in roles:
        perms = perms_by_role.get(r.id, [])
        if not perms and r.slug in DEFAULT_BUILTIN_ROLE_PERMISSIONS:
            perms = sorted(DEFAULT_BUILTIN_ROLE_PERMISSIONS[r.slug])
        elif not perms and r.system_role in DEFAULT_BUILTIN_ROLE_PERMISSIONS:
            perms = sorted(DEFAULT_BUILTIN_ROLE_PERMISSIONS[r.system_role])

        results.append(
            RbacRoleResponse(
                id=r.id,
                workspace_id=r.workspace_id,
                slug=r.slug,
                name=r.name,
                color_hex=r.color_hex,
                description=r.description,
                is_system=r.is_system,
                system_role=r.system_role,
                scope_tier=r.scope_tier,
                base_capability_mask=r.base_capability_mask,
                project_id=None,
                permissions=sorted(perms),
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return results


@router.post(
    "/roles",
    response_model=RbacRoleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom RBAC role",
)
async def create_role_endpoint(
    body: CreateRbacRoleRequest,
    caller: Caller,
    session: Session,
) -> RbacRoleResponse:
    """Create a new custom RBAC role (Rule 3).

    WORKSPACE_ADMIN and SERVER_ADMIN can create roles.
    If cloned by WORKSPACE_ADMIN from a role with workspace:* permissions,
    workspace:* grants are automatically stripped so escalation is prevented.
    """
    await require_permissions(
        session, caller, caller.workspace_id, {GranularPermission.WORKSPACE_CREATE_ROLE.value}
    )

    now = datetime.now(UTC)
    base_slug = body.slug or _slugify(body.name)
    role_id = uuid.uuid4()

    # Ensure unique slug within workspace
    existing_slug = await session.scalar(
        select(RbacRoleModel.id).where(
            RbacRoleModel.workspace_id == caller.workspace_id,
            RbacRoleModel.slug == base_slug,
        )
    )
    final_slug = f"{base_slug}-{role_id.hex[:6]}" if existing_slug else base_slug

    new_role = RbacRoleModel(
        id=role_id,
        workspace_id=caller.workspace_id,
        slug=final_slug,
        name=body.name,
        color_hex=body.color_hex,
        description=body.description,
        is_system=False,
        system_role=None,
        scope_tier=body.scope_tier,
        base_capability_mask=0,
        created_by_id=caller.principal_id,
        created_at=now,
        updated_at=now,
    )
    session.add(new_role)
    await session.flush()

    assigned_perms: list[str] = []
    if body.clone_from_role_id is not None:
        src_perms_stmt = select(RbacRolePermission.permission_key).where(
            RbacRolePermission.role_id == body.clone_from_role_id,
            RbacRolePermission.effect == "ALLOW",
        )
        src_perms = set((await session.execute(src_perms_stmt)).scalars().all())
        if not src_perms:
            src_role = await session.get(RbacRoleModel, body.clone_from_role_id)
            if src_role and src_role.slug in DEFAULT_BUILTIN_ROLE_PERMISSIONS:
                src_perms = set(DEFAULT_BUILTIN_ROLE_PERMISSIONS[src_role.slug])

        # Rule 3 / Rule 1: Strip workspace:* permissions if caller is not SERVER_ADMIN
        if not await _is_server_admin_caller(session, caller):
            src_perms = {p for p in src_perms if not p.startswith("workspace:")}

        for perm in src_perms:
            session.add(
                RbacRolePermission(
                    workspace_id=caller.workspace_id,
                    role_id=role_id,
                    project_id=body.project_id,
                    permission_key=perm,
                    effect="ALLOW",
                    updated_by_id=caller.principal_id,
                    updated_at=now,
                )
            )
            assigned_perms.append(perm)
        await session.flush()

    await session.refresh(new_role)
    await session.commit()

    return RbacRoleResponse(
        id=new_role.id,
        workspace_id=new_role.workspace_id,
        slug=new_role.slug,
        name=new_role.name,
        color_hex=new_role.color_hex,
        description=new_role.description,
        is_system=new_role.is_system,
        system_role=new_role.system_role,
        scope_tier=new_role.scope_tier,
        base_capability_mask=new_role.base_capability_mask,
        project_id=None,
        permissions=sorted(assigned_perms),
        created_at=new_role.created_at,
        updated_at=new_role.updated_at,
    )


@router.patch(
    "/roles/{role_id}",
    response_model=RbacRoleResponse,
    summary="Update RBAC role attributes",
)
async def update_role_endpoint(
    role_id: uuid.UUID,
    body: UpdateRbacRoleRequest,
    caller: Caller,
    session: Session,
) -> RbacRoleResponse:
    """Update role display name, color_hex, or description (Rule 1)."""
    role = await session.get(RbacRoleModel, role_id)
    if role is None or role.workspace_id != caller.workspace_id:
        raise ProblemException(
            code="NOT_FOUND",
            status=status.HTTP_404_NOT_FOUND,
            title="Not Found",
            detail="RBAC role not found.",
        )

    # Rule 1: WORKSPACE_ADMIN cannot modify role holding workspace:* permissions or system-admin
    if (
        role.slug == "system-admin"
        or role.system_role == "SERVER_ADMIN"
        or await _role_has_workspace_perms(session, role_id)
    ) and not await _is_server_admin_caller(session, caller):
        raise ProblemException(
            code="WORKSPACE_PERMISSION_LOCKED",
            status=status.HTTP_403_FORBIDDEN,
            title="Workspace Permission Locked",
            detail="Only Server Admin can modify roles with workspace permissions.",
        )

    if body.name is not None and not role.is_system:
        role.name = body.name
    if body.color_hex is not None:
        role.color_hex = body.color_hex
    if body.description is not None:
        role.description = body.description

    role.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(role)

    p_stmt = select(RbacRolePermission.permission_key).where(
        RbacRolePermission.role_id == role.id,
        RbacRolePermission.effect == "ALLOW",
    )
    perms = (await session.execute(p_stmt)).scalars().all()

    return RbacRoleResponse(
        id=role.id,
        workspace_id=role.workspace_id,
        slug=role.slug,
        name=role.name,
        color_hex=role.color_hex,
        description=role.description,
        is_system=role.is_system,
        system_role=role.system_role,
        scope_tier=role.scope_tier,
        base_capability_mask=role.base_capability_mask,
        project_id=None,
        permissions=sorted(perms),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


@router.delete(
    "/roles/{role_id}",
    summary="Delete custom RBAC role",
)
async def delete_role_endpoint(
    role_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Delete a custom RBAC role (Rule 1). Built-in roles cannot be deleted."""
    role = await session.get(RbacRoleModel, role_id)
    if role is None or role.workspace_id != caller.workspace_id:
        raise ProblemException(
            code="NOT_FOUND",
            status=status.HTTP_404_NOT_FOUND,
            title="Not Found",
            detail="RBAC role not found.",
        )

    if role.is_system:
        raise ProblemException(
            code="SYSTEM_ROLE_PROTECTED",
            status=status.HTTP_403_FORBIDDEN,
            title="System Role Protected",
            detail="Built-in system roles cannot be deleted.",
        )

    # Rule 1: Cannot delete role holding workspace:* permissions unless SERVER_ADMIN
    if await _role_has_workspace_perms(session, role_id) and not await _is_server_admin_caller(
        session, caller
    ):
        raise ProblemException(
            code="WORKSPACE_PERMISSION_LOCKED",
            status=status.HTTP_403_FORBIDDEN,
            title="Workspace Permission Locked",
            detail="Only Server Admin can delete roles with workspace permissions.",
        )

    # Delete role and associated labels & permissions
    await session.execute(delete(PrincipalRoleLabel).where(PrincipalRoleLabel.role_id == role_id))
    await session.execute(delete(RbacRolePermission).where(RbacRolePermission.role_id == role_id))
    await session.delete(role)
    await session.commit()

    return {"status": "deleted", "id": str(role_id)}


@router.get(
    "/roles/{role_id}/permissions",
    summary="Get permissions for a role",
)
async def get_role_permissions_endpoint(
    role_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Get active permissions assigned to an RBAC role."""
    role = await session.get(RbacRoleModel, role_id)
    if role is None or role.workspace_id != caller.workspace_id:
        raise ProblemException(
            code="NOT_FOUND",
            status=status.HTTP_404_NOT_FOUND,
            title="Not Found",
            detail="RBAC role not found.",
        )

    p_stmt = select(RbacRolePermission.permission_key).where(
        RbacRolePermission.role_id == role_id,
        RbacRolePermission.effect == "ALLOW",
    )
    perms = list((await session.execute(p_stmt)).scalars().all())
    if not perms and role.slug in DEFAULT_BUILTIN_ROLE_PERMISSIONS:
        perms = sorted(DEFAULT_BUILTIN_ROLE_PERMISSIONS[role.slug])

    return {"role_id": str(role_id), "permissions": sorted(perms)}


@router.put(
    "/roles/{role_id}/permissions",
    summary="Replace permissions for a role",
)
async def set_role_permissions_endpoint(
    role_id: uuid.UUID,
    body: SetRolePermissionsRequest,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Replace all permissions on a role (Rule 1 & Rule 2)."""
    role = await session.get(RbacRoleModel, role_id)
    if role is None or role.workspace_id != caller.workspace_id:
        raise ProblemException(
            code="NOT_FOUND",
            status=status.HTTP_404_NOT_FOUND,
            title="Not Found",
            detail="RBAC role not found.",
        )

    # Validate permission keys
    for p in body.permissions:
        if p not in ALL_PERMISSIONS:
            raise ProblemException(
                code="INVALID_PERMISSION_KEY",
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                title="Invalid Permission Key",
                detail=f"Unknown permission key: {p}",
            )

    # Existing permissions on role
    cur_perms = set(
        (
            await session.execute(
                select(RbacRolePermission.permission_key).where(
                    RbacRolePermission.role_id == role_id,
                    RbacRolePermission.effect == "ALLOW",
                )
            )
        )
        .scalars()
        .all()
    )
    new_perms = set(body.permissions)

    # Rule 1: WORKSPACE_ADMIN cannot toggle workspace:* permissions
    mutated_workspace_perms = (cur_perms ^ new_perms) & WORKSPACE_PERMISSIONS
    if mutated_workspace_perms and not await _is_server_admin_caller(session, caller):
        raise ProblemException(
            code="WORKSPACE_PERMISSION_LOCKED",
            status=status.HTTP_403_FORBIDDEN,
            title="Workspace Permission Locked",
            detail="Only Server Admin can modify workspace:* permissions.",
        )

    now = datetime.now(UTC)
    # Remove permissions not in new set
    to_remove = cur_perms - new_perms
    if to_remove:
        await session.execute(
            delete(RbacRolePermission).where(
                RbacRolePermission.role_id == role_id,
                RbacRolePermission.permission_key.in_(to_remove),
            )
        )

    # Add permissions not in current set
    to_add = new_perms - cur_perms
    for p in to_add:
        session.add(
            RbacRolePermission(
                workspace_id=caller.workspace_id,
                role_id=role_id,
                project_id=None,
                permission_key=p,
                effect="ALLOW",
                updated_by_id=caller.principal_id,
                updated_at=now,
            )
        )

    await session.commit()
    await session.refresh(role)

    return {
        "role_id": str(role_id),
        "base_capability_mask": role.base_capability_mask,
        "permissions": sorted(new_perms),
    }


@router.put(
    "/roles/permissions:batch",
    summary="Batch update a permission across multiple roles",
)
async def batch_update_role_permissions_endpoint(
    body: BatchUpdatePermissionsRequest,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Toggle a permission key across multiple roles simultaneously (tri-state checkbox support)."""
    if body.permission_key not in ALL_PERMISSIONS:
        raise ProblemException(
            code="INVALID_PERMISSION_KEY",
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Invalid Permission Key",
            detail=f"Unknown permission key: {body.permission_key}",
        )

    # Rule 1: WORKSPACE_ADMIN cannot modify workspace:* permissions
    if body.permission_key.startswith("workspace:") and not await _is_server_admin_caller(
        session, caller
    ):
        raise ProblemException(
            code="WORKSPACE_PERMISSION_LOCKED",
            status=status.HTTP_403_FORBIDDEN,
            title="Workspace Permission Locked",
            detail="Only Server Admin can modify workspace:* permissions.",
        )

    # Validate roles belong to caller's workspace
    roles = (
        (
            await session.execute(
                select(RbacRoleModel).where(
                    RbacRoleModel.id.in_(body.role_ids),
                    RbacRoleModel.workspace_id == caller.workspace_id,
                )
            )
        )
        .scalars()
        .all()
    )
    valid_role_ids = [r.id for r in roles]

    now = datetime.now(UTC)
    if body.granted:
        for r_id in valid_role_ids:
            # Check if exists
            exists = await session.scalar(
                select(RbacRolePermission.id).where(
                    RbacRolePermission.role_id == r_id,
                    RbacRolePermission.permission_key == body.permission_key,
                )
            )
            if not exists:
                session.add(
                    RbacRolePermission(
                        workspace_id=caller.workspace_id,
                        role_id=r_id,
                        project_id=None,
                        permission_key=body.permission_key,
                        effect="ALLOW",
                        updated_by_id=caller.principal_id,
                        updated_at=now,
                    )
                )
    else:
        await session.execute(
            delete(RbacRolePermission).where(
                RbacRolePermission.role_id.in_(valid_role_ids),
                RbacRolePermission.permission_key == body.permission_key,
            )
        )

    await session.commit()
    return {
        "status": "success",
        "permission_key": body.permission_key,
        "granted": body.granted,
        "updated_role_ids": [str(r) for r in valid_role_ids],
    }
