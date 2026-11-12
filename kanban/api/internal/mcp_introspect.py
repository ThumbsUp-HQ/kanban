# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Internal MCP token introspection endpoint (KB-P4-02a, S11.1)."""

from __future__ import annotations

import uuid  # noqa: TC003  # Runtime import required for Pydantic type annotations
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002  # Runtime import required for FastAPI Depends

from kanban.api.problems import ProblemException
from kanban.security.mcp_keys import (
    introspect_subject_token,
    verify_internal_mcp_auth_header,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

router = APIRouter(tags=["internal-mcp"])


class McpIntrospectRequest(BaseModel):
    """Payload for introspecting an MCP bearer token."""

    model_config = ConfigDict(extra="ignore")

    token: str
    surface: str | None = None


class McpIntrospectResponse(BaseModel):
    """Introspection result payload conforming to S11.1."""

    model_config = ConfigDict(extra="ignore")

    active: bool
    principal_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    surface: str | None = None
    scopes: list[str] | None = None
    token_kind: str | None = None
    reason: str | None = None


def verify_internal_auth(request: Request) -> None:
    """Enforce internal gateway HMAC or mTLS client authentication."""
    auth_header = request.headers.get("x-kb-internal-auth")
    if verify_internal_mcp_auth_header(auth_header):
        return

    client_cert = request.headers.get("x-ssl-client-cert") or request.scope.get("client_cert")
    if client_cert:
        return

    raise ProblemException(
        code="AUTHENTICATION_REQUIRED",
        status=401,
        title="Authentication Required",
        detail="Internal gateway authentication header or client certificate required.",
    )


async def get_internal_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield database session for internal introspection."""
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        msg = "Session factory not configured on app.state"
        raise RuntimeError(msg)

    async with session_factory.sessionmaker() as session:
        session.info["rls_bound"] = True
        yield session


@router.post(
    "/internal/v1/mcp/introspect",
    response_model=McpIntrospectResponse,
    summary="Introspect MCP bearer token",
    dependencies=[Depends(verify_internal_auth)],
)
@router.post(
    "/internal/mcp/introspect",
    response_model=McpIntrospectResponse,
    include_in_schema=False,
    dependencies=[Depends(verify_internal_auth)],
)
async def introspect_token(
    body: McpIntrospectRequest,
    session: Annotated[AsyncSession, Depends(get_internal_session)],
) -> McpIntrospectResponse:
    """Introspect bearer token digest against database and return active state."""
    result = await introspect_subject_token(session, token=body.token, surface=body.surface)
    return McpIntrospectResponse(
        active=result.active,
        principal_id=result.principal_id,
        workspace_id=result.workspace_id,
        surface=result.surface,
        scopes=result.scopes,
        token_kind=result.token_kind,
        reason=result.reason,
    )
