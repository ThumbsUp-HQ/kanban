"""Unit tests for Phase 1 audit_object_links() 6-reason detector and invalid_object_link_audits."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from database.tests.conftest import bind_ctx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _create_workspace(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Test Workspace",
) -> uuid.UUID:
    """Create a test workspace."""
    ws_slug = slug or f"ws-{uuid.uuid4().hex[:12]}"
    row = await session.execute(
        text("INSERT INTO workspaces (slug, name) VALUES (:slug, :name) RETURNING id"),
        {"slug": ws_slug, "name": name},
    )
    val = row.scalar_one()
    assert isinstance(val, uuid.UUID)
    return val


async def _create_user(
    session: AsyncSession,
    ws_id: uuid.UUID,
    *,
    display_name: str = "Test User",
) -> uuid.UUID:
    """Register and insert a user in objects, principals, and users."""
    u_id = uuid.uuid4()
    await session.scalar(
        text("SELECT register_object('user'::object_kind, :ws_id, NULL, :ckey, :name, :uid, :id)"),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{u_id.hex[:8]}",
            "name": display_name,
            "uid": u_id,
            "id": u_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
            "VALUES (:id, :ws_id, 'USER', :name)"
        ),
        {"id": u_id, "ws_id": ws_id, "name": display_name},
    )
    await session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
        {"id": u_id, "ws_id": ws_id, "email": f"{u_id.hex[:8]}@example.com"},
    )
    return u_id


async def _create_member(
    session: AsyncSession,
    ws_id: uuid.UUID,
    *,
    display_name: str = "Test Member",
) -> uuid.UUID:
    """Create a user with WORKSPACE_MEMBER role holding VIEW permission on workspace objects."""
    uid = await _create_user(session, ws_id, display_name=display_name)
    await session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :uid, 'WORKSPACE_MEMBER', 'workspace', NULL)"
        ),
        {"ws_id": ws_id, "uid": uid},
    )
    return uid


async def _create_project(
    session: AsyncSession,
    ws_id: uuid.UUID,
    *,
    identifier: str = "PRJ",
    name: str = "Test Project",
) -> uuid.UUID:
    """Register and create a project in the database."""
    u_id = uuid.uuid4()
    reg_row = await session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws_id, NULL, :identifier, :name, :u_id"
            ")"
        ),
        {"ws_id": ws_id, "identifier": identifier, "name": name, "u_id": u_id},
    )
    proj_id = reg_row.scalar_one()
    assert isinstance(proj_id, uuid.UUID)
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws_id, :identifier, :name)"
        ),
        {"id": proj_id, "ws_id": ws_id, "identifier": identifier, "name": name},
    )
    return proj_id


async def _register_obj(  # noqa: PLR0913
    session: AsyncSession,
    ws_id: uuid.UUID,
    obj_type: str,
    canonical_key: str,
    *,
    project_id: uuid.UUID | None = None,
    title: str = "Sample Title",
    user_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Register an object in the objects spine."""
    creator = user_id or uuid.uuid4()
    row = await session.execute(
        text(
            "SELECT register_object("
            "  CAST(:obj_type AS object_kind), :ws_id, :proj_id, :canonical_key, :title, :user_id"
            ")"
        ),
        {
            "obj_type": obj_type,
            "ws_id": ws_id,
            "proj_id": project_id,
            "canonical_key": canonical_key,
            "title": title,
            "user_id": creator,
        },
    )
    val = row.scalar_one()
    assert isinstance(val, uuid.UUID)
    return val


async def _create_issue(  # noqa: PLR0913
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    state_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    summary: str = "Issue Summary",
) -> uuid.UUID:
    """Create an issue object and matching issues table row with allocated sequence."""
    seq = await session.scalar(
        text("SELECT allocate_issue_sequence(:pid)"),
        {"pid": proj_id},
    )
    assert isinstance(seq, int)
    p_ident = await session.scalar(
        text("SELECT identifier FROM projects WHERE id = :id"),
        {"id": proj_id},
    )
    ckey = f"{p_ident}-{seq}"
    i_id = await _register_obj(
        session,
        ws_id,
        "issue",
        ckey,
        project_id=proj_id,
        title=summary,
        user_id=user_id,
    )
    await session.execute(
        text(
            "INSERT INTO issues ("
            "  id, workspace_id, project_id, sequence_id, summary, "
            "  description_markdown, state_id, priority_id, "
            "  created_by_id, original_created_by_id, board_rank"
            ") VALUES ("
            "  :id, :ws_id, :proj_id, :seq, :summary, "
            "  'Desc', :state_id, "
            "  (SELECT id FROM project_priorities WHERE project_id = :proj_id AND slug = 'none'), "
            "  :user_id, :user_id, 1.0"
            ")"
        ),
        {
            "id": i_id,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "seq": seq,
            "summary": summary,
            "state_id": state_id,
            "user_id": user_id,
        },
    )
    return i_id


