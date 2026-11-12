# ruff: noqa: PLR0913, PLR0917
"""Test fixture helpers for setting up workspaces, principals, and ACLs."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def create_workspace(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Test Workspace",
) -> uuid.UUID:
    """Create a workspace and return its ID."""
    ws_slug = slug or f"ws-{uuid.uuid4().hex[:12]}"
    row = await session.execute(
        text("INSERT INTO workspaces (slug, name) VALUES (:slug, :name) RETURNING id"),
        {"slug": ws_slug, "name": name},
    )
    return cast("uuid.UUID", row.scalar_one())


async def create_user(
    session: AsyncSession,
    ws_id: uuid.UUID,
    *,
    handle: str,
    display_name: str,
    email: str | None = None,
    status: str = "ACTIVE",
) -> uuid.UUID:
    """Create a user principal with matching objects and users entries."""
    user_email = email or f"{handle.lstrip('@')}@example.com"
    clean_handle = handle.lstrip("@")

    p_row = await session.execute(
        text(
            "INSERT INTO principals (workspace_id, principal_type, status, display_name) "
            "VALUES (:ws_id, 'USER', :status, :name) RETURNING id"
        ),
        {"ws_id": ws_id, "status": status, "name": display_name},
    )
    p_id = cast("uuid.UUID", p_row.scalar_one())

    await session.execute(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws_id, NULL, :ckey, :name, :p_id, :p_id"
            ")"
        ),
        {"ws_id": ws_id, "ckey": clean_handle, "name": display_name, "p_id": p_id},
    )

    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, :email)"
        ),
        {"id": p_id, "ws_id": ws_id, "email": user_email},
    )

    return p_id


async def create_group(
    session: AsyncSession,
    ws_id: uuid.UUID,
    name: str,
    *,
    external_source: str | None = None,
    external_id: str | None = None,
    status: str = "ACTIVE",
) -> uuid.UUID:
    """Create a group principal with matching groups row."""
    p_row = await session.execute(
        text(
            "INSERT INTO principals (workspace_id, principal_type, status, display_name) "
            "VALUES (:ws_id, 'GROUP', :status, :name) RETURNING id"
        ),
        {"ws_id": ws_id, "status": status, "name": name},
    )
    g_id = cast("uuid.UUID", p_row.scalar_one())

    await session.execute(
        text(
            "INSERT INTO groups ("
            "  id, principal_type, workspace_id, name, external_source, external_id"
            ") VALUES (:id, 'GROUP', :ws_id, :name, :ext_src, :ext_id)"
        ),
        {
            "id": g_id,
            "ws_id": ws_id,
            "name": name,
            "ext_src": external_source,
            "ext_id": external_id,
        },
    )
    return g_id


async def create_agent(
    session: AsyncSession,
    ws_id: uuid.UUID,
    display_name: str,
    *,
    principal_type: str = "AGENT",
    status: str = "ACTIVE",
) -> uuid.UUID:
    """Create an agent or service principal."""
    p_row = await session.execute(
        text(
            "INSERT INTO principals (workspace_id, principal_type, status, display_name) "
            "VALUES (:ws_id, :pt, :status, :name) RETURNING id"
        ),
        {"ws_id": ws_id, "pt": principal_type, "status": status, "name": display_name},
    )
    return cast("uuid.UUID", p_row.scalar_one())


async def create_project(
    session: AsyncSession,
    ws_id: uuid.UUID,
    *,
    identifier: str = "PRJ",
    name: str = "Test Project",
    created_by_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Register and create a project in the database."""
    creator_id = created_by_id or uuid.uuid4()
    reg_row = await session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws_id, NULL, :identifier, :name, :u_id"
            ")"
        ),
        {"ws_id": ws_id, "identifier": identifier, "name": name, "u_id": creator_id},
    )
    proj_id = cast("uuid.UUID", reg_row.scalar_one())
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws_id, :identifier, :name)"
        ),
        {"id": proj_id, "ws_id": ws_id, "identifier": identifier, "name": name},
    )
    return proj_id


async def create_registered_object(
    session: AsyncSession,
    ws_id: uuid.UUID,
    *,
    kind: str = "issue",
    key: str = "KAN-1",
    title: str = "Test Object",
    project_id: uuid.UUID | None = None,
    created_by_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Register an entity directly into the objects spine."""
    creator_id = created_by_id or uuid.uuid4()
    row = await session.execute(
        text(
            "SELECT register_object("
            "  CAST(:kind AS object_kind), :ws_id, :proj_id, :key, :title, :u_id"
            ")"
        ),
        {
            "kind": kind,
            "ws_id": ws_id,
            "proj_id": project_id,
            "key": key,
            "title": title,
            "u_id": creator_id,
        },
    )
    return cast("uuid.UUID", row.scalar_one())


async def add_role_binding(
    session: AsyncSession,
    ws_id: uuid.UUID,
    principal_id: uuid.UUID,
    role: str,
    scope_type: str = "project",
    project_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Add a role binding (SERVER, WORKSPACE, or PROJECT level)."""
    row = await session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :p_id, CAST(:role AS rbac_role), :scope, :proj_id) RETURNING id"
        ),
        {
            "ws_id": ws_id,
            "p_id": principal_id,
            "role": role,
            "scope": scope_type,
            "proj_id": project_id,
        },
    )
    return cast("uuid.UUID", row.scalar_one())


async def add_acl_entry(
    session: AsyncSession,
    ws_id: uuid.UUID,
    object_id: uuid.UUID,
    principal_id: uuid.UUID,
    *,
    effect: str = "ALLOW",
    capability_mask: int = 1,
    created_by_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Insert or upsert a resource ACL entry."""
    row = await session.execute(
        text(
            "INSERT INTO resource_acl_entries ("
            "  workspace_id, object_id, principal_id, effect, capability_mask, created_by_id"
            ") VALUES ("
            "  :ws_id, :obj_id, :p_id, :effect, :mask, :creator_id"
            ") RETURNING id"
        ),
        {
            "ws_id": ws_id,
            "obj_id": object_id,
            "p_id": principal_id,
            "effect": effect,
            "mask": capability_mask,
            "creator_id": created_by_id,
        },
    )
    return cast("uuid.UUID", row.scalar_one())


async def add_group_member(
    session: AsyncSession,
    ws_id: uuid.UUID,
    group_id: uuid.UUID,
    member_id: uuid.UUID,
) -> None:
    """Add a member to a group in principal_group_edges."""
    await session.execute(
        text(
            "INSERT INTO principal_group_edges (workspace_id, group_id, member_id) "
            "VALUES (:ws_id, :g_id, :m_id)"
        ),
        {"ws_id": ws_id, "g_id": group_id, "m_id": member_id},
    )


async def rebuild_era(session: AsyncSession, ws_id: uuid.UUID) -> None:
    """Manually invoke rebuild_effective_access_for_workspace."""
    await session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws_id)"),
        {"ws_id": ws_id},
    )
