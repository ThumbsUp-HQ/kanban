# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""User self-service MCP API keys router (KB-P4-14 / KANBA-106, S11.1, S3.2)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for Pydantic type annotations
from datetime import datetime  # noqa: TC003  # Runtime import required for Pydantic type annotations
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.mcp_api_key import McpApiKey
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import not_found
from kanban.security.mcp_keys import (
    mint_mcp_api_key,
    revoke_mcp_api_key,
)

router = APIRouter(prefix="/auth/mcp-keys", tags=["auth-mcp-keys"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


class PersonalMcpKeyMintRequest(BaseModel):
    """Payload for minting a self-service personal MCP API key."""

    model_config = ConfigDict(extra="forbid")

    surface: Literal["agent", "docs", "admin"]
    scopes: list[str] = Field(min_length=1)
    expires_in_days: int | None = Field(default=30, ge=1, le=365)
    expires_at: datetime | None = None
    scope_tier: Literal["global", "workspace", "project"] = "workspace"
    workspace_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    allowed_workspace_ids: list[uuid.UUID] | None = None
    allowed_project_ids: list[uuid.UUID] | None = None
    capability_mask: int = Field(default=7, ge=1, le=255)
    allowed_tools: list[str] | None = None
    disabled_tools: list[str] = Field(default_factory=list)
    allowed_cidrs: list[str] | None = None
    unlimited: bool = False
    confirm_unlimited: bool = False


class PersonalMcpKeyMintResponse(BaseModel):
    """One-time mint response carrying raw plaintext key."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    raw_key: str
    surface: str
    key_prefix: str
    display_hint: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None = None
    scope_tier: str = "workspace"
    owner_kind: str = "personal_user"
    workspace_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    allowed_tools: list[str] | None = None
    disabled_tools: list[str] = Field(default_factory=list)
    allowed_cidrs: list[str] | None = None
    capability_mask: int = 7


class PersonalMcpKeyItem(BaseModel):
    """Metadata for an existing personal MCP API key."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    surface: str
    key_prefix: str
    display_hint: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    scope_tier: str = "workspace"
    owner_kind: str = "personal_user"
    workspace_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    allowed_tools: list[str] | None = None
    disabled_tools: list[str] = Field(default_factory=list)
    allowed_cidrs: list[str] | None = None
    capability_mask: int = 7


class PersonalMcpKeyListResponse(BaseModel):
    """Listing response of personal MCP keys for current caller."""

    model_config = ConfigDict(extra="ignore")

    keys: list[PersonalMcpKeyItem]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=PersonalMcpKeyMintResponse,
    summary="Mint personal MCP API key",
)
async def mint_personal_key(
    body: PersonalMcpKeyMintRequest,
    caller: Caller,
    session: Session,
    response: Response,
) -> PersonalMcpKeyMintResponse:
    """Mint a self-service personal MCP API key locked to the caller's principal."""
    target_workspace_id = (
        None if body.scope_tier == "global" else (body.workspace_id or caller.workspace_id)
    )

    key_record, plaintext_token = await mint_mcp_api_key(
        session,
        workspace_id=target_workspace_id,
        principal_id=caller.principal_id,
        surface=body.surface,
        scopes=body.scopes,
        created_by_id=caller.principal_id,
        expires_at=body.expires_at,
        expires_in_days=body.expires_in_days,
        scope_tier=body.scope_tier,
        owner_kind="personal_user",
        project_id=body.project_id,
        allowed_workspace_ids=body.allowed_workspace_ids,
        allowed_project_ids=body.allowed_project_ids,
        capability_mask=body.capability_mask,
        allowed_tools=body.allowed_tools,
        disabled_tools=body.disabled_tools,
        allowed_cidrs=body.allowed_cidrs,
        unlimited=body.unlimited,
        confirm_unlimited=body.confirm_unlimited,
        caller_aal_level=caller.aal_level,
    )

    response.headers["Location"] = f"/api/v1/auth/mcp-keys/{key_record.id}"

    return PersonalMcpKeyMintResponse(
        id=key_record.id,
        raw_key=plaintext_token,
        surface=key_record.surface,
        key_prefix=key_record.key_prefix,
        display_hint=key_record.display_hint,
        scopes=list(key_record.scopes),
        created_at=key_record.created_at,
        expires_at=key_record.expires_at,
        scope_tier=key_record.scope_tier,
        owner_kind=key_record.owner_kind,
        workspace_id=key_record.workspace_id,
        project_id=key_record.project_id,
        allowed_tools=key_record.allowed_tools,
        disabled_tools=list(key_record.disabled_tools or []),
        allowed_cidrs=(
            [str(c) for c in key_record.allowed_cidrs] if key_record.allowed_cidrs else None
        ),
        capability_mask=key_record.capability_mask,
    )


@router.get(
    "",
    response_model=PersonalMcpKeyListResponse,
    summary="List personal MCP API keys",
)
async def list_personal_keys(
    caller: Caller,
    session: Session,
) -> PersonalMcpKeyListResponse:
    """List all personal MCP API keys owned by the calling principal."""
    stmt = (
        select(McpApiKey)
        .where(
            McpApiKey.principal_id == caller.principal_id,
            McpApiKey.owner_kind == "personal_user",
        )
        .order_by(McpApiKey.created_at.desc())
    )
    records = (await session.execute(stmt)).scalars().all()

    return PersonalMcpKeyListResponse(
        keys=[
            PersonalMcpKeyItem(
                id=k.id,
                surface=k.surface,
                key_prefix=k.key_prefix,
                display_hint=k.display_hint,
                scopes=list(k.scopes),
                created_at=k.created_at,
                expires_at=k.expires_at,
                revoked_at=k.revoked_at,
                last_used_at=k.last_used_at,
                scope_tier=k.scope_tier,
                owner_kind=k.owner_kind,
                workspace_id=k.workspace_id,
                project_id=k.project_id,
                allowed_tools=k.allowed_tools,
                disabled_tools=list(k.disabled_tools or []),
                allowed_cidrs=([str(c) for c in k.allowed_cidrs] if k.allowed_cidrs else None),
                capability_mask=k.capability_mask,
            )
            for k in records
        ]
    )


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke personal MCP API key",
)
async def revoke_personal_key(
    key_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> None:
    """Revoke a personal MCP API key owned by the caller."""
    key = await session.get(McpApiKey, key_id)
    if key is None or key.principal_id != caller.principal_id or key.owner_kind != "personal_user":
        not_found()

    await revoke_mcp_api_key(
        session,
        key_id=key_id,
        caller_principal_id=caller.principal_id,
    )
