# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for MCP API keys administration (KB-P4-02a, S11.1)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for Pydantic and type annotations
from datetime import datetime  # noqa: TC003  # Runtime import required for Pydantic type annotations
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.mcp_api_key import McpApiKey
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException, not_found
from kanban.security.mcp_keys import (
    mint_mcp_api_key,
    revoke_mcp_api_key,
)

router = APIRouter(tags=["admin-mcp-keys"])

_REQUIRED_AAL_LEVEL: Final[int] = 2

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


class McpApiKeyMintRequest(BaseModel):
    """Payload for minting a surface-bound MCP API key."""

    model_config = ConfigDict(extra="forbid")

    surface: Literal["agent", "docs", "admin"]
    scopes: list[str] = Field(min_length=1)
    principal_id: uuid.UUID | None = None
    expires_in_days: int | None = Field(default=None, ge=1, le=365)
    expires_at: datetime | None = None


class McpApiKeyMintResponse(BaseModel):
    """Response returned exactly once when an MCP API key is minted."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    token: str
    workspace_id: uuid.UUID
    principal_id: uuid.UUID
    surface: str
    key_prefix: str
    display_hint: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


class McpApiKeyResponse(BaseModel):
    """Metadata response for an existing MCP API key (without plaintext token)."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    workspace_id: uuid.UUID
    principal_id: uuid.UUID
    surface: str
    key_prefix: str
    display_hint: str
    scopes: list[str]
    created_by_id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


async def require_admin_aal2(caller: PrincipalContext, session: AsyncSession) -> None:
    """Enforce AAL2 authentication and workspace/server admin role."""
    if caller.aal_level < _REQUIRED_AAL_LEVEL:
        raise ProblemException(
            code="AAL2_REQUIRED",
            status=403,
            title="AAL2 Required",
            detail="Managing MCP API keys requires AAL2 authentication.",
        )

    stmt = text("SELECT app_principal_has_role(NULL, CAST(:roles AS text[]))")
    roles = ["SERVER_ADMIN", "WORKSPACE_ADMIN"]
    is_admin = (await session.execute(stmt, {"roles": roles})).scalar_one()
    if not is_admin:
        raise ProblemException(
            code="FORBIDDEN",
            status=403,
            title="Forbidden",
            detail="Caller lacks required workspace admin role.",
        )


@router.post(
    "/admin/mcp-keys",
    status_code=status.HTTP_201_CREATED,
    response_model=McpApiKeyMintResponse,
    summary="Mint a scoped MCP API key",
)
async def mint_key(
    body: McpApiKeyMintRequest,
    caller: Caller,
    session: Session,
    response: Response,
) -> McpApiKeyMintResponse:
    """Mint a surface-bound MCP API key and return plaintext token once."""
    await require_admin_aal2(caller, session)

    target_principal_id = body.principal_id or caller.principal_id

    key_record, plaintext_token = await mint_mcp_api_key(
        session,
        workspace_id=caller.workspace_id,
        principal_id=target_principal_id,
        surface=body.surface,
        scopes=body.scopes,
        created_by_id=caller.principal_id,
        expires_at=body.expires_at,
        expires_in_days=body.expires_in_days,
    )

    response.headers["Location"] = f"/api/v1/admin/mcp-keys/{key_record.id}"

    return McpApiKeyMintResponse(
        id=key_record.id,
        token=plaintext_token,
        workspace_id=key_record.workspace_id,
        principal_id=key_record.principal_id,
        surface=key_record.surface,
        key_prefix=key_record.key_prefix,
        display_hint=key_record.display_hint,
        scopes=list(key_record.scopes),
        created_at=key_record.created_at,
        expires_at=key_record.expires_at,
        revoked_at=key_record.revoked_at,
        last_used_at=key_record.last_used_at,
    )


@router.get(
    "/admin/mcp-keys",
    response_model=list[McpApiKeyResponse],
    summary="List MCP API keys in workspace",
)
async def list_keys(
    caller: Caller,
    session: Session,
    surface: Annotated[str | None, Query(description="Optional surface filter")] = None,
) -> list[McpApiKeyResponse]:
    """List metadata for MCP API keys belonging to the workspace."""
    await require_admin_aal2(caller, session)

    stmt = select(McpApiKey).where(McpApiKey.workspace_id == caller.workspace_id)
    if surface:
        stmt = stmt.where(McpApiKey.surface == surface)
    stmt = stmt.order_by(McpApiKey.created_at.desc())

    result = await session.execute(stmt)
    records = result.scalars().all()

    return [
        McpApiKeyResponse(
            id=k.id,
            workspace_id=k.workspace_id,
            principal_id=k.principal_id,
            surface=k.surface,
            key_prefix=k.key_prefix,
            display_hint=k.display_hint,
            scopes=list(k.scopes),
            created_by_id=k.created_by_id,
            created_at=k.created_at,
            expires_at=k.expires_at,
            revoked_at=k.revoked_at,
            last_used_at=k.last_used_at,
        )
        for k in records
    ]


@router.delete(
    "/admin/mcp-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an MCP API key",
)
async def revoke_key(
    key_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> None:
    """Revoke an MCP API key by ID."""
    await require_admin_aal2(caller, session)

    key = await session.get(McpApiKey, key_id)
    if key is None or key.workspace_id != caller.workspace_id:
        not_found()

    await revoke_mcp_api_key(
        session,
        key_id=key_id,
        caller_principal_id=caller.principal_id,
    )
