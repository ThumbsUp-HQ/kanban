# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unified canonical REST API router for MCP keys (KB-P3-AUDIT-25 / KAN-31).

Mounts canonical /api/v1/mcp-keys supporting both self-service (view=mine)
and tier-matched governance (view=governance) for project, workspace, and server scopes.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime  # noqa: TC003  # Runtime import required for Pydantic type annotations
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.mcp_api_key import McpApiKey
from database.models.projects import Project
from kanban.api.deps import PrincipalContext, get_principal, get_rls_session
from kanban.api.problems import ProblemException, not_found
from kanban.security.mcp_keys import (
    mint_mcp_api_key,
    revoke_mcp_api_key,
)

REQUIRED_AAL2_LEVEL: Final[int] = 2

router = APIRouter(prefix="/mcp-keys", tags=["mcp-keys"])

Caller = Annotated[PrincipalContext, Depends(get_principal)]
Session = Annotated[AsyncSession, Depends(get_rls_session)]


class UnifiedMcpKeyMintRequest(BaseModel):
    """Payload for minting a scoped MCP API key."""

    model_config = ConfigDict(extra="forbid")

    surface: Literal["agent", "docs", "admin"]
    scopes: list[str] | None = None
    label: str | None = Field(default=None, max_length=120)
    principal_id: uuid.UUID | None = None
    expires_in_days: int | None = Field(default=60, ge=1, le=365)
    expires_at: datetime | None = None
    scope_tier: Literal["global", "workspace", "project", "server"] = "workspace"
    owner_kind: Literal["service_bot", "personal_user"] = "personal_user"
    workspace_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    project_ref: str | None = None
    allowed_workspace_ids: list[uuid.UUID] | None = None
    allowed_project_ids: list[uuid.UUID] | None = None
    allowed_projects: list[str] | None = None
    capability_mask: int = Field(default=7, ge=1, le=255)
    allowed_tools: list[str] | None = None
    disabled_tools: list[str] = Field(default_factory=list)
    allowed_cidrs: list[str] | None = None
    unlimited: bool = False
    confirm_unlimited: bool = False


