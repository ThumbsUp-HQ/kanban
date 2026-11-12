"""Unit tests for Phase 1 purge_invalid_object_links() and delete-guard trigger (KANBA-53)."""

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


async def _create_service_principal(
    session: AsyncSession,
    ws_id: uuid.UUID,
    *,
    display_name: str = "system:trash-purge",
) -> uuid.UUID:
    """Insert a SERVICE_PRINCIPAL in principals."""
    sp_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
            "VALUES (:id, :ws_id, 'SERVICE_PRINCIPAL', :name)"
        ),
        {"id": sp_id, "ws_id": ws_id, "name": display_name},
    )
    return sp_id


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


async def _assign_role(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    principal_id: uuid.UUID,
    role: str,
    scope_type: str = "workspace",
    project_id: uuid.UUID | None = None,
) -> None:
    """Assign a role binding to a principal."""
    await session.execute(
        text(
            "INSERT INTO role_bindings ("
            "  workspace_id, principal_id, role, scope_type, project_id"
            ") VALUES (:ws_id, :pid, :role, :scope, :project_id)"
        ),
        {
            "ws_id": ws_id,
            "pid": principal_id,
            "role": role,
            "scope": scope_type,
            "project_id": project_id,
        },
    )


async def test_01_positive_purge_two_invalid_links(db_session: AsyncSession) -> None:
    """Case 1: Flag 2 invalid links, purge as WORKSPACE_ADMIN, verify deleted links, audits."""
    ws_id = await _create_workspace(db_session)
    admin_id = await _create_user(db_session, ws_id, display_name="Admin User")
    await _assign_role(db_session, ws_id, admin_id, "WORKSPACE_ADMIN")

    # Project 1 for link 1 (ARCHIVED_POLICY_VIOLATION)
    proj1 = await _create_project(db_session, ws_id, identifier="PRJA")
    st_res1 = await db_session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
        {"p": proj1},
    )
    st_id1 = st_res1.scalar_one()

    iss1 = await _create_issue(db_session, ws_id, proj1, st_id1, admin_id, summary="Iss 1")
    iss2 = await _create_issue(db_session, ws_id, proj1, st_id1, admin_id, summary="Iss 2")
    link1 = await _create_link(db_session, ws_id, iss1, "issue", iss2, "issue", "BLOCKS", admin_id)

    # Project 2 for link 2 (DANGLING_SOURCE)
    proj2 = await _create_project(db_session, ws_id, identifier="PRJB")
    st_res2 = await db_session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
        {"p": proj2},
    )
    st_id2 = st_res2.scalar_one()

    iss3 = await _register_obj(db_session, ws_id, "issue", "DNG-SRC", user_id=admin_id)
    iss4 = await _create_issue(db_session, ws_id, proj2, st_id2, admin_id, summary="Iss 4")
    link2 = await _create_link(db_session, ws_id, iss3, "issue", iss4, "issue", "BLOCKS", admin_id)

    # Trigger ARCHIVED_POLICY_VIOLATION on link1
    await db_session.execute(
        text("UPDATE objects SET archived_at = clock_timestamp() WHERE id = :id"),
        {"id": iss1},
    )

    # Trigger DANGLING_SOURCE on link2 under replica mode to simulate catalog/FK corruption
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(text("DELETE FROM objects WHERE id = :id"), {"id": iss3})
    await db_session.execute(text("SELECT * FROM audit_object_links(:ws)"), {"ws": ws_id})
    await db_session.execute(text("SET LOCAL session_replication_role = DEFAULT"))

    # Find audit IDs
    aud_rows = await db_session.execute(
        text(
            "SELECT id, link_id, reason FROM invalid_object_link_audits "
            "WHERE workspace_id = :ws AND purged_at IS NULL ORDER BY detected_at"
        ),
        {"ws": ws_id},
    )
    audits = aud_rows.mappings().all()
    assert len(audits) == 2
    a1 = next(a["id"] for a in audits if a["link_id"] == link1)
    a2 = next(a["id"] for a in audits if a["link_id"] == link2)

    # Invoke purge_invalid_object_links as WORKSPACE_ADMIN
    await bind_ctx(db_session, admin_id, ws_id)
    purge_res = await db_session.execute(
        text(
            "SELECT purged_audit_id, purged_link_id, activity_id "
            "FROM purge_invalid_object_links(:audit_ids, :actor_id, :reason)"
        ),
        {
            "audit_ids": [a1, a2],
            "actor_id": admin_id,
            "reason": "Cleanup archived blockers",
        },
    )
    purged = purge_res.mappings().all()
    assert len(purged) == 2
    assert {r["purged_audit_id"] for r in purged} == {a1, a2}
    assert {r["purged_link_id"] for r in purged} == {link1, link2}

    # Verify both object_links rows are deleted
    links_remaining = await db_session.execute(
        text("SELECT count(*) FROM object_links WHERE id IN (:l1, :l2)"),
        {"l1": link1, "l2": link2},
    )
    assert links_remaining.scalar_one() == 0

    # Verify both audit rows survive with purged_at, purged_by_id, purge_reason
    audits_surviving = await db_session.execute(
        text(
            "SELECT id, purged_at, purged_by_id, purge_reason "
            "FROM invalid_object_link_audits WHERE id IN (:a1, :a2)"
        ),
        {"a1": a1, "a2": a2},
    )
    surv_rows = audits_surviving.mappings().all()
    assert len(surv_rows) == 2
    for r in surv_rows:
        assert r["purged_at"] is not None
        assert r["purged_by_id"] == admin_id
        assert r["purge_reason"] == "Cleanup archived blockers"

    # Verify 2 INVALID_OBJECT_LINK_PURGED rows in activity_records
    act_rows = await db_session.execute(
        text(
            "SELECT id, event_type, actor_id, payload "
            "FROM activity_records "
            "WHERE workspace_id = :ws AND event_type = 'INVALID_OBJECT_LINK_PURGED' "
            "ORDER BY chain_seq"
        ),
        {"ws": ws_id},
    )
    acts = act_rows.mappings().all()
    assert len(acts) == 2
    for act in acts:
        assert act["actor_id"] == admin_id
        assert act["payload"]["purge_reason"] == "Cleanup archived blockers"
        assert act["payload"]["link_id"] in (str(link1), str(link2))

    # Verify hash chain validity
    chain_res = await db_session.execute(
        text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws)"),
        {"ws": ws_id},
    )
    chain = chain_res.mappings().one()
    assert chain["is_valid"] is True
    assert chain["checked_rows"] >= 2