async def _create_link(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    src_id: uuid.UUID,
    src_type: str,
    tgt_id: uuid.UUID,
    tgt_type: str,
    link_type: str,
    user_id: uuid.UUID,
) -> uuid.UUID:
    """Create an object_links row."""
    res = await session.execute(
        text(
            "INSERT INTO object_links ("
            "  workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, created_by_id"
            ") VALUES ("
            "  :ws_id, :src_id, CAST(:src_type AS object_kind), "
            "  :tgt_id, CAST(:tgt_type AS object_kind), "
            "  CAST(:link_type AS link_kind), :user_id"
            ") RETURNING id"
        ),
        {
            "ws_id": ws_id,
            "src_id": src_id,
            "src_type": src_type,
            "tgt_id": tgt_id,
            "tgt_type": tgt_type,
            "link_type": link_type,
            "user_id": user_id,
        },
    )
    val = res.scalar_one()
    assert isinstance(val, uuid.UUID)
    return val


async def test_01_class_1_dangling_source_and_target(db_session: AsyncSession) -> None:
    """Case 1: Simulate object deletion as superuser; audit detects DANGLING_SOURCE/TARGET."""
    ws_id = await _create_workspace(db_session)
    user_id = await _create_member(db_session, ws_id)

    src1 = await _register_obj(db_session, ws_id, "issue", "DNG-1", user_id=user_id)
    tgt1 = await _register_obj(db_session, ws_id, "issue", "DNG-2", user_id=user_id)
    src2 = await _register_obj(db_session, ws_id, "issue", "DNG-3", user_id=user_id)
    tgt2 = await _register_obj(db_session, ws_id, "issue", "DNG-4", user_id=user_id)

    link1 = await _create_link(db_session, ws_id, src1, "issue", tgt1, "issue", "BLOCKS", user_id)
    link2 = await _create_link(db_session, ws_id, src2, "issue", tgt2, "issue", "BLOCKS", user_id)

    # Simulate catalog / FK corruption as superuser
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(text("DELETE FROM objects WHERE id = :id"), {"id": src1})
    await db_session.execute(text("DELETE FROM objects WHERE id = :id"), {"id": tgt2})

    # Run audit_object_links
    res = await db_session.execute(
        text("SELECT * FROM audit_object_links(:ws)"),
        {"ws": ws_id},
    )
    detected = res.mappings().all()
    assert len(detected) == 2

    # Check link1: dangling source
    row1 = next(r for r in detected if r["link_id"] == link1)
    assert row1["reason"] == "DANGLING_SOURCE"

    # Check link2: dangling target
    row2 = next(r for r in detected if r["link_id"] == link2)
    assert row2["reason"] == "DANGLING_TARGET"

    # Verify link_state flipped to FLAGGED_INVALID
    states = await db_session.execute(
        text("SELECT id, link_state FROM object_links WHERE id IN (:l1, :l2)"),
        {"l1": link1, "l2": link2},
    )
    for s in states.mappings().all():
        assert s["link_state"] == "FLAGGED_INVALID"

    # Verify audit snapshots in table
    audits = await db_session.execute(
        text(
            "SELECT link_id, reason, source_snapshot, target_snapshot "
            "FROM invalid_object_link_audits"
        ),
    )
    audit_rows = audits.mappings().all()
    assert len(audit_rows) == 2

    a1 = next(r for r in audit_rows if r["link_id"] == link1)
    assert a1["reason"] == "DANGLING_SOURCE"
    assert a1["source_snapshot"] is None
    assert a1["target_snapshot"] is not None

    a2 = next(r for r in audit_rows if r["link_id"] == link2)
    assert a2["reason"] == "DANGLING_TARGET"
    assert a2["source_snapshot"] is not None
    assert a2["target_snapshot"] is None


