# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Forensic unit tests for granular RBAC schema, RLS, triggers, and ERA integration.

(KB-GRANULAR-RBAC, KAN-83).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, insert, select, text
from sqlalchemy.exc import DBAPIError

from database.models import (
    EffectiveResourceAccess,
    ObjectKind,
    ObjectRecord,
    PrincipalRoleLabel,
    Project,
    RbacRole,
    RbacRoleModel,
    RbacRolePermission,
    RoleBinding,
    User,
    Workspace,
)
from database.session import RLSContext, bind_rls_context

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _create_workspace_with_user(
    session: AsyncSession,
    slug_prefix: str,
    role: RbacRole = RbacRole.WORKSPACE_ADMIN,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create workspace and active user with role binding under migrator authority."""
    _orig_user = await session.scalar(text("SELECT current_user"))
    await session.execute(text("RESET SESSION AUTHORIZATION"))

    ws_id = uuid.uuid4()
    ws = Workspace(id=ws_id, slug=f"{slug_prefix}-{ws_id.hex[:8]}", name=f"{slug_prefix} Workspace")
    session.add(ws)
    await session.flush()

    # Seed RBAC roles for the workspace
    await session.execute(
        text("SELECT seed_workspace_rbac_roles(:ws_id)"),
        {"ws_id": ws_id},
    )

    u_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, :name, 'ACTIVE')"
        ),
        {"id": u_id, "ws_id": ws_id, "name": f"{slug_prefix} User"},
    )
    u_obj = ObjectRecord(
        id=u_id,
        object_type=ObjectKind.USER,
        workspace_id=ws_id,
        canonical_key=f"usr-{u_id.hex[:12]}",
        display_title=f"{slug_prefix} User",
        created_by_id=u_id,
    )
    session.add(u_obj)
    await session.flush()

    user = User(
        id=u_id,
        object_type=ObjectKind.USER,
        principal_type="USER",
        workspace_id=ws_id,
        email=f"{slug_prefix}@example.com",
    )
    session.add(user)

    rb = RoleBinding(
        workspace_id=ws_id,
        principal_id=u_id,
        role=role,
        scope_type="workspace" if role != RbacRole.SERVER_ADMIN else "server",
        project_id=None,
    )
    session.add(rb)
    await session.flush()

    # Backfill role label
    role_slug = {
        RbacRole.SERVER_ADMIN: "system-admin",
        RbacRole.WORKSPACE_ADMIN: "workspace-admin",
        RbacRole.PROJECT_ADMIN: "project-admin",
        RbacRole.WORKSPACE_MEMBER: "users",
        RbacRole.MEMBER: "users",
        RbacRole.VIEWER: "viewer",
        RbacRole.WORKSPACE_GUEST: "guest",
    }[role]
    r_stmt = select(RbacRoleModel.id).where(
        RbacRoleModel.workspace_id == ws_id,
        RbacRoleModel.slug == role_slug,
    )
    role_id = (await session.execute(r_stmt)).scalar_one()
    prl = PrincipalRoleLabel(
        workspace_id=ws_id,
        principal_id=u_id,
        role_id=role_id,
        project_id=None,
    )
    session.add(prl)
    await session.flush()
    await session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws_id)"),
        {"ws_id": ws_id},
    )

    await session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_rls_context(session, RLSContext(workspace_id=ws_id, principal_id=u_id))

    return ws_id, u_id


@pytest.mark.asyncio
async def test_built_in_roles_seeded(db_session: AsyncSession) -> None:
    """Verify built-in roles and permissions are seeded with correct capability masks."""
    ws_id, _ = await _create_workspace_with_user(db_session, "seed-check")

    stmt = select(RbacRoleModel).where(RbacRoleModel.workspace_id == ws_id)
    roles = (await db_session.execute(stmt)).scalars().all()
    roles_by_slug = {r.slug: r for r in roles}

    assert "system-admin" in roles_by_slug
    assert "workspace-admin" in roles_by_slug
    assert "project-admin" in roles_by_slug
    assert "users" in roles_by_slug
    assert "viewer" in roles_by_slug
    assert "guest" in roles_by_slug

    assert roles_by_slug["system-admin"].base_capability_mask == 255
    assert roles_by_slug["workspace-admin"].base_capability_mask == 255
    assert roles_by_slug["project-admin"].base_capability_mask == 191
    assert roles_by_slug["users"].base_capability_mask == 31
    assert roles_by_slug["viewer"].base_capability_mask == 3
    assert roles_by_slug["guest"].base_capability_mask == 1

    # Check viewer permissions: has view, comment, but NOT attach_files
    viewer_id = roles_by_slug["viewer"].id
    p_stmt = select(RbacRolePermission.permission_key).where(
        RbacRolePermission.role_id == viewer_id
    )
    viewer_perms = set((await db_session.execute(p_stmt)).scalars().all())
    assert viewer_perms == {"issue:view", "issue:comment"}
    assert "field:attach_files" not in viewer_perms


@pytest.mark.asyncio
async def test_tenant_isolation_rls(app_session: AsyncSession) -> None:
    """Verify FORCE RLS isolates rbac_roles and labels across workspaces."""
    ws1_id, u1_id = await _create_workspace_with_user(app_session, "tenant-a")
    ws2_id, _ = await _create_workspace_with_user(app_session, "tenant-b")

    # Drop to kanban_app session bound to ws1
    await bind_rls_context(
        app_session,
        RLSContext(workspace_id=ws1_id, principal_id=u1_id),
    )

    roles = (await app_session.execute(select(RbacRoleModel))).scalars().all()
    assert all(r.workspace_id == ws1_id for r in roles)
    assert not any(r.workspace_id == ws2_id for r in roles)

    labels = (await app_session.execute(select(PrincipalRoleLabel))).scalars().all()
    assert all(label.workspace_id == ws1_id for label in labels)
    assert not any(label.workspace_id == ws2_id for label in labels)


@pytest.mark.asyncio
async def test_rule_1_workspace_admin_cannot_modify_workspace_permissions(
    app_session: AsyncSession,
) -> None:
    """Rule 1: WORKSPACE_ADMIN cannot toggle workspace:* permissions (SQLSTATE 42501)."""
    ws_id, u_id = await _create_workspace_with_user(
        app_session, "rule1-ws", role=RbacRole.WORKSPACE_ADMIN
    )

    # Fetch users role
    stmt = select(RbacRoleModel.id).where(
        RbacRoleModel.workspace_id == ws_id,
        RbacRoleModel.slug == "users",
    )
    users_role_id = (await app_session.execute(stmt)).scalar_one()

    # Drop to kanban_app authority with WORKSPACE_ADMIN context
    await bind_rls_context(
        app_session,
        RLSContext(workspace_id=ws_id, principal_id=u_id),
    )

    # Attempt to grant workspace:create to users role
    with pytest.raises(DBAPIError) as exc_info:
        await app_session.execute(
            insert(RbacRolePermission).values(
                workspace_id=ws_id,
                role_id=users_role_id,
                permission_key="workspace:create",
                effect="ALLOW",
            )
        )
    assert getattr(exc_info.value.orig, "pgcode", None) == "42501"
    assert "WORKSPACE_PERMISSION_LOCKED" in str(exc_info.value)


@pytest.mark.asyncio
async def test_rule_1_workspace_admin_cannot_modify_or_delete_system_admin_role(
    app_session: AsyncSession,
) -> None:
    """Rule 1: WORKSPACE_ADMIN cannot delete or modify system-admin role (SQLSTATE 42501)."""
    ws_id, u_id = await _create_workspace_with_user(
        app_session, "rule1-del", role=RbacRole.WORKSPACE_ADMIN
    )

    stmt = select(RbacRoleModel).where(
        RbacRoleModel.workspace_id == ws_id,
        RbacRoleModel.slug == "system-admin",
    )
    sys_admin = (await app_session.execute(stmt)).scalar_one()

    await bind_rls_context(
        app_session,
        RLSContext(workspace_id=ws_id, principal_id=u_id),
    )

    # Attempt to delete system-admin role
    with pytest.raises(DBAPIError) as exc_info:
        await app_session.execute(delete(RbacRoleModel).where(RbacRoleModel.id == sys_admin.id))
    assert getattr(exc_info.value.orig, "pgcode", None) == "42501"
    assert "WORKSPACE_PERMISSION_LOCKED" in str(exc_info.value)


@pytest.mark.asyncio
async def test_rule_1_workspace_admin_cannot_bind_workspace_permission_role(
    app_session: AsyncSession,
) -> None:
    """Rule 1: WORKSPACE_ADMIN cannot bind system-admin role (ROLE_ESCALATION_DENIED 42501)."""
    ws_id, u_id = await _create_workspace_with_user(
        app_session, "rule1-bind", role=RbacRole.WORKSPACE_ADMIN
    )

    sys_admin_id = (
        await app_session.execute(
            select(RbacRoleModel.id).where(
                RbacRoleModel.workspace_id == ws_id,
                RbacRoleModel.slug == "system-admin",
            )
        )
    ).scalar_one()

    target_user_id = uuid.uuid4()
    await app_session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Target User', 'ACTIVE')"
        ),
        {"id": target_user_id, "ws_id": ws_id},
    )

    await bind_rls_context(
        app_session,
        RLSContext(workspace_id=ws_id, principal_id=u_id),
    )

    with pytest.raises(DBAPIError) as exc_info:
        await app_session.execute(
            insert(PrincipalRoleLabel).values(
                workspace_id=ws_id,
                principal_id=target_user_id,
                role_id=sys_admin_id,
                project_id=None,
            )
        )
    assert getattr(exc_info.value.orig, "pgcode", None) == "42501"
    assert "ROLE_ESCALATION_DENIED" in str(exc_info.value)


@pytest.mark.asyncio
async def test_rule_2_standard_user_cannot_modify_permissions(
    app_session: AsyncSession,
) -> None:
    """Rule 2: Standard User cannot modify issue:* or field:* permissions (42501)."""
    ws_id, u_id = await _create_workspace_with_user(
        app_session, "rule2-user", role=RbacRole.WORKSPACE_MEMBER
    )

    users_role_id = (
        await app_session.execute(
            select(RbacRoleModel.id).where(
                RbacRoleModel.workspace_id == ws_id,
                RbacRoleModel.slug == "users",
            )
        )
    ).scalar_one()

    await bind_rls_context(
        app_session,
        RLSContext(workspace_id=ws_id, principal_id=u_id),
    )

    with pytest.raises(DBAPIError) as exc_info:
        await app_session.execute(
            insert(RbacRolePermission).values(
                workspace_id=ws_id,
                role_id=users_role_id,
                permission_key="issue:delete",
                effect="ALLOW",
            )
        )
    assert getattr(exc_info.value.orig, "pgcode", None) == "42501"
    assert "INSUFFICIENT_CAPABILITY" in str(exc_info.value)


@pytest.mark.asyncio
async def test_server_admin_can_modify_workspace_permissions(
    app_session: AsyncSession,
) -> None:
    """SERVER_ADMIN can toggle workspace:* permissions."""
    ws_id, sa_id = await _create_workspace_with_user(
        app_session, "sa-ws", role=RbacRole.SERVER_ADMIN
    )

    users_role_id = (
        await app_session.execute(
            select(RbacRoleModel.id).where(
                RbacRoleModel.workspace_id == ws_id,
                RbacRoleModel.slug == "users",
            )
        )
    ).scalar_one()

    await bind_rls_context(
        app_session,
        RLSContext(workspace_id=ws_id, principal_id=sa_id),
    )

    # Insert workspace:create_project on users role
    await app_session.execute(
        insert(RbacRolePermission).values(
            workspace_id=ws_id,
            role_id=users_role_id,
            permission_key="workspace:create_project",
            effect="ALLOW",
        )
    )

    # Verify inserted
    perm = (
        await app_session.execute(
            select(RbacRolePermission).where(
                RbacRolePermission.role_id == users_role_id,
                RbacRolePermission.permission_key == "workspace:create_project",
            )
        )
    ).scalar_one_or_none()
    assert perm is not None


@pytest.mark.asyncio
async def test_mask_derivation_and_era_rebuild_additive_union(
    app_session: AsyncSession,
) -> None:
    """Verify base_capability_mask derivation and ERA additive union across multi-role labels."""
    ws_id, u_id = await _create_workspace_with_user(
        app_session, "multi-role", role=RbacRole.WORKSPACE_MEMBER
    )

    await app_session.execute(text("RESET SESSION AUTHORIZATION"))

    # Create a project and object
    p_id = uuid.uuid4()
    p_obj = ObjectRecord(
        id=p_id,
        object_type=ObjectKind.PROJECT,
        workspace_id=ws_id,
        canonical_key="PROJ",
        display_title="Test Project",
        created_by_id=u_id,
    )
    app_session.add(p_obj)
    await app_session.flush()

    project = Project(
        id=p_id,
        object_type=ObjectKind.PROJECT,
        workspace_id=ws_id,
        identifier="PROJ",
        name="Test Project",
    )
    app_session.add(project)
    await app_session.flush()

    # Create custom role 'security-lead' with color_hex
    custom_role_id = uuid.uuid4()
    custom_role = RbacRoleModel(
        id=custom_role_id,
        workspace_id=ws_id,
        slug="security-lead",
        name="Security Lead",
        color_hex="#10b981",
        is_system=False,
        scope_tier="workspace",
        base_capability_mask=0,
    )
    app_session.add(custom_role)
    await app_session.flush()

    # Add permissions: issue:view, issue:comment, field:modify_summary, issue:manage_acl
    # Expected mask: 1 (view) | 2 (comment) | 4 (edit) | 32 (share/manage_acl) = 39
    perms = ["issue:view", "issue:comment", "field:modify_summary", "issue:manage_acl"]
    for p in perms:
        app_session.add(
            RbacRolePermission(
                workspace_id=ws_id,
                role_id=custom_role_id,
                permission_key=p,
                effect="ALLOW",
            )
        )
    await app_session.flush()

    # Check mask derived on rbac_roles
    await app_session.refresh(custom_role)
    assert custom_role.base_capability_mask == 39

    # Assign custom role label to user in addition to existing 'users' role (mask 31)
    # Combined effective mask should be: 31 | 39 = 63 (includes SHARE bit 32!)
    app_session.add(
        PrincipalRoleLabel(
            workspace_id=ws_id,
            principal_id=u_id,
            role_id=custom_role_id,
            project_id=None,
        )
    )
    await app_session.flush()
    await app_session.execute(
        text("SELECT rebuild_effective_access_for_workspace(:ws_id)"),
        {"ws_id": ws_id},
    )

    await app_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_rls_context(app_session, RLSContext(workspace_id=ws_id, principal_id=u_id))

    era_stmt = select(EffectiveResourceAccess.allow_mask).where(
        EffectiveResourceAccess.workspace_id == ws_id,
        EffectiveResourceAccess.principal_id == u_id,
        EffectiveResourceAccess.object_id == p_id,
    )
    effective_mask = (await app_session.execute(era_stmt)).scalar_one()
    # 31 (standard user) | 39 (security lead) = 63
    assert (effective_mask & 32) == 32
    assert (effective_mask & 31) == 31