async def test_02_multi_reason_sibling_closure_and_service_principal(
    db_session: AsyncSession,
) -> None:
    """Case 2: Sibling closure under single audit ID; SERVICE_PRINCIPAL succeeds."""
    ws_id = await _create_workspace(db_session)
    sp_id = await _create_service_principal(db_session, ws_id, display_name="system:trash-purge")
    await _assign_role(db_session, ws_id, sp_id, "WORKSPACE_ADMIN")

    user_id = await _create_user(db_session, ws_id, display_name="Regular User")
    proj_id = await _create_project(db_session, ws_id, identifier="PRJM")
    await _assign_role(
        db_session, ws_id, user_id, "MEMBER", scope_type="project", project_id=proj_id
    )

    st_res = await db_session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
        {"p": proj_id},
    )
    st_id = st_res.scalar_one()

    iss1 = await _create_issue(db_session, ws_id, proj_id, st_id, user_id, summary="Iss 1")
    iss2 = await _create_issue(db_session, ws_id, proj_id, st_id, user_id, summary="Iss 2")
    link_id = await _create_link(db_session, ws_id, iss1, "issue", iss2, "issue", "BLOCKS", user_id)

    # 1. Archive source issue -> ARCHIVED_POLICY_VIOLATION
    await db_session.execute(
        text("UPDATE objects SET archived_at = clock_timestamp() WHERE id = :id"),
        {"id": iss1},
    )

    # 2. Add DENY VIEW ACL on target for user -> PERMISSION_SEVERED
    await db_session.execute(
        text(
            "INSERT INTO resource_acl_entries ("
            "  workspace_id, object_id, principal_id, effect, capability_mask"
            ") VALUES (:ws_id, :oid, :uid, 'DENY', 1)"
        ),
        {"ws_id": ws_id, "oid": iss2, "uid": user_id},
    )

    # Run audit
    await db_session.execute(text("SELECT * FROM audit_object_links(:ws)"), {"ws": ws_id})

    # Verify link has 2 open audit rows
    aud_rows = await db_session.execute(
        text(
            "SELECT id, reason FROM invalid_object_link_audits "
            "WHERE link_id = :lid AND purged_at IS NULL ORDER BY reason"
        ),
        {"lid": link_id},
    )
    audits = aud_rows.mappings().all()
    assert len(audits) == 2
    reasons = {a["reason"] for a in audits}
    assert reasons == {"ARCHIVED_POLICY_VIOLATION", "PERMISSION_SEVERED"}

    # Pass ONLY ONE audit ID to purge_invalid_object_links
    chosen_audit_id = audits[0]["id"]
    sibling_audit_id = audits[1]["id"]

    await bind_ctx(db_session, sp_id, ws_id)
    purge_res = await db_session.execute(
        text(
            "SELECT purged_audit_id, purged_link_id, activity_id "
            "FROM purge_invalid_object_links(:audit_ids, :actor_id, :reason)"
        ),
        {
            "audit_ids": [chosen_audit_id],
            "actor_id": sp_id,
            "reason": "Purging archived and severed link via service principal",
        },
    )
    purged = purge_res.mappings().all()
    # Both audit rows are returned as closed
    assert len(purged) == 2
    assert {r["purged_audit_id"] for r in purged} == {chosen_audit_id, sibling_audit_id}
    assert all(r["purged_link_id"] == link_id for r in purged)

    # Verify link is deleted
    link_rem = await db_session.execute(
        text("SELECT count(*) FROM object_links WHERE id = :id"),
        {"id": link_id},
    )
    assert link_rem.scalar_one() == 0

    # Verify BOTH audits are marked as purged
    surv_rows = await db_session.execute(
        text(
            "SELECT id, purged_at, purged_by_id, purge_reason "
            "FROM invalid_object_link_audits WHERE link_id = :lid"
        ),
        {"lid": link_id},
    )
    for r in surv_rows.mappings().all():
        assert r["purged_at"] is not None
        assert r["purged_by_id"] == sp_id
        assert r["purge_reason"] == "Purging archived and severed link via service principal"

    # Exactly 1 activity record created for this link
    acts = await db_session.execute(
        text(
            "SELECT id, event_type, actor_id, payload FROM activity_records "
            "WHERE workspace_id = :ws AND event_type = 'INVALID_OBJECT_LINK_PURGED'"
        ),
        {"ws": ws_id},
    )
    act_list = acts.mappings().all()
    assert len(act_list) == 1
    assert act_list[0]["actor_id"] == sp_id
    payload = act_list[0]["payload"]
    assert set(payload["reasons"]) == {"ARCHIVED_POLICY_VIOLATION", "PERMISSION_SEVERED"}