async def test_02_class_2_soft_deleted_endpoint_retention_window(db_session: AsyncSession) -> None:
    """Case 2: Soft-deleted endpoint inside retention is ignored; flagged once grace expires."""
    ws_id = await _create_workspace(db_session)
    user_id = await _create_member(db_session, ws_id)
    proj_id = await _create_project(db_session, ws_id, identifier="DEL")

    src = await _register_obj(
        db_session, ws_id, "issue", "DEL-1", project_id=proj_id, user_id=user_id
    )
    tgt = await _register_obj(
        db_session, ws_id, "issue", "DEL-2", project_id=proj_id, user_id=user_id
    )
    link_id = await _create_link(db_session, ws_id, src, "issue", tgt, "issue", "BLOCKS", user_id)

    # Soft delete target 10 days ago (workspace default retention is 30 days)
    await db_session.execute(
        text(
            "UPDATE objects SET deleted_at = clock_timestamp() - interval '10 days' WHERE id = :id"
        ),
        {"id": tgt},
    )

    # Audit as of now: inside 30-day retention window -> 0 flagged rows
    res_now = await db_session.execute(
        text("SELECT * FROM audit_object_links(:ws, clock_timestamp())"),
        {"ws": ws_id},
    )
    assert len(res_now.mappings().all()) == 0

    state_now = await db_session.execute(
        text("SELECT link_state FROM object_links WHERE id = :id"),
        {"id": link_id},
    )
    assert state_now.scalar_one() == "ACTIVE"

    # Audit as of now + 21 days: 10 + 21 = 31 days > 30 days -> flags SOFT_DELETED_ENDPOINT
    res_future = await db_session.execute(
        text("SELECT * FROM audit_object_links(:ws, clock_timestamp() + interval '21 days')"),
        {"ws": ws_id},
    )
    flagged = res_future.mappings().all()
    assert len(flagged) == 1
    assert flagged[0]["link_id"] == link_id
    assert flagged[0]["reason"] == "SOFT_DELETED_ENDPOINT"

    state_future = await db_session.execute(
        text("SELECT link_state FROM object_links WHERE id = :id"),
        {"id": link_id},
    )
    assert state_future.scalar_one() == "FLAGGED_INVALID"


async def test_03_class_3_archived_policy_violation_incremental_trigger(
    db_session: AsyncSession,
) -> None:
    """Case 3: Setting archived_at triggers immediate FLAGGED_INVALID; unarchiving auto-heals."""
    ws_id = await _create_workspace(db_session)
    user_id = await _create_member(db_session, ws_id)
    proj_id = await _create_project(db_session, ws_id, identifier="ARC")

    # Fetch In Progress state
    st_res = await db_session.execute(
        text("SELECT id, name FROM workflow_states WHERE project_id = :p"),
        {"p": proj_id},
    )
    states_by_name = {r["name"]: r["id"] for r in st_res.mappings().all()}
    in_progress_id = states_by_name["In Progress"]

    kan0 = await _create_issue(
        db_session, ws_id, proj_id, in_progress_id, user_id, summary="Blocking issue"
    )
    kan1 = await _create_issue(
        db_session, ws_id, proj_id, in_progress_id, user_id, summary="In progress blocked issue"
    )

    # Link: KAN-0 BLOCKS KAN-1
    link_id = await _create_link(db_session, ws_id, kan0, "issue", kan1, "issue", "BLOCKS", user_id)

    # Step 1: Archive KAN-0 -> incremental trigger immediately flags ARCHIVED_POLICY_VIOLATION
    await db_session.execute(
        text("UPDATE objects SET archived_at = clock_timestamp() WHERE id = :id"),
        {"id": kan0},
    )

    link_state = await db_session.execute(
        text("SELECT link_state FROM object_links WHERE id = :id"),
        {"id": link_id},
    )
    assert link_state.scalar_one() == "FLAGGED_INVALID"

    audit_row = await db_session.execute(
        text(
            "SELECT reason, resolved_at FROM invalid_object_link_audits "
            "WHERE link_id = :lid AND purged_at IS NULL"
        ),
        {"lid": link_id},
    )
    audit = audit_row.mappings().one()
    assert audit["reason"] == "ARCHIVED_POLICY_VIOLATION"
    assert audit["resolved_at"] is None

    # Step 2: Unarchive KAN-0 -> incremental trigger auto-heals link back to ACTIVE
    await db_session.execute(
        text("UPDATE objects SET archived_at = NULL WHERE id = :id"),
        {"id": kan0},
    )

    link_state_healed = await db_session.execute(
        text("SELECT link_state FROM object_links WHERE id = :id"),
        {"id": link_id},
    )
    assert link_state_healed.scalar_one() == "ACTIVE"

    audit_row_healed = await db_session.execute(
        text(
            "SELECT reason, resolved_at FROM invalid_object_link_audits "
            "WHERE link_id = :lid AND purged_at IS NULL"
        ),
        {"lid": link_id},
    )
    audit_healed = audit_row_healed.mappings().one()
    assert audit_healed["reason"] == "ARCHIVED_POLICY_VIOLATION"
    assert audit_healed["resolved_at"] is not None


