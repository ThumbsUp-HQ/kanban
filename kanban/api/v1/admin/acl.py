# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for Object ACL entries administration (KB-P4-09b, S11.4, S3.2, S3.4)."""

from __future__ import annotations

import logging
import uuid  # noqa: TC003
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from kanban.admin import acl_service
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.auth.mfa.policy import require_admin_aal2
from kanban.security.access_manifest import AccessManifest

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/acl-entries",
    tags=["admin-acl"],
    dependencies=[Depends(require_admin_aal2)],
)

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


class GrantAclEntryRequest(BaseModel):
    """Schema for granting an ALLOW or DENY ACL capability entry."""

    model_config = ConfigDict(extra="forbid")

    object_id: str | uuid.UUID
    principal_id: str | uuid.UUID
    effect: Literal["ALLOW", "DENY"]
    capabilities: list[str] = Field(min_length=1, max_length=8)


class RevokeAclEntryRequest(BaseModel):
    """Schema for revoking an ACL entry."""

    model_config = ConfigDict(extra="forbid")

    object_id: str | uuid.UUID
    principal_id: str | uuid.UUID
    effect: Literal["ALLOW", "DENY"]


@router.post("", status_code=status.HTTP_200_OK)
async def grant_acl_entry_endpoint(
    body: GrantAclEntryRequest,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Grant or replace an ALLOW/DENY ACL entry for an object."""
    return await acl_service.grant_acl_entry(
        session,
        caller.workspace_id,
        caller,
        object_id=body.object_id,
        principal_id=body.principal_id,
        effect=body.effect,
        capabilities=body.capabilities,
    )


@router.delete("", status_code=status.HTTP_200_OK)
async def revoke_acl_entry_endpoint(
    body: RevokeAclEntryRequest,
    caller: Caller,
    session: Session,
) -> dict[str, object]:
    """Revoke an ALLOW/DENY ACL entry for an object."""
    return await acl_service.revoke_acl_entry(
        session,
        caller.workspace_id,
        caller,
        object_id=body.object_id,
        principal_id=body.principal_id,
        effect=body.effect,
    )


@router.get("/{object_id}/manifest", response_model=AccessManifest)
async def inspect_manifest_endpoint(
    object_id: str,
    caller: Caller,
    session: Session,
) -> AccessManifest:
    """Inspect access manifest for an object enforcing anti-enumeration."""
    return await acl_service.inspect_access_manifest(
        session,
        caller,
        object_id,
    )
