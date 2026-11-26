# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit and clean-DB tests for LDAP group synchronization and closure triggers (KB-P2-07)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from database.models.auth import LdapGroupMapping
from database.models.principals import Group, Principal, PrincipalGroupEdge
from kanban.auth.cards.repository import admin_upsert
from kanban.auth.ldap.sync import _reconcile_group_nesting_edges, sync_ldap_groups

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _setup_workspace_and_admin(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Provision workspace and SERVER_ADMIN principal with AAL2 session context."""
    ws_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "LDAP Sync WS"},
    )

    u_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{u_id.hex}",
            "title": "LDAP Admin",
            "u_id": u_id,
        },
    )

    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'LDAP Admin', 'ACTIVE')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )

    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'admin@example.com')"
        ),
        {"id": u_id, "ws_id": ws_id},
    )

    rb_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO role_bindings "
            "(id, workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:id, :ws_id, :p_id, 'SERVER_ADMIN', 'server', NULL)"
        ),
        {"id": rb_id, "ws_id": ws_id, "p_id": u_id},
    )

    await session.execute(
        text(
            "SELECT set_config('app.principal_id', :p_id, true), "
            "set_config('app.workspace_id', :w_id, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"p_id": str(u_id), "w_id": str(ws_id)},
    )

    return ws_id, u_id


async def _create_test_user(session: AsyncSession, ws_id: uuid.UUID) -> uuid.UUID:
    """Create a standard workspace user to test membership edges."""
    user_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :title, :u_id, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{user_id.hex}",
            "title": "Directory User",
            "u_id": user_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name, status) "
            "VALUES (:id, 'USER', :ws_id, 'Directory User', 'ACTIVE')"
        ),
        {"id": user_id, "ws_id": ws_id},
    )
    await session.execute(
        text(
            "INSERT INTO users (id, object_type, principal_type, workspace_id, email) "
            "VALUES (:id, 'user', 'USER', :ws_id, 'user@example.com')"
        ),
        {"id": user_id, "ws_id": ws_id},
    )
    return user_id


async def _create_local_group(session: AsyncSession, ws_id: uuid.UUID, name: str) -> uuid.UUID:
    """Create a local non-LDAP group."""
    grp_id = uuid.uuid4()
    principal = Principal(
        id=grp_id,
        principal_type="GROUP",
        workspace_id=ws_id,
        status="ACTIVE",
        display_name=name,
    )
    session.add(principal)
    await session.flush()

    group = Group(
        id=grp_id,
        principal_type="GROUP",
        workspace_id=ws_id,
        name=name,
        external_source=None,
        external_id=None,
    )
    session.add(group)
    await session.flush()
    return grp_id


@pytest.mark.asyncio
async def test_09_group_dn_sync_lifecycle_and_closure(db_session: AsyncSession) -> None:
    """Test Case 9: Group DN sync with clean-DB harness, memberOf reconcile, and closure check."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    user_id = await _create_test_user(db_session, ws_id)

    # 1. User belongs to a local non-LDAP group
    local_grp_id = await _create_local_group(db_session, ws_id, "Local Engineers")
    db_session.add(
        PrincipalGroupEdge(
            member_id=user_id,
            group_id=local_grp_id,
            workspace_id=ws_id,
        )
    )
    await db_session.flush()

    group_dn_map = {
        "CN=Core-Backend,OU=Groups,DC=corp,DC=example": "Core Backend",
        r"CN=Engineers\, Systems,OU=Groups,DC=corp,DC=example": "Systems Engineering",
    }

    # First sync: user has Core-Backend and an unmapped group
    raw_dns_1 = [
        "CN=Core-Backend,OU=Groups,DC=corp,DC=example",
        "CN=Unmapped,OU=Groups,DC=corp,DC=example",
    ]
    matched_1 = await sync_ldap_groups(db_session, ws_id, user_id, raw_dns_1, group_dn_map)
    assert matched_1 == ["Core Backend"]

    # Verify Core Backend group was created with external_source='LDAP'
    stmt_grp = select(Group).where(Group.workspace_id == ws_id, Group.name == "Core Backend")
    res_grp = await db_session.execute(stmt_grp)
    core_backend_grp = res_grp.scalars().one()
    assert core_backend_grp.external_source == "LDAP"

    # Verify PrincipalGroupEdge exists for Core Backend
    stmt_edges = select(PrincipalGroupEdge).where(
        PrincipalGroupEdge.workspace_id == ws_id,
        PrincipalGroupEdge.member_id == user_id,
    )
    res_edges = await db_session.execute(stmt_edges)
    edge_gids = {e.group_id for e in res_edges.scalars().all()}
    assert core_backend_grp.id in edge_gids
    assert local_grp_id in edge_gids  # Local group must remain untouched!

    # Verify closure populated via DB trigger
    stmt_closure = text(
        "SELECT depth FROM principal_group_closure "
        "WHERE member_id = :u_id AND ancestor_group_id = :g_id"
    )
    res_closure = await db_session.execute(
        stmt_closure, {"u_id": user_id, "g_id": core_backend_grp.id}
    )
    closure_rows = res_closure.fetchall()
    assert len(closure_rows) >= 1

    # Second sync: Core Backend removed from user's directory groups
    raw_dns_2 = ["CN=Unmapped,OU=Groups,DC=corp,DC=example"]
    matched_2 = await sync_ldap_groups(db_session, ws_id, user_id, raw_dns_2, group_dn_map)
    assert matched_2 == []

    # Verify Core Backend edge was revoked, but Local Engineers edge remains
    res_edges_2 = await db_session.execute(stmt_edges)
    edge_gids_2 = {e.group_id for e in res_edges_2.scalars().all()}
    assert core_backend_grp.id not in edge_gids_2
    assert local_grp_id in edge_gids_2

    # Third sync: Case variants, extra spaces, and escaped commas
    raw_dns_3 = [
        " cn = Core-Backend , ou = Groups , dc = corp , dc = example ",
        r"CN=Engineers\, Systems,OU=Groups,DC=corp,DC=example",
    ]
    matched_3 = await sync_ldap_groups(db_session, ws_id, user_id, raw_dns_3, group_dn_map)
    assert matched_3 == ["Core Backend", "Systems Engineering"]

    res_edges_3 = await db_session.execute(stmt_edges)
    edge_gids_3 = {e.group_id for e in res_edges_3.scalars().all()}
    assert core_backend_grp.id in edge_gids_3
    assert local_grp_id in edge_gids_3
    assert len(edge_gids_3) == 3


@pytest.mark.asyncio
async def test_group_sync_empty_inputs(db_session: AsyncSession) -> None:
    """Test group sync empty mapping or empty inputs."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    user_id = await _create_test_user(db_session, ws_id)

    res1 = await sync_ldap_groups(db_session, ws_id, user_id, [], {})
    assert res1 == []

    res2 = await sync_ldap_groups(
        db_session,
        ws_id,
        user_id,
        ["cn=group,dc=com"],
        {"": ""},
    )
    assert res2 == []


@pytest.mark.asyncio
async def test_group_sync_reconciliation_idempotency(db_session: AsyncSession) -> None:
    """Test running group sync multiple times with same groups is a no-op."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    user_id = await _create_test_user(db_session, ws_id)

    group_map = {"cn=devs,dc=example,dc=com": "Developers"}
    dns = ["cn=devs,dc=example,dc=com"]

    first_res = await sync_ldap_groups(db_session, ws_id, user_id, dns, group_map)
    assert first_res == ["Developers"]

    second_res = await sync_ldap_groups(db_session, ws_id, user_id, dns, group_map)
    assert second_res == ["Developers"]


@pytest.mark.asyncio
async def test_ldap_group_mapping_table_model(db_session: AsyncSession) -> None:
    """Test LdapGroupMapping ORM model and database table persistence."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)

    card_id = await admin_upsert(
        db_session,
        workspace_id=ws_id,
        provider_kind="LDAP",
        slug="ldap-mapping-test",
        display_name="LDAP Mapping Test Card",
        sort_rank="0002",
        public_config={
            "kind": "LDAP",
            "url": "ldaps://localhost:636",
            "transport_mode": "ldaps",
            "base_dn": "dc=example,dc=com",
        },
    )

    mapping = LdapGroupMapping(
        card_id=card_id,
        workspace_id=ws_id,
        ldap_dn="cn=security-auditors,ou=groups,dc=example,dc=com",
        group_name="Security Auditors",
    )
    db_session.add(mapping)
    await db_session.flush()

    assert mapping.id is not None
    assert str(mapping.card_id) == str(card_id)
    assert "security-auditors" in repr(mapping)

    # Query back
    stmt = select(LdapGroupMapping).where(LdapGroupMapping.card_id == card_id)
    res = await db_session.execute(stmt)
    loaded = res.scalars().one()
    assert loaded.group_name == "Security Auditors"
    assert loaded.ldap_dn == "cn=security-auditors,ou=groups,dc=example,dc=com"


@pytest.mark.asyncio
async def test_group_sync_nested_group_parent_map(db_session: AsyncSession) -> None:
    """Test group sync reconciles inter-group nesting edges and closure triggers."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    user_id = await _create_test_user(db_session, ws_id)

    child_dn = "cn=subteam,ou=groups,dc=example,dc=com"
    parent_dn = "cn=parent,ou=groups,dc=example,dc=com"
    group_map = {
        child_dn: "Subteam Group",
        parent_dn: "Parent Group",
    }
    parent_map = {
        child_dn: [parent_dn],
    }

    # User is only member of child group directly
    matched = await sync_ldap_groups(
        db_session,
        ws_id,
        user_id,
        [child_dn],
        group_map,
        group_parent_map=parent_map,
    )
    assert matched == ["Subteam Group"]

    # Verify inter-group edge was created
    child_stmt = select(Group).where(Group.name == "Subteam Group", Group.workspace_id == ws_id)
    parent_stmt = select(Group).where(Group.name == "Parent Group", Group.workspace_id == ws_id)
    child_grp = await db_session.scalar(child_stmt)
    parent_grp = await db_session.scalar(parent_stmt)
    assert child_grp is not None
    assert parent_grp is not None

    edge = await db_session.scalar(
        select(PrincipalGroupEdge).where(
            PrincipalGroupEdge.member_id == child_grp.id,
            PrincipalGroupEdge.group_id == parent_grp.id,
            PrincipalGroupEdge.workspace_id == ws_id,
        )
    )
    assert edge is not None

    # Verify closure depth in principal_group_closure
    closure_depth = await db_session.scalar(
        text(
            "SELECT depth FROM principal_group_closure "
            "WHERE member_id = :u_id AND ancestor_group_id = :p_id "
            "ORDER BY depth DESC LIMIT 1"
        ),
        {"u_id": user_id, "p_id": parent_grp.id},
    )
    assert closure_depth is not None
    assert closure_depth >= 2

    # Second sync: idempotent, doesn't duplicate
    matched2 = await sync_ldap_groups(
        db_session,
        ws_id,
        user_id,
        [child_dn],
        group_map,
        group_parent_map=parent_map,
    )
    assert matched2 == ["Subteam Group"]


async def test_sync_ldap_groups_parent_map_defensive_branches(
    db_session: AsyncSession,
) -> None:
    """Test defensive branches in group nesting edge reconciliation (lines 35, 43, 47)."""
    ws_id, _ = await _setup_workspace_and_admin(db_session)
    user_id = await _create_test_user(db_session, ws_id)

    child_dn = "cn=subteam,ou=groups,dc=example,dc=com"
    parent_dn = "cn=parent,ou=groups,dc=example,dc=com"
    group_map = {
        child_dn: "Subteam Group",
        parent_dn: "Parent Group",
    }
    # Include:
    # 1. Unmapped child DN (line 35)
    # 2. Unmapped parent DN (line 43)
    # 3. Self-referential parent DN (child == parent, line 47)
    parent_map = {
        "cn=unmapped_child,ou=groups,dc=example,dc=com": [parent_dn],
        child_dn: [
            "cn=unmapped_parent,ou=groups,dc=example,dc=com",
            child_dn,
            parent_dn,
        ],
    }

    matched = await sync_ldap_groups(
        db_session,
        ws_id,
        user_id,
        [child_dn],
        group_map,
        group_parent_map=parent_map,
    )
    assert matched == ["Subteam Group"]


async def test_reconcile_group_nesting_edges_missing_group_records(
    db_session: AsyncSession,
) -> None:
    """Test _reconcile_group_nesting_edges when groups are missing in group_by_name."""
    ws_id = uuid.uuid4()
    child_dn = "cn=child,ou=groups,dc=example,dc=com"
    parent_dn = "cn=parent,ou=groups,dc=example,dc=com"
    canonical_map = {
        child_dn: "Child Group",
        parent_dn: "Parent Group",
    }

    # Case 1: c_name not in group_by_name (line 39)
    await _reconcile_group_nesting_edges(
        db_session,
        ws_id,
        group_parent_map={child_dn: [parent_dn]},
        canonical_map=canonical_map,
        group_by_name={},
    )

    # Case 2: p_name not in group_by_name (line 47: not p_grp)
    mock_child = Group(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        name="Child Group",
    )
    await _reconcile_group_nesting_edges(
        db_session,
        ws_id,
        group_parent_map={child_dn: [parent_dn]},
        canonical_map=canonical_map,
        group_by_name={"Child Group": mock_child},
    )


