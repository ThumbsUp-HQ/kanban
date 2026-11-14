# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Internal ephemeral MCP token minting and revocation endpoints (KB-P4-13, S14.3)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for Pydantic type annotations
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002  # Runtime import required for FastAPI Depends

from kanban.api.internal.mcp_introspect import get_internal_session
from kanban.api.problems import ProblemException
from kanban.security.ephemeral_mcp_tokens import (
    mint_ephemeral_token,
    revoke_ephemeral_tokens_by_execution,
)
from kanban.security.mcp_keys import verify_internal_mcp_auth_header

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


def verify_mint_service_principal(request: Request) -> None:
    """Enforce that only agent-runtime or kanban-api can mint ephemeral tokens.

    mcp-gateway is strictly forbidden (HTTP 403).
    Unauthenticated callers are rejected (HTTP 401).
    """
    service_principal = (
        request.headers.get("x-kb-service-principal")
        or request.headers.get("x-client-cert-cn")
        or request.headers.get("x-ssl-client-cn")
    )
    auth_header = request.headers.get("x-kb-internal-auth")
    client_cert = request.headers.get("x-ssl-client-cert") or request.scope.get("client_cert")

    # If caller identifies as mcp-gateway or presents mcp-gateway HMAC header -> 403 Forbidden
    if (
        service_principal == "mcp-gateway"
        or (client_cert and "mcp-gateway" in str(client_cert))
        or verify_internal_mcp_auth_header(auth_header)
    ):
        raise ProblemException(
            code="FORBIDDEN",
            status=403,
            title="Forbidden",
            detail="mcp-gateway service principal is forbidden from minting ephemeral tokens.",
        )

    # Require client certificate or valid agent-runtime / kanban-api principal
    if service_principal in ("agent-runtime", "kanban-api"):
        return

    if client_cert:
        return

    raise ProblemException(
        code="AUTHENTICATION_REQUIRED",
        status=401,
        title="Authentication Required",
        detail="Internal agent-runtime or kanban-api client certificate required.",
    )


def verify_revoke_auth(request: Request) -> None:
    """Enforce internal authentication for token revocation."""
    auth_header = request.headers.get("x-kb-internal-auth")
    if verify_internal_mcp_auth_header(auth_header):
        return

    client_cert = request.headers.get("x-ssl-client-cert") or request.scope.get("client_cert")
    if client_cert:
        return

    service_principal = (
        request.headers.get("x-kb-service-principal")
        or request.headers.get("x-client-cert-cn")
        or request.headers.get("x-ssl-client-cn")
    )
    if service_principal in ("agent-runtime", "kanban-api", "mcp-gateway"):
        return

    raise ProblemException(
        code="AUTHENTICATION_REQUIRED",
        status=401,
        title="Authentication Required",
        detail="Internal authentication required to revoke ephemeral tokens.",
    )


@router.post(
    "/internal/v1/mcp/ephemeral-tokens",
    response_model=MintEphemeralTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mint short-lived ephemeral read-only MCP token",
    dependencies=[Depends(verify_mint_service_principal)],
)
async def mint_token_endpoint(
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
    execution_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_internal_session)],
) -> RevokeEphemeralTokenResponse:
    """Revoke all active tokens for the specified execution ID."""
    count = await revoke_ephemeral_tokens_by_execution(session, execution_id=execution_id)
    return RevokeEphemeralTokenResponse(revoked_count=count)