async def test_04_class_4_type_matrix_violation(db_session: AsyncSession) -> None:
    """Case 4: Delete tuple from link_type_matrix as superuser; audit flags violation."""
    ws_id = await _create_workspace(db_session)
    user_id = await _create_member(db_session, ws_id)

    doc1 = await _register_obj(db_session, ws_id, "doc", "DOC-A", user_id=user_id)
    doc2 = await _register_obj(db_session, ws_id, "doc", "DOC-B", user_id=user_id)
    link_id = await _create_link(db_session, ws_id, doc1, "doc", doc2, "doc", "RELATES_TO", user_id)

    # Delete (doc, RELATES_TO, doc) tuple from matrix as superuser
    await db_session.execute(
        text(
            "DELETE FROM link_type_matrix "
            "WHERE source_type = 'doc' AND link_type = 'RELATES_TO' AND target_type = 'doc'"
        )
    )

    # Run audit
    res = await db_session.execute(
        text("SELECT * FROM audit_object_links(:ws)"),
        {"ws": ws_id},
    )
    detected = res.mappings().all()
    assert len(detected) == 1
    assert detected[0]["link_id"] == link_id
    assert detected[0]["reason"] == "TYPE_MATRIX_VIOLATION"

    # Verify link_state flipped
    state = await db_session.execute(
        text("SELECT link_state FROM object_links WHERE id = :id"),
        {"id": link_id},
    )
    assert state.scalar_one() == "FLAGGED_INVALID"


