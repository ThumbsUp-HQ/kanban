# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for Principals, Groups, and Role Bindings administration.

(KB-P4-09b, S11.4, S3.1).
"""

from __future__ import annotations

import logging
import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003
from typing import Annotated, Literal, Self

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PrincipalRoleLabel, RbacRoleModel, RbacRolePermission
from kanban.admin import principal_service
from kanban.api.deps import PrincipalContext, get_rls_session
from kanban.api.problems import FieldError, ProblemException
from kanban.api.v1.admin.workspace_settings import require_workspace_or_server_admin
from kanban.auth.mfa.policy import require_admin_aal2

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["admin-principals"],
    dependencies=[Depends(require_admin_aal2), Depends(require_workspace_or_server_admin)],
)

Caller = Annotated[PrincipalContext, Depends(require_workspace_or_server_admin)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


class ProvisionPrincipalRequest(BaseModel):
    """Schema for provisioning a user, group, or agent principal."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["USER", "GROUP", "AGENT"] = Field(
        description=(
            "Principal classification: USER for human accounts, GROUP for teams, AGENT for bots"
        )
    )
    display_name: str = Field(
        min_length=1, max_length=120, description="Human-readable display name"
    )
    handle: str | None = Field(
        default=None,
        pattern=r"^@?[a-z0-9][a-z0-9._-]{1,38}$",
        description="Unique username or agent handle slug (required for USER and AGENT)",
    )
    email: str | None = Field(
        default=None, description="Email address associated with human user accounts"
    )
    password: str | None = Field(
        default=None,
        min_length=8,
        max_length=1024,
        description="Optional initial password for local user credentials",
    )
    role: str | None = Field(
        default=None,
        description="Initial RBAC role (e.g. WORKSPACE_MEMBER, SERVER_ADMIN)",
    )


class ResetPasswordRequest(BaseModel):
    """Schema for resetting user password credentials."""

    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=8, max_length=1024, description="New user password")


class UpdatePrincipalRequest(BaseModel):
    """Schema for updating principal status, display name, or password."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "deactivated", "disabled"] | None = Field(
        default=None,
        description=(
            "Target operational status: active for normal access, deactivated for soft hold,"
            " disabled"
        ),
    )
    display_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        description="Updated human-readable display name",
    )
    password: str | None = Field(
        default=None,
        min_length=8,
        max_length=1024,
        description="Optional password update for local credentials",
    )


class RoleBindingRequest(BaseModel):
    """Schema for binding or unbinding an RBAC role."""

    model_config = ConfigDict(extra="ignore")

    principal_id: uuid.UUID = Field(
        description="Target principal UUID receiving the role assignment"
    )
    role: str | None = Field(
        default=None,
        description="RBAC role name to bind (e.g. SERVER_ADMIN, WORKSPACE_ADMIN, PROJECT_ADMIN)",
    )
    role_name: str | None = Field(
        default=None,
        description="Alternative field name for role",
    )
    scope_type: Literal["server", "workspace", "project"] = Field(
        description="Hierarchy tier for the binding: server, workspace, or project"
    )
    scope_id: uuid.UUID | None = Field(
        default=None,
        description="Optional scope target UUID (required when scope_type is project)",
    )

    @model_validator(mode="after")
    def resolve_role_field(self) -> Self:
        """Resolve role from role or role_name."""
        resolved = self.role or self.role_name
        if not resolved:
            msg = "role or role_name is required"
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail=msg,
                errors=[FieldError(path="role", message=msg)],
            )
        self.role = resolved
        self.role_name = resolved
        return self


@router.get(
    "/admin/principals",
    summary="List workspace principals",
)
async def list_principals_endpoint(
    caller: Caller,
    session: Session,
    filter: Annotated[  # noqa: A002
        str | None,
        Query(description="USER, GROUP, AGENT, or SERVICE_PRINCIPAL"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, object]]:
    """List principals in the current workspace with optional type filtering."""
    clean_filter = filter.strip() if filter and filter.strip() else None
    if clean_filter and clean_filter.upper() == "ALL":
        clean_filter = None
    return await principal_service.list_principals(
        session,
        caller.workspace_id,
        filter_type=clean_filter,
        limit=limit,
    )


@router.post(
    "/admin/principals",
    status_code=status.HTTP_201_CREATED,
    summary="Provision principal",
)
async def provision_principal_endpoint(
    body: ProvisionPrincipalRequest,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Provision a new USER, GROUP, or AGENT principal within the current workspace."""
    if body.type == "USER":
        if not body.handle:
            msg = "handle is required for USER provisioning"
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail=msg,
                errors=[FieldError(path="handle", message=msg)],
            )
        if not body.email:
            msg = "email is required for USER provisioning"
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail=msg,
                errors=[FieldError(path="email", message=msg)],
            )
        return await principal_service.provision_user(
            session,
            caller.workspace_id,
            caller.principal_id,
            handle=body.handle,
            display_name=body.display_name,
            email=body.email,
            password=body.password,
            role=body.role,
        )
    if body.type == "GROUP":
        group_name = (
            principal_service.normalize_handle(body.handle) if body.handle else body.display_name
        )
        res = await principal_service.provision_group(
            session,
            caller.workspace_id,
            caller.principal_id,
            name=group_name,
            display_name=body.display_name,
        )
        if body.handle:
            res["handle"] = f"@{group_name}"
        return res
    agent_handle = body.handle or body.display_name.lower().replace(" ", "-")
    return await principal_service.provision_agent(
        session,
        caller.workspace_id,
        caller.principal_id,
        handle=agent_handle,
        display_name=body.display_name,
    )


