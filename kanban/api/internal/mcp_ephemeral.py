# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Internal ephemeral MCP token minting and revocation endpoints (KB-P4-13, KAN-63, S14.3)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for Pydantic type annotations
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
)

from kanban.api.internal.mcp_introspect import get_internal_session
from kanban.security.ephemeral_mcp_tokens import (
    mint_ephemeral_token,
    revoke_ephemeral_tokens_by_execution,
)
from kanban.security.service_auth import verify_internal_service_auth

router = APIRouter(tags=["internal-mcp-ephemeral"])


class MintEphemeralTokenRequest(BaseModel):
    """Payload for minting a short-lived ephemeral MCP token."""

    model_config = ConfigDict(extra="ignore")

    workspace_id: uuid.UUID
    execution_id: uuid.UUID
    invoking_principal_id: uuid.UUID
    agent_principal_id: uuid.UUID
    project_id: uuid.UUID
    allowed_tools: list[str] | None = None
    ttl_seconds: int = 120
    max_calls: int = 25


class MintEphemeralTokenResponse(BaseModel):
    """Result returned after minting ephemeral token."""

    model_config = ConfigDict(extra="ignore")

    token: str
    expires_at: str
    max_calls: int
    allowed_tools: list[str]


class RevokeEphemeralTokenResponse(BaseModel):
    """Result returned after revoking execution tokens."""

    model_config = ConfigDict(extra="ignore")

    revoked_count: int


async def verify_mint_service_principal(request: Request) -> None:
    """Enforce that only cryptographically verified agent-runtime or kanban-api can mint tokens.

    mcp-gateway is strictly forbidden (HTTP 403).
    Unauthenticated or header-spoofed callers are rejected (HTTP 401).
    """
    body_bytes = await request.body()
    verify_internal_service_auth(
        request,
        allowed_principals=("agent-runtime", "kanban-api"),
        body_bytes=body_bytes,
    )


async def verify_revoke_auth(request: Request) -> None:
    """Enforce verified internal service authentication for token revocation."""
    body_bytes = await request.body()
    verify_internal_service_auth(
        request,
        allowed_principals=("agent-runtime", "kanban-api", "mcp-gateway"),
        body_bytes=body_bytes,
    )


async def _commit_if_pooled_engine(request: Request, session: AsyncSession) -> None:
    """Commit transaction when session_factory is backed by a pooled AsyncEngine."""
    sf = getattr(request.app.state, "session_factory", None)
    engine = getattr(sf, "_engine", None) if sf is not None else None
    if isinstance(engine, AsyncEngine):
        await session.commit()


@router.post(
    "/internal/v1/mcp/ephemeral-tokens",
    response_model=MintEphemeralTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mint short-lived ephemeral read-only MCP token",
    dependencies=[Depends(verify_mint_service_principal)],
)
async def mint_token_endpoint(
    request: Request,
    body: MintEphemeralTokenRequest,
    session: Annotated[AsyncSession, Depends(get_internal_session)],
) -> MintEphemeralTokenResponse:
    """Mint ephemeral token bound to execution_id and Invoker ∩ Agent ∩ Project."""
    record, plaintext = await mint_ephemeral_token(
        session,
        workspace_id=body.workspace_id,
        execution_id=body.execution_id,
        invoking_principal_id=body.invoking_principal_id,
        agent_principal_id=body.agent_principal_id,
        project_id=body.project_id,
        allowed_tools=body.allowed_tools,
        ttl_seconds=body.ttl_seconds,
        max_calls=body.max_calls,
    )
    await _commit_if_pooled_engine(request, session)
    return MintEphemeralTokenResponse(
        token=plaintext,
        expires_at=record.expires_at.isoformat(),
        max_calls=record.max_calls,
        allowed_tools=record.allowed_tools,
    )


@router.post(
    "/internal/v1/mcp/ephemeral-tokens/by-execution/{execution_id}/revoke",
    response_model=RevokeEphemeralTokenResponse,
    summary="Revoke active ephemeral tokens by execution ID",
    dependencies=[Depends(verify_revoke_auth)],
)
async def revoke_tokens_endpoint(
    request: Request,
    execution_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_internal_session)],
) -> RevokeEphemeralTokenResponse:
    """Revoke all active tokens for the specified execution ID."""
    count = await revoke_ephemeral_tokens_by_execution(session, execution_id=execution_id)
    await _commit_if_pooled_engine(request, session)
    return RevokeEphemeralTokenResponse(revoked_count=count)