async def test_03_security_bypass_and_role_checks(db_session: AsyncSession) -> None:
    """Case 3: Direct DELETE guard, ACTIVE deletion, role boundaries, actor match, RLS context."""
    ws_id = await _create_workspace(db_session)
    admin_id = await _create_user(db_session, ws_id, display_name="Admin")
    member_id = await _create_user(db_session, ws_id, display_name="Member")
    proj_admin_id = await _create_user(db_session, ws_id, display_name="Proj Admin")

    await _assign_role(db_session, ws_id, admin_id, "WORKSPACE_ADMIN")
    await _assign_role(db_session, ws_id, member_id, "WORKSPACE_MEMBER")

    proj_id = await _create_project(db_session, ws_id, identifier="SEC")
    await _assign_role(
        db_session, ws_id, proj_admin_id, "PROJECT_ADMIN", scope_type="project", project_id=proj_id
    )

    st_res = await db_session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
        {"p": proj_id},
    )
    st_id = st_res.scalar_one()

    iss1 = await _create_issue(db_session, ws_id, proj_id, st_id, admin_id, summary="Iss 1")
    iss2 = await _create_issue(db_session, ws_id, proj_id, st_id, admin_id, summary="Iss 2")
    iss3 = await _create_issue(db_session, ws_id, proj_id, st_id, admin_id, summary="Iss 3")

    link_active = await _create_link(
        db_session, ws_id, iss1, "issue", iss2, "issue", "BLOCKS", admin_id
    )
    link_flagged = await _create_link(
        db_session, ws_id, iss2, "issue", iss3, "issue", "BLOCKS", admin_id
    )

    # Sub-case 3a: Flag link_flagged
    await db_session.execute(
        text("UPDATE object_links SET link_state = 'FLAGGED_INVALID' WHERE id = :id"),
        {"id": link_flagged},
    )

    # Direct DELETE on FLAGGED_INVALID raises FLAGGED_LINK_REQUIRES_AUDITED_PURGE
    with pytest.raises(DBAPIError) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM object_links WHERE id = :id"),
                {"id": link_flagged},
            )
    assert "FLAGGED_LINK_REQUIRES_AUDITED_PURGE" in str(exc_info.value)

    # Direct DELETE on ACTIVE link succeeds
    await db_session.execute(
        text("DELETE FROM object_links WHERE id = :id"),
        {"id": link_active},
    )
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM object_links WHERE id = :id"),
            {"id": link_active},
        )
        == 0
    )

    # Create audit record for link_flagged so we can test purge_invalid_object_links
    aud_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO invalid_object_link_audits ("
            "  id, workspace_id, link_id, reason, link_snapshot"
            ") VALUES (:id, :ws_id, :lid, 'ARCHIVED_POLICY_VIOLATION', '{\"test\": true}'::jsonb)"
        ),
        {"id": aud_id, "ws_id": ws_id, "lid": link_flagged},
    )

    # Sub-case 3b: WORKSPACE_MEMBER calling purge raises PURGE_FORBIDDEN
    await bind_ctx(db_session, member_id, ws_id)
    with pytest.raises(DBAPIError) as exc_member:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT * FROM purge_invalid_object_links(:aids, :actor, 'reason text')"),
                {"aids": [aud_id], "actor": member_id},
            )
    assert "PURGE_FORBIDDEN" in str(exc_member.value)

    # Sub-case 3c: PROJECT_ADMIN calling purge raises PURGE_FORBIDDEN
    await bind_ctx(db_session, proj_admin_id, ws_id)
    with pytest.raises(DBAPIError) as exc_proj_admin:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT * FROM purge_invalid_object_links(:aids, :actor, 'reason text')"),
                {"aids": [aud_id], "actor": proj_admin_id},
            )
    assert "PURGE_FORBIDDEN" in str(exc_proj_admin.value)

    # Sub-case 3d: Actor mismatch raises PURGE_ACTOR_MISMATCH
    await bind_ctx(db_session, admin_id, ws_id)
    with pytest.raises(DBAPIError) as exc_mismatch:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT * FROM purge_invalid_object_links(:aids, :actor, 'reason text')"),
                {"aids": [aud_id], "actor": member_id},
            )
    assert "PURGE_ACTOR_MISMATCH" in str(exc_mismatch.value)

    # Sub-case 3e: Missing RLS context raises RLS_CONTEXT_REQUIRED
    await bind_ctx(db_session, None, None)
    with pytest.raises(DBAPIError) as exc_rls:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT * FROM purge_invalid_object_links(:aids, :actor, 'reason text')"),
                {"aids": [aud_id], "actor": admin_id},
            )
    assert "RLS_CONTEXT_REQUIRED" in str(exc_rls.value)


