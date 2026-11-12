"""Database test configuration and role-bound fixtures."""

import uuid
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def bind_ctx(
    session: AsyncSession,
    principal_id: UUID | str | None,
    workspace_id: UUID | str | None,
) -> None:
    """Set transaction-local principal and workspace context (Section 3.3)."""
    p_str = str(principal_id) if principal_id is not None else ""
    w_str = str(workspace_id) if workspace_id is not None else ""
    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true)"
        ),
        {"p_id": p_str, "w_id": w_str},
    )


_WORKSPACE_ADMINS: dict[uuid.UUID, uuid.UUID] = {}


async def bootstrap_workspace_admin(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Test Workspace",
    *,
    workspace_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision a workspace and its administrative principal under admin authority.

    Restores the original session authorization upon completion.
    """
    orig_user = await session.scalar(text("SELECT current_user"))
    ws_slug = slug or f"ws-{uuid.uuid4().hex[:12]}"
    ws_id = workspace_id or uuid.uuid4()
    admin_id = uuid.uuid4()

    await session.execute(text("RESET SESSION AUTHORIZATION"))
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": ws_slug, "name": name},
    )
    await session.execute(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws_id, NULL, :ckey, 'Admin User', :uid, :id"
            ")"
        ),
        {"ws_id": ws_id, "ckey": f"usr-{admin_id.hex[:8]}", "uid": admin_id, "id": admin_id},
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
            "VALUES (:id, :ws_id, 'USER', 'Admin User')"
        ),
        {"id": admin_id, "ws_id": ws_id},
    )
    await session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
        {"id": admin_id, "ws_id": ws_id, "email": f"admin-{admin_id.hex[:6]}@example.com"},
    )
    await session.execute(
        text(
            "INSERT INTO role_bindings (principal_id, workspace_id, role, scope_type, project_id) "
            "VALUES (:p_id, :ws_id, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"p_id": admin_id, "ws_id": ws_id},
    )

    _WORKSPACE_ADMINS[ws_id] = admin_id
    if orig_user == "kanban_app":
        await session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
        await bind_ctx(session, principal_id=admin_id, workspace_id=ws_id)
        cur = await session.scalar(text("SELECT current_user"))
        assert cur == "kanban_app"
    else:
        await session.execute(text(f"SET LOCAL SESSION AUTHORIZATION {orig_user}"))
        await bind_ctx(session, principal_id=admin_id, workspace_id=ws_id)
        cur = await session.scalar(text("SELECT current_user"))
        assert cur == orig_user
    return ws_id, admin_id


async def bind_workspace_admin(session: AsyncSession, workspace_id: uuid.UUID) -> uuid.UUID:
    """Bind RLS session context to the workspace admin for the given workspace."""
    admin_id = _WORKSPACE_ADMINS.get(workspace_id)
    if not admin_id:
        await session.execute(text("RESET SESSION AUTHORIZATION"))
        admin_id = await session.scalar(
            text(
                "SELECT principal_id FROM role_bindings "
                "WHERE workspace_id = :ws AND role = 'WORKSPACE_ADMIN' LIMIT 1"
            ),
            {"ws": workspace_id},
        )
        if admin_id:
            _WORKSPACE_ADMINS[workspace_id] = admin_id
    assert isinstance(admin_id, uuid.UUID), f"No admin found for workspace {workspace_id}"
    await bind_ctx(session, principal_id=admin_id, workspace_id=workspace_id)
    return admin_id


@pytest.fixture
def superuser_session(db_session: AsyncSession) -> AsyncSession:
    """Provide session with default superuser / maintenance privileges."""
    return db_session


@pytest.fixture
async def app_session(db_session: AsyncSession) -> AsyncSession:
    """Provide session switched to least-privilege kanban_app role."""
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    return db_session