async def test_05_class_5_cross_workspace_leak(db_session: AsyncSession) -> None:
    """Case 5: Bypass trigger via replica mode to cross-link; audit flags CROSS_WORKSPACE_LEAK."""
    ws1 = await _create_workspace(db_session, slug="ws-one")
    ws2 = await _create_workspace(db_session, slug="ws-two")
    user_id = await _create_member(db_session, ws1)

    obj1 = await _register_obj(db_session, ws1, "issue", "W1-1", user_id=user_id)
    obj2 = await _register_obj(db_session, ws2, "issue", "W2-1", user_id=user_id)

    # Insert cross-workspace link bypassing validation via session_replication_role
    lid = uuid.uuid4()
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "INSERT INTO object_links ("
            "  id, workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, source_key_snapshot, target_key_snapshot, created_by_id, link_state"
            ") VALUES ("
            "  :id, :ws, :src, 'issue', :tgt, 'issue', 'BLOCKS', 'W1-1', 'W2-1', :user, 'ACTIVE'"
            ")"
        ),
        {"id": lid, "ws": ws1, "src": obj1, "tgt": obj2, "user": user_id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = DEFAULT"))

    # Audit ws1
    res = await db_session.execute(
        text("SELECT * FROM audit_object_links(:ws)"),
        {"ws": ws1},
    )
    flagged = res.mappings().all()
    assert len(flagged) >= 1
    reasons = {r["reason"] for r in flagged if r["link_id"] == lid}
    assert "CROSS_WORKSPACE_LEAK" in reasons

    state = await db_session.execute(
        text("SELECT link_state FROM object_links WHERE id = :id"),
        {"id": lid},
    )
    assert state.scalar_one() == "FLAGGED_INVALID"


async def test_06_class_6_permission_severed_incremental_trigger(
    db_session: AsyncSession,
) -> None:
    """Case 6: Adding DENY VIEW ACL flags PERMISSION_SEVERED; removing DENY auto-heals."""
    ws_id = await _create_workspace(db_session)
    u1 = await _create_user(db_session, ws_id, display_name="User One")
    proj_id = await _create_project(db_session, ws_id, identifier="SEC")

    # Give u1 MEMBER role on project SEC (includes VIEW mask = 1)
    await db_session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :uid, 'MEMBER', 'project', :pid)"
        ),
        {"ws_id": ws_id, "uid": u1, "pid": proj_id},
    )

    # Register issues in project
    kan1 = await _register_obj(db_session, ws_id, "issue", "SEC-1", project_id=proj_id, user_id=u1)
    sec1 = await _register_obj(db_session, ws_id, "issue", "SEC-2", project_id=proj_id, user_id=u1)

    # Create link created by u1: KAN-1 RELATES_TO SEC-1
    link_id = await _create_link(db_session, ws_id, kan1, "issue", sec1, "issue", "RELATES_TO", u1)

    # Verify link is ACTIVE
    st = await db_session.execute(
        text("SELECT link_state FROM object_links WHERE id = :id"),
        {"id": link_id},
    )
    assert st.scalar_one() == "ACTIVE"

    # Add DENY VIEW (capability_mask = 1) for u1 on sec1
    # Triggers era refresh and incremental audit trigger in same statement
    await db_session.execute(
        text(
            "INSERT INTO resource_acl_entries ("
            "  workspace_id, object_id, principal_id, effect, capability_mask"
            ") VALUES (:ws_id, :oid, :uid, 'DENY', 1)"
        ),
        {"ws_id": ws_id, "oid": sec1, "uid": u1},
    )

    # Verify link flipped to FLAGGED_INVALID
    st_denied = await db_session.execute(
        text("SELECT link_state FROM object_links WHERE id = :id"),
        {"id": link_id},
    )
    assert st_denied.scalar_one() == "FLAGGED_INVALID"

    audits = await db_session.execute(
        text(
            "SELECT reason, resolved_at FROM invalid_object_link_audits "
            "WHERE link_id = :lid AND purged_at IS NULL"
        ),
        {"lid": link_id},
    )
    audit = audits.mappings().one()
    assert audit["reason"] == "PERMISSION_SEVERED"
    assert audit["resolved_at"] is None

    # Remove DENY entry -> incremental trigger auto-heals link back to ACTIVE
    await db_session.execute(
        text(
            "DELETE FROM resource_acl_entries "
            "WHERE workspace_id = :ws_id AND object_id = :oid AND principal_id = :uid"
        ),
        {"ws_id": ws_id, "oid": sec1, "uid": u1},
    )

    st_healed = await db_session.execute(
        text("SELECT link_state FROM object_links WHERE id = :id"),
        {"id": link_id},
    )
    assert st_healed.scalar_one() == "ACTIVE"

    audits_healed = await db_session.execute(
        text(
            "SELECT reason, resolved_at FROM invalid_object_link_audits "
            "WHERE link_id = :lid AND purged_at IS NULL"
        ),
        {"lid": link_id},
    )
    audit_h = audits_healed.mappings().one()
    assert audit_h["reason"] == "PERMISSION_SEVERED"
    assert audit_h["resolved_at"] is not None