async def test_04_active_link_refusal_and_replay(db_session: AsyncSession) -> None:
    """Case 4: Tampering link_state to ACTIVE aborts purge; replay and resolved audits rejected."""
    ws_id = await _create_workspace(db_session)
    admin_id = await _create_user(db_session, ws_id, display_name="Admin")
    await _assign_role(db_session, ws_id, admin_id, "WORKSPACE_ADMIN")

    proj_id = await _create_project(db_session, ws_id, identifier="ACT")
    st_res = await db_session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
        {"p": proj_id},
    )
    st_id = st_res.scalar_one()

    iss1 = await _create_issue(db_session, ws_id, proj_id, st_id, admin_id, summary="Iss 1")
    iss2 = await _create_issue(db_session, ws_id, proj_id, st_id, admin_id, summary="Iss 2")
    link_id = await _create_link(
        db_session, ws_id, iss1, "issue", iss2, "issue", "BLOCKS", admin_id
    )

    # Create audit row while link is ACTIVE (simulating tampered state)
    aud_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO invalid_object_link_audits ("
            "  id, workspace_id, link_id, reason, link_snapshot"
            ") VALUES (:id, :ws_id, :lid, 'ARCHIVED_POLICY_VIOLATION', '{\"test\": true}'::jsonb)"
        ),
        {"id": aud_id, "ws_id": ws_id, "lid": link_id},
    )

    await bind_ctx(db_session, admin_id, ws_id)

    # Sub-case 4a: Link is ACTIVE -> PURGE_ACTIVE_LINK_REFUSED, zero rows deleted
    with pytest.raises(DBAPIError) as exc_active:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT * FROM purge_invalid_object_links(:aids, :actor, 'Purge attempt')"),
                {"aids": [aud_id], "actor": admin_id},
            )
    assert "PURGE_ACTIVE_LINK_REFUSED" in str(exc_active.value)
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM object_links WHERE id = :id"),
            {"id": link_id},
        )
        == 1
    )

    # Flag the link properly
    await db_session.execute(
        text("UPDATE object_links SET link_state = 'FLAGGED_INVALID' WHERE id = :id"),
        {"id": link_id},
    )

    # Valid purge succeeds
    purge_first = await db_session.execute(
        text("SELECT * FROM purge_invalid_object_links(:aids, :actor, 'First purge')"),
        {"aids": [aud_id], "actor": admin_id},
    )
    assert len(purge_first.mappings().all()) == 1

    # Sub-case 4b: Replay with already-purged audit -> PURGE_ALREADY_EXECUTED
    with pytest.raises(DBAPIError) as exc_replay:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT * FROM purge_invalid_object_links(:aids, :actor, 'Replay purge')"),
                {"aids": [aud_id], "actor": admin_id},
            )
    assert "PURGE_ALREADY_EXECUTED" in str(exc_replay.value)

    # Sub-case 4c: Resolved audit -> PURGE_AUDIT_RESOLVED
    link2 = await _create_link(
        db_session, ws_id, iss1, "issue", iss2, "issue", "RELATES_TO", admin_id
    )
    await db_session.execute(
        text("UPDATE object_links SET link_state = 'FLAGGED_INVALID' WHERE id = :id"),
        {"id": link2},
    )
    aud2_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO invalid_object_link_audits ("
            "  id, workspace_id, link_id, reason, link_snapshot, resolved_at"
            ") VALUES ("
            "  :id, :ws_id, :lid, 'ARCHIVED_POLICY_VIOLATION', '{\"test\": true}'::jsonb, "
            "  clock_timestamp()"
            ")"
        ),
        {"id": aud2_id, "ws_id": ws_id, "lid": link2},
    )

    with pytest.raises(DBAPIError) as exc_resolved:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT * FROM purge_invalid_object_links(:aids, :actor, 'Purge resolved')"),
                {"aids": [aud2_id], "actor": admin_id},
            )
    assert "PURGE_AUDIT_RESOLVED" in str(exc_resolved.value)

    # Sub-case 4d: Unknown audit ID -> PURGE_AUDIT_NOT_FOUND
    with pytest.raises(DBAPIError) as exc_not_found:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT * FROM purge_invalid_object_links(:aids, :actor, 'Purge unknown')"),
                {"aids": [uuid.uuid4()], "actor": admin_id},
            )
    assert "PURGE_AUDIT_NOT_FOUND" in str(exc_not_found.value)

    # Sub-case 4e: Cross-workspace audit ID -> PURGE_AUDIT_NOT_FOUND
    ws2_id = await _create_workspace(db_session)
    aud_ws2 = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO invalid_object_link_audits ("
            "  id, workspace_id, link_id, reason, link_snapshot"
            ") VALUES (:id, :ws_id, :lid, 'ARCHIVED_POLICY_VIOLATION', '{\"test\": true}'::jsonb)"
        ),
        {"id": aud_ws2, "ws_id": ws2_id, "lid": link2},
    )

    with pytest.raises(DBAPIError) as exc_cross_ws:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT * FROM purge_invalid_object_links(:aids, :actor, 'Cross ws purge')"),
                {"aids": [aud_ws2], "actor": admin_id},
            )
    assert "PURGE_AUDIT_NOT_FOUND" in str(exc_cross_ws.value)