class UnifiedMcpApiKeyResponse(BaseModel):
    """Consistent metadata response for an MCP API key without secret hash."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    label: str | None = None
    workspace_id: uuid.UUID | None = None
    principal_id: uuid.UUID
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
    project_id: uuid.UUID | None = None
    allowed_workspace_ids: list[uuid.UUID] | None = None
    allowed_project_ids: list[uuid.UUID] | None = None
    allowed_projects: list[str] | None = None
    capability_mask: int = 7
    allowed_tools: list[str] | None = None
    disabled_tools: list[str] = Field(default_factory=list)
    allowed_cidrs: list[str] | None = None


class UnifiedMcpKeyMintResponse(UnifiedMcpApiKeyResponse):
    """Response returned exactly once carrying the one-time plaintext token."""

    token: str
    raw_key: str | None = None


async def _resolve_project_id_to_key_map(
    session: Session,
    project_ids: set[uuid.UUID],
) -> dict[uuid.UUID, str]:
    if not project_ids:
        return {}
    with contextlib.suppress(Exception):
        stmt = select(Project.id, Project.identifier).where(Project.id.in_(project_ids))
        rows = (await session.execute(stmt)).all()
        return {row[0]: row[1] for row in rows}
    return {}


def _resolve_key_project_list(
    key_item: McpApiKey,
    id_to_key: dict[uuid.UUID, str],
) -> list[str] | None:
    if key_item.allowed_project_ids:
        res = [id_to_key.get(p, str(p)) for p in key_item.allowed_project_ids]
        return res or None
    if key_item.project_id:
        return [id_to_key.get(key_item.project_id, str(key_item.project_id))]
    return None


@router.get(
    "",
    response_model=list[UnifiedMcpApiKeyResponse],
    summary="List MCP API keys (mine or governance)",
)
async def list_unified_mcp_keys(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917
    caller: Caller,
    session: Session,
    view: Annotated[
        Literal["mine", "governance"],
        Query(description="View mode: mine (personal keys) or governance (scoped keys)"),
    ] = "mine",
    scope_tier: Annotated[
        str | None,
        Query(description="Filter by scope tier (project, workspace, server, or global)"),
    ] = None,
    project_ref: Annotated[
        str | None,
        Query(description="Filter by target project key or UUID"),
    ] = None,
    surface: Annotated[
        str | None,
        Query(description="Filter by surface (agent, docs, admin)"),
    ] = None,
) -> list[UnifiedMcpApiKeyResponse]:
    """Retrieve MCP API keys matching view, scope, and principal permissions."""
    normalized_scope_tier = "global" if scope_tier in ("global", "server") else scope_tier

    resolved_project_id: uuid.UUID | None = None
    if project_ref:
        p_ref_str = str(project_ref).strip()
        resolved_project_id = (
            await session.execute(
                text("SELECT resolve_project_id_by_key_or_id(:ws_id, :ident)"),
                {"ws_id": caller.workspace_id, "ident": p_ref_str},
            )
        ).scalar_one_or_none()
        if not resolved_project_id:
            try:
                resolved_project_id = uuid.UUID(p_ref_str)
            except ValueError:
                resolved_project_id = None
        if not resolved_project_id:
            return []

    stmt = select(McpApiKey)

    if view == "mine":
        stmt = stmt.where(McpApiKey.principal_id == caller.principal_id)
        if normalized_scope_tier:
            stmt = stmt.where(McpApiKey.scope_tier == normalized_scope_tier)
        if resolved_project_id:
            stmt = stmt.where(
                or_(
                    McpApiKey.project_id == resolved_project_id,
                    McpApiKey.allowed_project_ids.contains([resolved_project_id]),
                )
            )
    else:
        # Governance view: strictly requires fresh AAL2 + administrative role
        if caller.aal_level < REQUIRED_AAL2_LEVEL:
            raise ProblemException(
                code="AAL2_REQUIRED",
                status=403,
                title="AAL2 Required",
                detail="Accessing governance MCP keys requires fresh AAL2 authentication.",
            )

        stmt_sa = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
        is_server_admin = bool((await session.execute(stmt_sa)).scalar_one())
        stmt_wa = text(
            "SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])"
        )
        is_workspace_admin = bool((await session.execute(stmt_wa)).scalar_one())

        if is_server_admin:
            stmt = stmt.where(
                or_(
                    McpApiKey.workspace_id == caller.workspace_id,
                    McpApiKey.workspace_id.is_(None),
                )
            )
        elif is_workspace_admin:
            stmt = stmt.where(McpApiKey.workspace_id == caller.workspace_id)
        else:
            # PROJECT_ADMIN only: strictly restricted to scope_tier == "project" targeting projects
            # where the caller holds Capability.ADMIN (never workspace-wide or other projects' keys)
            if normalized_scope_tier is not None and normalized_scope_tier != "project":
                return []

            stmt_admin_projs = select(Project.id).where(
                Project.workspace_id == caller.workspace_id,
                or_(
                    text("app_has_object_capability(projects.id, 64)"),
                    text(
                        "app_principal_has_role(projects.id, "
                        "ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])"
                    ),
                ),
            )
            admin_proj_ids = list((await session.execute(stmt_admin_projs)).scalars().all())
            if not admin_proj_ids:
                raise ProblemException(
                    code="FORBIDDEN",
                    status=403,
                    title="Forbidden",
                    detail="Caller possesses no project administration permissions in workspace.",
                )

            stmt = stmt.where(
                McpApiKey.workspace_id == caller.workspace_id,
                McpApiKey.scope_tier == "project",
                McpApiKey.project_id.in_(admin_proj_ids),
            )

        if normalized_scope_tier:
            stmt = stmt.where(McpApiKey.scope_tier == normalized_scope_tier)
        if resolved_project_id:
            stmt = stmt.where(
                or_(
                    McpApiKey.project_id == resolved_project_id,
                    McpApiKey.allowed_project_ids.contains([resolved_project_id]),
                )
            )

    if surface:
        stmt = stmt.where(McpApiKey.surface == surface)

    stmt = stmt.order_by(McpApiKey.created_at.desc())
    records = (await session.execute(stmt)).scalars().all()

    all_proj_ids: set[uuid.UUID] = set()
    for k in records:
        if k.allowed_project_ids:
            all_proj_ids.update(k.allowed_project_ids)
        if k.project_id:
            all_proj_ids.add(k.project_id)

    id_to_key = await _resolve_project_id_to_key_map(session, all_proj_ids)

    return [
        UnifiedMcpApiKeyResponse(
            id=k.id,
            label=k.label,
            workspace_id=k.workspace_id,
            principal_id=k.principal_id,
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
            project_id=k.project_id,
            allowed_workspace_ids=k.allowed_workspace_ids,
            allowed_project_ids=k.allowed_project_ids,
            allowed_projects=_resolve_key_project_list(k, id_to_key),
            capability_mask=k.capability_mask,
            allowed_tools=k.allowed_tools,
            disabled_tools=list(k.disabled_tools or []),
            allowed_cidrs=([str(c) for c in k.allowed_cidrs] if k.allowed_cidrs else None),
        )
        for k in records
    ]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=UnifiedMcpKeyMintResponse,
    summary="Mint an MCP API key",
)
async def mint_unified_mcp_key(  # noqa: C901
    body: UnifiedMcpKeyMintRequest,
    caller: Caller,
    session: Session,
    response: Response,
) -> UnifiedMcpKeyMintResponse:
    """Mint a scoped MCP API key returning the one-time plaintext token."""
    resolved_scope_tier = "global" if body.scope_tier in ("global", "server") else body.scope_tier
    target_workspace_id = None if resolved_scope_tier == "global" else caller.workspace_id
    target_principal_id = (
        body.principal_id
        if (body.owner_kind == "service_bot" and body.principal_id is not None)
        else caller.principal_id
    )

    allowed_project_ids = list(body.allowed_project_ids or [])
    project_refs = list(body.allowed_projects or [])
    if body.project_ref and body.project_ref not in project_refs:
        project_refs.append(body.project_ref)

    if project_refs:
        for p_ref in project_refs:
            p_ref_str = str(p_ref).strip()
            resolved_p = (
                await session.execute(
                    text("SELECT resolve_project_id_by_key_or_id(:ws_id, :ident)"),
                    {"ws_id": target_workspace_id, "ident": p_ref_str},
                )
            ).scalar_one_or_none()
            if resolved_p and resolved_p not in allowed_project_ids:
                allowed_project_ids.append(resolved_p)
            elif not resolved_p:
                try:
                    p_uuid = uuid.UUID(p_ref_str)
                    if p_uuid not in allowed_project_ids:
                        allowed_project_ids.append(p_uuid)
                except ValueError:
                    pass

    target_project_id = body.project_id
    if target_project_id is None and resolved_scope_tier == "project" and allowed_project_ids:
        target_project_id = allowed_project_ids[0]

    effective_scopes = body.scopes or [f"{body.surface}:read", f"{body.surface}:write"]

    key_record, plaintext_token = await mint_mcp_api_key(
        session,
        workspace_id=target_workspace_id,
        principal_id=target_principal_id,
        surface=body.surface,
        scopes=effective_scopes,
        created_by_id=caller.principal_id,
        expires_at=body.expires_at,
        expires_in_days=body.expires_in_days,
        scope_tier=resolved_scope_tier,
        owner_kind=body.owner_kind,
        project_id=target_project_id,
        allowed_workspace_ids=body.allowed_workspace_ids,
        allowed_project_ids=allowed_project_ids or None,
        capability_mask=body.capability_mask,
        allowed_tools=body.allowed_tools,
        disabled_tools=body.disabled_tools,
        allowed_cidrs=body.allowed_cidrs,
        unlimited=body.unlimited,
        confirm_unlimited=body.confirm_unlimited,
        caller_aal_level=caller.aal_level,
        label=body.label,
    )

    response.headers["Location"] = f"/api/v1/mcp-keys/{key_record.id}"

    resolved_proj_keys: list[str] = []
    if key_record.allowed_project_ids:
        keys_res = (
            await session.execute(
                text("SELECT resolve_project_keys(:p_ids)"),
                {"p_ids": list(key_record.allowed_project_ids)},
            )
        ).scalar_one_or_none()
        if keys_res:
            resolved_proj_keys = [str(k) for k in keys_res]

    return UnifiedMcpKeyMintResponse(
        id=key_record.id,
        token=plaintext_token,
        raw_key=plaintext_token,
        label=key_record.label,
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
        scope_tier=key_record.scope_tier,
        owner_kind=key_record.owner_kind,
        project_id=key_record.project_id,
        allowed_workspace_ids=key_record.allowed_workspace_ids,
        allowed_project_ids=key_record.allowed_project_ids,
        allowed_projects=(
            resolved_proj_keys
            or (
                [str(p) for p in key_record.allowed_project_ids]
                if key_record.allowed_project_ids
                else None
            )
        ),
        capability_mask=key_record.capability_mask,
        allowed_tools=key_record.allowed_tools,
        disabled_tools=list(key_record.disabled_tools or []),
        allowed_cidrs=(
            [str(c) for c in key_record.allowed_cidrs] if key_record.allowed_cidrs else None
        ),
    )


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an MCP API key",
)
async def revoke_unified_mcp_key(
    key_id: uuid.UUID,
    caller: Caller,
    session: Session,
) -> None:
    """Revoke an active MCP API key with owner or tier-matched governance authority."""
    key = await session.get(McpApiKey, key_id)
    if key is None:
        not_found()

    is_owner = key.principal_id == caller.principal_id

    if not is_owner:
        if caller.aal_level < REQUIRED_AAL2_LEVEL:
            raise ProblemException(
                code="AAL2_REQUIRED",
                status=403,
                title="AAL2 Required",
                detail="Revoking keys under governance requires fresh AAL2 authentication.",
            )

        stmt_sa = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
        is_server_admin = bool((await session.execute(stmt_sa)).scalar_one())
        stmt_wa = text(
            "SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN'])"
        )
        is_workspace_admin = bool((await session.execute(stmt_wa)).scalar_one())

        if is_server_admin:
            if key.workspace_id is not None and key.workspace_id != caller.workspace_id:
                not_found()
        elif is_workspace_admin:
            if key.workspace_id != caller.workspace_id:
                not_found()
        else:
            # PROJECT_ADMIN only: strictly restricted to scope_tier == "project" targeting
            # projects where caller holds Capability.ADMIN
            if (
                key.scope_tier != "project"
                or key.workspace_id != caller.workspace_id
                or key.project_id is None
            ):
                not_found()

            stmt_can_admin = text(
                "SELECT app_has_object_capability(:p_id, 64) OR "
                "app_principal_has_role(:p_id, "
                "ARRAY['SERVER_ADMIN', 'WORKSPACE_ADMIN', 'PROJECT_ADMIN'])"
            )
            can_admin = bool(
                (await session.execute(stmt_can_admin, {"p_id": key.project_id})).scalar_one()
            )
            if not can_admin:
                not_found()

    await revoke_mcp_api_key(
        session,
        key_id=key_id,
        caller_principal_id=caller.principal_id,
    )