@router.get(
    "/admin/principals/{principal_id}",
    summary="Get principal details",
)
async def get_principal_endpoint(
    principal_id: str,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Retrieve administrative metadata and group memberships for a principal by UUID or handle."""
    return await principal_service.get_principal_detail(
        session,
        caller.workspace_id,
        principal_id,
    )


@router.patch(
    "/admin/principals/{principal_id}",
    summary="Update principal status or display name",
)
async def patch_principal_endpoint(
    principal_id: uuid.UUID,
    body: UpdatePrincipalRequest,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Update principal operational status, display name, or password credentials."""
    if body.password:
        await principal_service.reset_password(
            session,
            caller.workspace_id,
            caller.principal_id,
            principal_id,
            body.password,
        )
    return await principal_service.update_principal(
        session,
        caller.workspace_id,
        caller.principal_id,
        principal_id,
        status=body.status,
        display_name=body.display_name,
    )


@router.post(
    "/admin/principals/{principal_id}/password",
    summary="Reset principal local password",
)
async def reset_password_endpoint(
    principal_id: uuid.UUID,
    body: ResetPasswordRequest,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Reset password credentials for a local user principal."""
    return await principal_service.reset_password(
        session,
        caller.workspace_id,
        caller.principal_id,
        principal_id,
        body.password,
    )


@router.get(
    "/admin/groups/{group_id}/members",
    summary="List group members",
)
async def list_group_members_endpoint(
    group_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> list[dict[str, object]]:
    """List direct member principals (users, groups, agents) of the group."""
    return await principal_service.list_group_members(
        session,
        caller.workspace_id,
        group_id=group_id,
    )


@router.post(
    "/admin/groups/{group_id}/members/{principal_id}",
    summary="Add group member",
)
async def add_group_member_endpoint(
    group_id: uuid.UUID,
    principal_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Add an existing principal (user or agent) as a member of the administrative group."""
    return await principal_service.add_group_member(
        session,
        caller.workspace_id,
        caller.principal_id,
        group_id=group_id,
        member_id=principal_id,
    )


@router.delete(
    "/admin/groups/{group_id}/members/{principal_id}",
    summary="Remove group member",
)
async def remove_group_member_endpoint(
    group_id: uuid.UUID,
    principal_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Remove a member principal from the specified administrative group."""
    return await principal_service.remove_group_member(
        session,
        caller.workspace_id,
        caller.principal_id,
        group_id=group_id,
        member_id=principal_id,
    )


@router.post(
    "/admin/role-bindings",
    summary="Bind RBAC role to principal",
)
async def bind_role_endpoint(
    body: RoleBindingRequest,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Bind an RBAC role to a principal at server, workspace, or project scope."""
    target_role = body.role or body.role_name
    if not target_role:
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail="Role is required",
            errors=[FieldError(path="role", message="Role is required")],
        )
    return await principal_service.bind_role(
        session,
        caller.workspace_id,
        caller.principal_id,
        principal_id=body.principal_id,
        role_name=target_role,
        scope_type=body.scope_type,
        project_id=body.scope_id,
    )


@router.delete(
    "/admin/role-bindings",
    summary="Unbind RBAC role from principal",
)
async def unbind_role_endpoint(
    body: RoleBindingRequest,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Unbind an RBAC role from a principal at server, workspace, or project scope."""
    target_role = body.role or body.role_name
    if not target_role:
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail="Role is required",
            errors=[FieldError(path="role", message="Role is required")],
        )
    return await principal_service.unbind_role(
        session,
        caller.workspace_id,
        caller.principal_id,
        principal_id=body.principal_id,
        role_name=target_role,
        scope_type=body.scope_type,
        project_id=body.scope_id,
    )


class PrincipalRoleLabelItem(BaseModel):
    """Assigned role label for a principal."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    principal_id: uuid.UUID
    role_id: uuid.UUID
    role_slug: str
    role_name: str
    color_hex: str
    scope_tier: str
    project_id: uuid.UUID | None = None
    created_at: datetime


class AssignRoleLabelRequest(BaseModel):
    """Payload to assign a single role label to a principal."""

    model_config = ConfigDict(extra="forbid")

    role_id: uuid.UUID
    project_id: uuid.UUID | None = None


class BatchSetRoleLabelsRequest(BaseModel):
    """Payload to replace all role labels on a principal."""

    model_config = ConfigDict(extra="forbid")

    role_ids: list[uuid.UUID]
    project_id: uuid.UUID | None = None


async def _is_server_admin_caller(session: AsyncSession, caller: PrincipalContext) -> bool:
    if getattr(caller, "is_server_admin", False):
        return True
    try:
        stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
        res = await session.execute(stmt)
        return bool(res.scalar_one())
    except Exception:  # noqa: BLE001
        return False


async def _check_role_label_escalation(
    session: AsyncSession, caller: PrincipalContext, role: RbacRoleModel
) -> None:
    is_server_admin = await _is_server_admin_caller(session, caller)
    is_sys_or_server_role = role.slug == "system-admin" or role.system_role == "SERVER_ADMIN"
    if is_sys_or_server_role and not is_server_admin:
        raise ProblemException(
            code="ROLE_ESCALATION_DENIED",
            status=status.HTTP_403_FORBIDDEN,
            title="Role Escalation Denied",
            detail="Binding or unbinding a role with workspace permissions requires SERVER_ADMIN.",
        )
    stmt = select(RbacRolePermission.id).where(
        RbacRolePermission.role_id == role.id,
        RbacRolePermission.permission_key.like("workspace:%"),
        RbacRolePermission.effect == "ALLOW",
    )
    if (await session.execute(stmt)).first() is not None and not is_server_admin:
        raise ProblemException(
            code="ROLE_ESCALATION_DENIED",
            status=status.HTTP_403_FORBIDDEN,
            title="Role Escalation Denied",
            detail="Binding or unbinding a role with workspace permissions requires SERVER_ADMIN.",
        )


@router.get(
    "/admin/principals/{principal_id}/role-labels",
    response_model=list[PrincipalRoleLabelItem],
    summary="List assigned role labels for principal",
)
async def list_principal_role_labels_endpoint(
    principal_id: uuid.UUID,
    caller: Caller,
    session: Session,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[PrincipalRoleLabelItem]:
    """List all custom and built-in role labels attached to a user, group, or agent."""
    stmt = (
        select(PrincipalRoleLabel, RbacRoleModel)
        .join(RbacRoleModel, RbacRoleModel.id == PrincipalRoleLabel.role_id)
        .where(
            PrincipalRoleLabel.principal_id == principal_id,
            PrincipalRoleLabel.workspace_id == caller.workspace_id,
            (
                PrincipalRoleLabel.project_id.is_(None)
                if project_id is None
                else (
                    PrincipalRoleLabel.project_id.is_(None)
                    | (PrincipalRoleLabel.project_id == project_id)
                )
            ),
        )
        .order_by(PrincipalRoleLabel.created_at.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        PrincipalRoleLabelItem(
            id=label.id,
            workspace_id=label.workspace_id,
            principal_id=label.principal_id,
            role_id=label.role_id,
            role_slug=role.slug,
            role_name=role.name,
            color_hex=role.color_hex,
            scope_tier=role.scope_tier,
            project_id=label.project_id,
            created_at=label.created_at,
        )
        for label, role in rows
    ]


@router.post(
    "/admin/principals/{principal_id}/role-labels",
    response_model=PrincipalRoleLabelItem,
    status_code=status.HTTP_201_CREATED,
    summary="Assign role label to principal",
)
async def assign_principal_role_label_endpoint(
    principal_id: uuid.UUID,
    body: AssignRoleLabelRequest,
    caller: Caller,
    session: Session,
) -> PrincipalRoleLabelItem:
    """Attach a role label to a principal (Rule 1)."""
    role = await session.get(RbacRoleModel, body.role_id)
    if role is None or role.workspace_id != caller.workspace_id:
        raise ProblemException(
            code="NOT_FOUND",
            status=status.HTTP_404_NOT_FOUND,
            title="Not Found",
            detail="RBAC role not found.",
        )

    await _check_role_label_escalation(session, caller, role)

    label = PrincipalRoleLabel(
        workspace_id=caller.workspace_id,
        principal_id=principal_id,
        role_id=body.role_id,
        project_id=body.project_id,
        assigned_by_id=caller.principal_id,
    )
    session.add(label)
    await session.commit()
    await session.refresh(label)

    return PrincipalRoleLabelItem(
        id=label.id,
        workspace_id=label.workspace_id,
        principal_id=label.principal_id,
        role_id=label.role_id,
        role_slug=role.slug,
        role_name=role.name,
        color_hex=role.color_hex,
        scope_tier=role.scope_tier,
        project_id=label.project_id,
        created_at=label.created_at,
    )


@router.put(
    "/admin/principals/{principal_id}/role-labels",
    response_model=list[PrincipalRoleLabelItem],
    summary="Batch set role labels for principal",
)
async def batch_set_principal_role_labels_endpoint(
    principal_id: uuid.UUID,
    body: BatchSetRoleLabelsRequest,
    caller: Caller,
    session: Session,
) -> list[PrincipalRoleLabelItem]:
    """Batch replace all role labels on a principal (multi-role chip picker support)."""
    # Fetch existing labels
    cur_labels = (
        (
            await session.execute(
                select(PrincipalRoleLabel).where(
                    PrincipalRoleLabel.principal_id == principal_id,
                    PrincipalRoleLabel.workspace_id == caller.workspace_id,
                    (
                        PrincipalRoleLabel.project_id.is_(None)
                        if body.project_id is None
                        else PrincipalRoleLabel.project_id == body.project_id
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    cur_role_ids = {lbl.role_id for lbl in cur_labels}
    new_role_ids = set(body.role_ids)

    # Check escalation on all changed roles
    changed_ids = cur_role_ids ^ new_role_ids
    if changed_ids:
        roles_stmt = select(RbacRoleModel).where(
            RbacRoleModel.id.in_(changed_ids),
            RbacRoleModel.workspace_id == caller.workspace_id,
        )
        for r in (await session.execute(roles_stmt)).scalars().all():
            await _check_role_label_escalation(session, caller, r)

    # Delete removed
    to_delete = cur_role_ids - new_role_ids
    if to_delete:
        await session.execute(
            delete(PrincipalRoleLabel).where(
                PrincipalRoleLabel.principal_id == principal_id,
                PrincipalRoleLabel.workspace_id == caller.workspace_id,
                PrincipalRoleLabel.role_id.in_(to_delete),
                (
                    PrincipalRoleLabel.project_id.is_(None)
                    if body.project_id is None
                    else PrincipalRoleLabel.project_id == body.project_id
                ),
            )
        )

    # Add new
    to_add = new_role_ids - cur_role_ids
    for r_id in to_add:
        session.add(
            PrincipalRoleLabel(
                workspace_id=caller.workspace_id,
                principal_id=principal_id,
                role_id=r_id,
                project_id=body.project_id,
                assigned_by_id=caller.principal_id,
            )
        )

    await session.commit()

    # Return refreshed list
    return await list_principal_role_labels_endpoint(
        principal_id, caller, session, project_id=body.project_id
    )


@router.delete(
    "/admin/principals/{principal_id}/role-labels/{role_id}",
    summary="Remove a role label from principal",
)
async def remove_principal_role_label_endpoint(
    principal_id: uuid.UUID,
    role_id: uuid.UUID,
    caller: Caller,
    session: Session,
    project_id: Annotated[uuid.UUID | None, Query()] = None,
) -> dict[str, object]:
    """Detach a role label from a principal (Rule 1)."""
    role = await session.get(RbacRoleModel, role_id)
    if role is not None and role.workspace_id == caller.workspace_id:
        await _check_role_label_escalation(session, caller, role)

    await session.execute(
        delete(PrincipalRoleLabel).where(
            PrincipalRoleLabel.principal_id == principal_id,
            PrincipalRoleLabel.workspace_id == caller.workspace_id,
            PrincipalRoleLabel.role_id == role_id,
            (
                PrincipalRoleLabel.project_id.is_(None)
                if project_id is None
                else PrincipalRoleLabel.project_id == project_id
            ),
        )
    )
    await session.commit()
    return {"status": "deleted", "principal_id": str(principal_id), "role_id": str(role_id)}