async def test_05_boundary_conditions(db_session: AsyncSession) -> None:
    """Case 5: Array boundaries, reason boundaries (<3, >1000), duplicate deduplication."""
    ws_id = await _create_workspace(db_session)
    admin_id = await _create_user(db_session, ws_id, display_name="Admin")
    await _assign_role(db_session, ws_id, admin_id, "WORKSPACE_ADMIN")

    proj_id = await _create_project(db_session, ws_id, identifier="BND")
    st_res = await db_session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
        {"p": proj_id},
    )
    st_id = st_res.scalar_one()

    iss1 = await _create_issue(db_session, ws_id, proj_id, st_id, admin_id, summary="Iss 1")
    iss2 = await _create_issue(db_session, ws_id, proj_id, st_id, admin_id, summary="Iss 2")
    link_id = await _create_link(
        db_session, ws_id, iss1, "issue", iss2, "issue", "BLOCKS", admin_id
    )
    await db_session.execute(
        text("UPDATE object_links SET link_state = 'FLAGGED_INVALID' WHERE id = :id"),
        {"id": link_id},
    )

    aud_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO invalid_object_link_audits ("
            "  id, workspace_id, link_id, reason, link_snapshot"
            ") VALUES (:id, :ws_id, :lid, 'ARCHIVED_POLICY_VIOLATION', '{\"test\": true}'::jsonb)"
        ),
        {"id": aud_id, "ws_id": ws_id, "lid": link_id},
    )

    await bind_ctx(db_session, admin_id, ws_id)

    # 1. Empty array -> PURGE_AUDIT_IDS_INVALID
    with pytest.raises(DBAPIError) as exc_empty:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "SELECT * FROM purge_invalid_object_links('{}'::uuid[], :actor, 'Valid reason')"
                ),
                {"actor": admin_id},
            )
    assert "PURGE_AUDIT_IDS_INVALID" in str(exc_empty.value)

    # 2. Array containing NULL -> PURGE_AUDIT_IDS_INVALID
    with pytest.raises(DBAPIError) as exc_null_item:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "SELECT * FROM purge_invalid_object_links("
                    "  ARRAY[:id, NULL]::uuid[], :actor, 'Valid reason'"
                    ")"
                ),
                {"id": aud_id, "actor": admin_id},
            )
    assert "PURGE_AUDIT_IDS_INVALID" in str(exc_null_item.value)

    # 3. Whitespace-only reason -> PURGE_REASON_REQUIRED
    with pytest.raises(DBAPIError) as exc_ws_reason:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT * FROM purge_invalid_object_links(:aids, :actor, '   ')"),
                {"aids": [aud_id], "actor": admin_id},
            )
    assert "PURGE_REASON_REQUIRED" in str(exc_ws_reason.value)

    # 4. Reason too short (2 chars) -> PURGE_REASON_REQUIRED
    with pytest.raises(DBAPIError) as exc_short:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT * FROM purge_invalid_object_links(:aids, :actor, 'ab')"),
                {"aids": [aud_id], "actor": admin_id},
            )
    assert "PURGE_REASON_REQUIRED" in str(exc_short.value)

    # 5. Reason too long (>1000 chars) -> PURGE_REASON_REQUIRED
    with pytest.raises(DBAPIError) as exc_long:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT * FROM purge_invalid_object_links(:aids, :actor, :reason)"),
                {"aids": [aud_id], "actor": admin_id, "reason": "x" * 1001},
            )
    assert "PURGE_REASON_REQUIRED" in str(exc_long.value)

    # 6. Duplicate IDs in array are deduplicated deterministically and succeed
    res_dedup = await db_session.execute(
        text("SELECT * FROM purge_invalid_object_links(:aids, :actor, 'Valid deduplicated purge')"),
        {"aids": [aud_id, aud_id], "actor": admin_id},
    )
    rows = res_dedup.mappings().all()
    assert len(rows) == 1
    assert rows[0]["purged_audit_id"] == aud_id