async def test_07_security_idempotency_and_immutability(db_session: AsyncSession) -> None:
    """Case 7: Audit idempotency, non-admin AUDIT_LINKS_FORBIDDEN, immutability triggers."""
    ws_id = await _create_workspace(db_session)
    admin_id = await _create_user(db_session, ws_id, display_name="Admin")
    member_id = await _create_user(db_session, ws_id, display_name="Member")

    # Workspace admin role
    await db_session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :p, 'WORKSPACE_ADMIN', 'workspace', NULL)"
        ),
        {"ws_id": ws_id, "p": admin_id},
    )

    # Workspace member role
    await db_session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :p, 'WORKSPACE_MEMBER', 'workspace', NULL)"
        ),
        {"ws_id": ws_id, "p": member_id},
    )

    # Create a link with a type violation
    doc1 = await _register_obj(db_session, ws_id, "doc", "DOC-S1", user_id=admin_id)
    doc2 = await _register_obj(db_session, ws_id, "doc", "DOC-S2", user_id=admin_id)
    link_id = await _create_link(
        db_session, ws_id, doc1, "doc", doc2, "doc", "RELATES_TO", admin_id
    )

    await db_session.execute(
        text(
            "DELETE FROM link_type_matrix "
            "WHERE source_type = 'doc' AND link_type = 'RELATES_TO' AND target_type = 'doc'"
        )
    )

    # Sub-case 7a: Idempotency: run audit twice
    res1 = await db_session.execute(
        text("SELECT * FROM audit_object_links(:ws)"),
        {"ws": ws_id},
    )
    assert len(res1.mappings().all()) == 1

    res2 = await db_session.execute(
        text("SELECT * FROM audit_object_links(:ws)"),
        {"ws": ws_id},
    )
    assert len(res2.mappings().all()) == 1

    # Exactly 1 open audit row exists (no duplicate inserts)
    audit_count = await db_session.execute(
        text(
            "SELECT count(*) FROM invalid_object_link_audits "
            "WHERE link_id = :lid AND purged_at IS NULL AND resolved_at IS NULL"
        ),
        {"lid": link_id},
    )
    assert audit_count.scalar_one() == 1

    # Sub-case 7b: Non-admin caller under kanban_app raises AUDIT_LINKS_FORBIDDEN
    await db_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    try:
        await bind_ctx(db_session, member_id, ws_id)
        with pytest.raises(DBAPIError) as exc_info:
            async with db_session.begin_nested():
                await db_session.execute(
                    text("SELECT * FROM audit_object_links(:ws)"),
                    {"ws": ws_id},
                )
        assert "AUDIT_LINKS_FORBIDDEN" in str(exc_info.value)

        # Sub-case 7c: Admin caller under kanban_app succeeds
        await bind_ctx(db_session, admin_id, ws_id)
        res_admin = await db_session.execute(
            text("SELECT * FROM audit_object_links(:ws)"),
            {"ws": ws_id},
        )
        assert len(res_admin.mappings().all()) == 1
    finally:
        await db_session.execute(text("RESET SESSION AUTHORIZATION"))

    # Sub-case 7d: Immutability guard triggers
    audit_row = await db_session.execute(
        text("SELECT id FROM invalid_object_link_audits WHERE link_id = :lid"),
        {"lid": link_id},
    )
    aid = audit_row.scalar_one()

    # DELETE raises LINK_AUDIT_RECORD_IMMUTABLE
    with pytest.raises(DBAPIError) as del_exc:
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM invalid_object_link_audits WHERE id = :id"),
                {"id": aid},
            )
    assert "LINK_AUDIT_RECORD_IMMUTABLE" in str(del_exc.value)

    # UPDATE immutable snapshot column raises LINK_AUDIT_SNAPSHOT_IMMUTABLE
    with pytest.raises(DBAPIError) as upd_exc:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE invalid_object_link_audits SET link_id = :dummy WHERE id = :id"),
                {"dummy": uuid.uuid4(), "id": aid},
            )
    assert "LINK_AUDIT_SNAPSHOT_IMMUTABLE" in str(upd_exc.value)

    # UPDATE mutable column (purge_reason) succeeds
    await db_session.execute(
        text(
            "UPDATE invalid_object_link_audits "
            "SET purge_reason = 'Valid purge reason' WHERE id = :id"
        ),
        {"id": aid},
    )
    updated = await db_session.execute(
        text("SELECT purge_reason FROM invalid_object_link_audits WHERE id = :id"),
        {"id": aid},
    )
    assert updated.scalar_one() == "Valid purge reason"


