# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for Principals, Groups, and Role Bindings administration.

(KB-P4-09b, S11.4, S3.1).
"""

from __future__ import annotations

import logging
import uuid  # noqa: TC003
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

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

    type: Literal["USER", "GROUP", "AGENT"]
    display_name: str = Field(min_length=1, max_length=120)
    handle: str | None = Field(default=None, pattern=r"^@?[a-z0-9][a-z0-9._-]{1,38}$")
    email: str | None = None


class UpdatePrincipalRequest(BaseModel):
    """Schema for updating principal status or display name."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "deactivated", "disabled"] | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=120)


class RoleBindingRequest(BaseModel):
    """Schema for binding or unbinding an RBAC role."""

    model_config = ConfigDict(extra="forbid")

    principal_id: uuid.UUID
    role: str
    scope_type: Literal["server", "workspace", "project"]
    scope_id: uuid.UUID | None = None


@router.get("/admin/principals")
async def list_principals_endpoint(
    caller: Caller,
    session: Session,
    filter: Annotated[  # noqa: A002
        str | None,
        Query(description="USER, GROUP, AGENT, or SERVICE_PRINCIPAL"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, object]]:
    """List principals in the current workspace."""
    return await principal_service.list_principals(
        session,
        caller.workspace_id,
        filter_type=filter,
        limit=limit,
    )


@router.post("/admin/principals", status_code=status.HTTP_201_CREATED)
async def provision_principal_endpoint(
    body: ProvisionPrincipalRequest,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Provision a new USER, GROUP, or AGENT principal."""
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
        )
    if body.type == "GROUP":
        return await principal_service.provision_group(
            session,
            caller.workspace_id,
            caller.principal_id,
            name=body.display_name,
            display_name=body.display_name,
        )
    agent_handle = body.handle or body.display_name.lower().replace(" ", "-")
    return await principal_service.provision_agent(
        session,
        caller.workspace_id,
        caller.principal_id,
        handle=agent_handle,
        display_name=body.display_name,
    )


@router.get("/admin/principals/{principal_id}")
async def get_principal_endpoint(
    principal_id: str,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Get full details of a principal by UUID or reference."""
    return await principal_service.get_principal_detail(
        session,
        caller.workspace_id,
        principal_id,
    )


@router.patch("/admin/principals/{principal_id}")
async def patch_principal_endpoint(
    principal_id: uuid.UUID,
    body: UpdatePrincipalRequest,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Update principal status or display name."""
    return await principal_service.update_principal(
        session,
        caller.workspace_id,
        caller.principal_id,
        principal_id,
        status=body.status,
        display_name=body.display_name,
    )


@router.post("/admin/groups/{group_id}/members/{principal_id}")
async def add_group_member_endpoint(
    group_id: uuid.UUID,
    principal_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Add a principal as a member of a group."""
    return await principal_service.add_group_member(
        session,
        caller.workspace_id,
        caller.principal_id,
        group_id=group_id,
        member_id=principal_id,
    )


@router.delete("/admin/groups/{group_id}/members/{principal_id}")
async def remove_group_member_endpoint(
    group_id: uuid.UUID,
    principal_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Remove a principal from a group."""
    return await principal_service.remove_group_member(
        session,
        caller.workspace_id,
        caller.principal_id,
        group_id=group_id,
        member_id=principal_id,
    )


@router.post("/admin/role-bindings")
async def bind_role_endpoint(
    body: RoleBindingRequest,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Bind an RBAC role to a principal."""
    return await principal_service.bind_role(
        session,
        caller.workspace_id,
        caller.principal_id,
        principal_id=body.principal_id,
        role_name=body.role,
        scope_type=body.scope_type,
        project_id=body.scope_id,
    )


@router.delete("/admin/role-bindings")
async def unbind_role_endpoint(
    body: RoleBindingRequest,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Unbind an RBAC role from a principal."""
    return await principal_service.unbind_role(
        session,
        caller.workspace_id,
        caller.principal_id,
        principal_id=body.principal_id,
        role_name=body.role,
        scope_type=body.scope_type,
        project_id=body.scope_id,
    )