async def test_06_verify_catalog_gate_remains_clean(db_session: AsyncSession) -> None:
    """Case 6: Verify FORCE RLS, trigger presence, security definer catalog status."""
    # Verify purge_invalid_object_links function signature and security properties
    proc_info = await db_session.execute(
        text(
            "SELECT p.prosecdef, p.provolatile, n.nspname "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = 'purge_invalid_object_links'"
        )
    )
    p_row = proc_info.mappings().one()
    assert p_row["prosecdef"] is True
    assert p_row["provolatile"] in ("v", b"v")  # VOLATILE

    # Verify execution permission granted to kanban_app
    has_perm = await db_session.scalar(
        text(
            "SELECT has_function_privilege("
            "  'kanban_app', 'purge_invalid_object_links(uuid[], uuid, text)', 'EXECUTE'"
            ")"
        )
    )
    assert has_perm is True

    # Verify trigger exists on object_links
    trg = await db_session.execute(
        text(
            "SELECT tgname FROM pg_trigger "
            "WHERE tgname = 'object_links_flagged_delete_guard_bd_trg' AND NOT tgisinternal"
        )
    )
    assert len(trg.mappings().all()) == 1

    # Verify invalid_object_link_audits FORCE RLS remains enabled
    rls = await db_session.execute(
        text(
            "SELECT c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = 'invalid_object_link_audits'"
        )
    )
    r_row = rls.mappings().one()
    assert r_row["relrowsecurity"] is True
    assert r_row["relforcerowsecurity"] is True