async def test_08_multiple_concurrent_violations(db_session: AsyncSession) -> None:
    """Case 8: Link violating multiple rules emits distinct audit records for each reason."""
    ws1 = await _create_workspace(db_session, slug="ws-m1")
    ws2 = await _create_workspace(db_session, slug="ws-two")
    user_id = await _create_member(db_session, ws1)

    obj1 = await _register_obj(db_session, ws1, "issue", "M1-1", user_id=user_id)
    obj2 = await _register_obj(db_session, ws2, "issue", "M2-1", user_id=user_id)

    # Insert cross-workspace link with an invalid matrix tuple
    lid = uuid.uuid4()
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "INSERT INTO object_links ("
            "  id, workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, source_key_snapshot, target_key_snapshot, created_by_id, link_state"
            ") VALUES ("
            "  :id, :ws, :src, 'issue', :tgt, 'issue', "
            "  'ASSIGNED_TO', 'M1-1', 'M2-1', :user, 'ACTIVE'"
            ")"
        ),
        {"id": lid, "ws": ws1, "src": obj1, "tgt": obj2, "user": user_id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = DEFAULT"))

    # Audit workspace
    res = await db_session.execute(
        text("SELECT * FROM audit_object_links(:ws)"),
        {"ws": ws1},
    )
    detected = res.mappings().all()

    # Link violates both TYPE_MATRIX_VIOLATION (issue->ASSIGNED_TO->issue is not valid)
    # and CROSS_WORKSPACE_LEAK (ws1 != ws2)
    reasons = {r["reason"] for r in detected if r["link_id"] == lid}
    assert "TYPE_MATRIX_VIOLATION" in reasons
    assert "CROSS_WORKSPACE_LEAK" in reasons
    assert len(reasons) >= 2


async def test_09_all_six_reasons_sample(db_session: AsyncSession) -> None:  # noqa: PLR0915
    """Case 9: Verify all 6 invalidity classes captured in invalid_object_link_audits."""
    ws1 = await _create_workspace(db_session, slug="ws-six-1")
    ws2 = await _create_workspace(db_session, slug="ws-six-2")
    user_id = await _create_member(db_session, ws1, display_name="Auditor User")
    proj_id = await _create_project(db_session, ws1, identifier="SIX")

    # Workflow state In Progress
    st_res = await db_session.execute(
        text("SELECT id, name FROM workflow_states WHERE project_id = :p"),
        {"p": proj_id},
    )
    states_by_name = {r["name"]: r["id"] for r in st_res.mappings().all()}
    in_progress_id = states_by_name["In Progress"]

    # 1. Class 1: DANGLING_SOURCE
    src_dng = await _register_obj(
        db_session, ws1, "issue", "SIX-D1", project_id=proj_id, user_id=user_id
    )
    tgt_dng = await _register_obj(
        db_session, ws1, "issue", "SIX-D2", project_id=proj_id, user_id=user_id
    )
    await _create_link(db_session, ws1, src_dng, "issue", tgt_dng, "issue", "BLOCKS", user_id)
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(text("DELETE FROM objects WHERE id = :id"), {"id": src_dng})
    await db_session.execute(text("SET LOCAL session_replication_role = DEFAULT"))

    # Class 1: DANGLING_TARGET
    src_dng2 = await _register_obj(
        db_session, ws1, "issue", "SIX-D3", project_id=proj_id, user_id=user_id
    )
    tgt_dng2 = await _register_obj(
        db_session, ws1, "issue", "SIX-D4", project_id=proj_id, user_id=user_id
    )
    await _create_link(db_session, ws1, src_dng2, "issue", tgt_dng2, "issue", "BLOCKS", user_id)
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(text("DELETE FROM objects WHERE id = :id"), {"id": tgt_dng2})
    await db_session.execute(text("SET LOCAL session_replication_role = DEFAULT"))

    # 2. Class 2: SOFT_DELETED_ENDPOINT
    src_del = await _register_obj(
        db_session, ws1, "issue", "SIX-SD1", project_id=proj_id, user_id=user_id
    )
    tgt_del = await _register_obj(
        db_session, ws1, "issue", "SIX-SD2", project_id=proj_id, user_id=user_id
    )
    await _create_link(db_session, ws1, src_del, "issue", tgt_del, "issue", "BLOCKS", user_id)
    await db_session.execute(
        text(
            "UPDATE objects SET deleted_at = clock_timestamp() - interval '40 days' WHERE id = :id"
        ),
        {"id": tgt_del},
    )

    # 3. Class 3: ARCHIVED_POLICY_VIOLATION
    kan0 = await _create_issue(
        db_session, ws1, proj_id, in_progress_id, user_id, summary="Archived Blocker"
    )
    kan1 = await _create_issue(
        db_session, ws1, proj_id, in_progress_id, user_id, summary="Active Blocked"
    )
    await _create_link(db_session, ws1, kan0, "issue", kan1, "issue", "BLOCKS", user_id)
    await db_session.execute(
        text("UPDATE objects SET archived_at = clock_timestamp() WHERE id = :id"),
        {"id": kan0},
    )

    # 4. Class 4: TYPE_MATRIX_VIOLATION
    src_tm = await _register_obj(
        db_session, ws1, "issue", "SIX-TM1", project_id=proj_id, user_id=user_id
    )
    tgt_tm = await _register_obj(
        db_session, ws1, "issue", "SIX-TM2", project_id=proj_id, user_id=user_id
    )
    lid_tm = uuid.uuid4()
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "INSERT INTO object_links ("
            "  id, workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, source_key_snapshot, target_key_snapshot, created_by_id, link_state"
            ") VALUES ("
            "  :id, :ws, :src, 'issue', :tgt, 'issue', "
            "  'ASSIGNED_TO', 'SIX-TM1', 'SIX-TM2', :user, 'ACTIVE'"
            ")"
        ),
        {"id": lid_tm, "ws": ws1, "src": src_tm, "tgt": tgt_tm, "user": user_id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = DEFAULT"))

    # 5. Class 5: CROSS_WORKSPACE_LEAK
    src_cw = await _register_obj(
        db_session, ws1, "issue", "SIX-CW1", project_id=proj_id, user_id=user_id
    )
    tgt_cw = await _register_obj(db_session, ws2, "issue", "SIX-CW2", user_id=user_id)
    lid_cw = uuid.uuid4()
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "INSERT INTO object_links ("
            "  id, workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, source_key_snapshot, target_key_snapshot, created_by_id, link_state"
            ") VALUES ("
            "  :id, :ws, :src, 'issue', :tgt, 'issue', "
            "  'BLOCKS', 'SIX-CW1', 'SIX-CW2', :user, 'ACTIVE'"
            ")"
        ),
        {"id": lid_cw, "ws": ws1, "src": src_cw, "tgt": tgt_cw, "user": user_id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = DEFAULT"))

    # 6. Class 6: PERMISSION_SEVERED
    u_perm = await _create_user(db_session, ws1, display_name="Perm User")
    await db_session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :uid, 'MEMBER', 'project', :pid)"
        ),
        {"ws_id": ws1, "uid": u_perm, "pid": proj_id},
    )
    src_p = await _register_obj(
        db_session, ws1, "issue", "SIX-P1", project_id=proj_id, user_id=u_perm
    )
    tgt_p = await _register_obj(
        db_session, ws1, "issue", "SIX-P2", project_id=proj_id, user_id=u_perm
    )
    await _create_link(db_session, ws1, src_p, "issue", tgt_p, "issue", "RELATES_TO", u_perm)
    await db_session.execute(
        text(
            "INSERT INTO resource_acl_entries ("
            "  workspace_id, object_id, principal_id, effect, capability_mask"
            ") VALUES (:ws_id, :oid, :uid, 'DENY', 1)"
        ),
        {"ws_id": ws1, "oid": tgt_p, "uid": u_perm},
    )

    # Run audit on ws1 as of clock_timestamp() under replica mode
    # to simulate catalog corruption environment where dangling endpoints exist
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text("SELECT * FROM audit_object_links(:ws, clock_timestamp())"),
        {"ws": ws1},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = DEFAULT"))

    # Query all invalid_object_link_audits for ws1
    query_res = await db_session.execute(
        text(
            "SELECT "
            "  a.reason::text AS reason, "
            "  a.link_snapshot->>'link_type' AS link_type, "
            "  ol.link_state::text AS link_state, "
            "  a.link_id, "
            "  (a.source_snapshot IS NOT NULL) AS has_source_snapshot, "
            "  (a.target_snapshot IS NOT NULL) AS has_target_snapshot "
            "FROM invalid_object_link_audits a "
            "JOIN object_links ol ON ol.id = a.link_id "
            "WHERE a.workspace_id = :ws "
            "ORDER BY a.reason"
        ),
        {"ws": ws1},
    )
    rows = query_res.mappings().all()

    # Verify all 6 invalidity classes are present
    captured_reasons = {r["reason"] for r in rows}
    expected_reasons = {
        "DANGLING_SOURCE",
        "DANGLING_TARGET",
        "SOFT_DELETED_ENDPOINT",
        "ARCHIVED_POLICY_VIOLATION",
        "TYPE_MATRIX_VIOLATION",
        "CROSS_WORKSPACE_LEAK",
        "PERMISSION_SEVERED",
    }
    assert expected_reasons.issubset(captured_reasons)
    for r in rows:
        assert r["link_state"] == "FLAGGED_INVALID", f"Row failed: {dict(r)}"
