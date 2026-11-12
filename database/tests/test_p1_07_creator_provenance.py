"""Unit tests for Phase 1 created-by provenance trigger with admin override and ledger."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from database.tests.conftest import bind_ctx

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class IssueContext:
    """Project and user context for issue creation."""

    workspace_id: uuid.UUID
    project_id: uuid.UUID
    identifier: str
    user_id: uuid.UUID
    state_id: uuid.UUID
    priority_id: uuid.UUID


@dataclass(frozen=True)
class IssueParams:
    """Attributes for issue creation."""

    summary: str = "Test Issue"
    original_creator_id: uuid.UUID | None = None
    creator_modified_by_id: uuid.UUID | None = None
    creator_modified_at: datetime | None = None


async def _create_workspace(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Test Workspace",
) -> uuid.UUID:
    """Create a test workspace and return its UUID."""
    ws_slug = slug or f"ws-{uuid.uuid4().hex[:12]}"
    row = await session.execute(
        text("INSERT INTO workspaces (slug, name) VALUES (:slug, :name) RETURNING id"),
        {"slug": ws_slug, "name": name},
    )
    val = row.scalar_one()
    assert isinstance(val, uuid.UUID)
    return val


async def _create_principal(
    session: AsyncSession,
    ws_id: uuid.UUID,
    *,
    principal_type: str = "USER",
    display_name: str = "Test Principal",
) -> uuid.UUID:
    """Create a principal in the principals table."""
    row = await session.execute(
        text(
            "INSERT INTO principals (workspace_id, principal_type, display_name) "
            "VALUES (:ws_id, :pt, :name) RETURNING id"
        ),
        {"ws_id": ws_id, "pt": principal_type, "name": display_name},
    )
    val = row.scalar_one()
    assert isinstance(val, uuid.UUID)
    return val


async def _create_user(
    session: AsyncSession,
    ws_id: uuid.UUID,
    email: str,
    display_name: str = "Test User",
) -> uuid.UUID:
    """Create a user in principals, objects, and users tables."""
    u_id = await _create_principal(session, ws_id, principal_type="USER", display_name=display_name)
    await session.execute(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws_id, NULL::uuid, :ckey, :title, :creator, :id"
            ")"
        ),
        {
            "ws_id": ws_id,
            "ckey": f"usr-{u_id.hex}",
            "title": display_name,
            "creator": u_id,
            "id": u_id,
        },
    )
    await session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
        {"id": u_id, "ws_id": ws_id, "email": email},
    )
    return u_id


async def _create_group(
    session: AsyncSession,
    ws_id: uuid.UUID,
    name: str,
) -> uuid.UUID:
    """Create a principal and matching groups row."""
    p_id = await _create_principal(session, ws_id, principal_type="GROUP", display_name=name)
    await session.execute(
        text("INSERT INTO groups (id, workspace_id, name) VALUES (:id, :ws_id, :name)"),
        {"id": p_id, "ws_id": ws_id, "name": name},
    )
    return p_id


async def _bind_role(
    session: AsyncSession,
    ws_id: uuid.UUID,
    principal_id: uuid.UUID,
    role: str,
    project_id: uuid.UUID | None = None,
) -> None:
    """Insert a role_bindings row inferring scope_type from role and project_id."""
    if project_id is not None:
        scope = "project"
    elif role == "SERVER_ADMIN":
        scope = "server"
    else:
        scope = "workspace"

    await session.execute(
        text(
            "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type, project_id) "
            "VALUES (:ws_id, :p_id, CAST(:role AS rbac_role), :scope, :proj_id)"
        ),
        {
            "ws_id": ws_id,
            "p_id": principal_id,
            "role": role,
            "scope": scope,
            "proj_id": project_id,
        },
    )


async def _create_project(
    session: AsyncSession,
    ws_id: uuid.UUID,
    creator_id: uuid.UUID,
    identifier: str = "PRJ",
    name: str = "Test Project",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create a project and return (project_id, default_state_id, default_priority_id)."""
    p_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws, NULL::uuid, :ident, :name, :creator, :id"
            ")"
        ),
        {"ws": ws_id, "ident": identifier, "name": name, "creator": creator_id, "id": p_id},
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws, :ident, :name)"
        ),
        {"id": p_id, "ws": ws_id, "ident": identifier, "name": name},
    )

    state_row = await session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p AND is_default = true"),
        {"p": p_id},
    )
    state_id = state_row.scalar_one()
    assert isinstance(state_id, uuid.UUID)

    prio_row = await session.execute(
        text("SELECT id FROM project_priorities WHERE project_id = :p AND is_default = true"),
        {"p": p_id},
    )
    prio_id = prio_row.scalar_one()
    assert isinstance(prio_id, uuid.UUID)

    return p_id, state_id, prio_id


async def _create_issue(
    session: AsyncSession,
    ctx: IssueContext,
    params: IssueParams | None = None,
) -> tuple[uuid.UUID, int]:
    """Allocate sequence and insert issue."""
    p = params or IssueParams()
    seq_row = await session.execute(
        text("SELECT allocate_issue_sequence(:p)"),
        {"p": ctx.project_id},
    )
    seq = seq_row.scalar_one()
    assert isinstance(seq, int)

    i_id = uuid.uuid4()
    canonical_key = f"{ctx.identifier}-{seq}"

    await session.execute(
        text(
            "SELECT register_object(  'issue'::object_kind, :ws, :p, :ckey, :summary, :user, :id)"
        ),
        {
            "ws": ctx.workspace_id,
            "p": ctx.project_id,
            "ckey": canonical_key,
            "summary": p.summary,
            "user": ctx.user_id,
            "id": i_id,
        },
    )

    orig_user = p.original_creator_id or ctx.user_id
    await session.execute(
        text(
            "INSERT INTO issues ("
            "  id, workspace_id, project_id, sequence_id, summary, "
            "  description_markdown, state_id, priority_id, "
            "  created_by_id, original_created_by_id, creator_modified_by_id, "
            "  creator_modified_at, board_rank"
            ") VALUES ("
            "  :id, :ws, :p, :seq, :summary, "
            "  '', :state, :prio, "
            "  :user, :orig_user, :mod_by, :mod_at, '0|hzzzzz:'"
            ")"
        ),
        {
            "id": i_id,
            "ws": ctx.workspace_id,
            "p": ctx.project_id,
            "seq": seq,
            "summary": p.summary,
            "state": ctx.state_id,
            "prio": ctx.priority_id,
            "user": ctx.user_id,
            "orig_user": orig_user,
            "mod_by": p.creator_modified_by_id,
            "mod_at": p.creator_modified_at,
        },
    )
    return i_id, seq


async def test_01_positive_project_admin_override(db_session: AsyncSession) -> None:
    """Test 1: PROJECT_ADMIN on project overrides created_by_id U1 -> U2."""
    ws = await _create_workspace(db_session)
    u1 = await _create_user(db_session, ws, "u1@example.com", "User One")
    u2 = await _create_user(db_session, ws, "u2@example.com", "User Two")
    admin = await _create_user(db_session, ws, "admin@example.com", "Project Admin")
    p, state_id, prio_id = await _create_project(db_session, ws, admin, "KAN")

    await _bind_role(db_session, ws, admin, "PROJECT_ADMIN", p)
    ctx = IssueContext(ws, p, "KAN", u1, state_id, prio_id)
    i_id, _ = await _create_issue(db_session, ctx)

    # Set session RLS to admin
    await bind_ctx(db_session, admin, ws)

    # Perform creator override
    await db_session.execute(
        text("UPDATE issues SET created_by_id = :u2 WHERE id = :i"),
        {"u2": u2, "i": i_id},
    )

    # Verify issues row
    issue_row = (
        (
            await db_session.execute(
                text(
                    "SELECT created_by_id, original_created_by_id, creator_modified_by_id, "
                    "creator_modified_at FROM issues WHERE id = :i"
                ),
                {"i": i_id},
            )
        )
        .mappings()
        .one()
    )

    assert issue_row["created_by_id"] == u2
    assert issue_row["original_created_by_id"] == u1
    assert issue_row["creator_modified_by_id"] == admin
    assert issue_row["creator_modified_at"] is not None

    # Verify objects table is updated
    obj_row = (
        (
            await db_session.execute(
                text("SELECT created_by_id FROM objects WHERE id = :i"),
                {"i": i_id},
            )
        )
        .mappings()
        .one()
    )
    assert obj_row["created_by_id"] == u2

    # Verify activity_records
    act_rows = (
        (
            await db_session.execute(
                text(
                    "SELECT id, workspace_id, object_id, object_type, actor_id, event_type, "
                    "payload, prev_hash, row_hash FROM activity_records WHERE object_id = :i"
                ),
                {"i": i_id},
            )
        )
        .mappings()
        .all()
    )

    assert len(act_rows) == 1
    act = act_rows[0]
    assert act["event_type"] == "CREATOR_OVERRIDDEN"
    assert act["actor_id"] == admin
    assert act["object_type"] == "issue"
    assert act["payload"]["from_user_id"] == str(u1)
    assert act["payload"]["to_user_id"] == str(u2)
    assert act["payload"]["original_created_by_id"] == str(u1)
    assert len(bytes(act["prev_hash"])) == 32
    assert len(bytes(act["row_hash"])) == 32


async def test_02_positive_server_admin_direct_and_group(db_session: AsyncSession) -> None:
    """Test 2: SERVER_ADMIN at server scope and SERVER_ADMIN via group membership can override."""
    ws = await _create_workspace(db_session)
    u1 = await _create_user(db_session, ws, "u1@example.com", "User One")
    u2 = await _create_user(db_session, ws, "u2@example.com", "User Two")
    u3 = await _create_user(db_session, ws, "u3@example.com", "User Three")
    server_admin = await _create_user(db_session, ws, "sadmin@example.com", "Server Admin")
    group_user = await _create_user(db_session, ws, "gadmin@example.com", "Group Admin User")
    admin_group = await _create_group(db_session, ws, "AdminGroup")

    p, state_id, prio_id = await _create_project(db_session, ws, u1, "KAN")
    ctx = IssueContext(ws, p, "KAN", u1, state_id, prio_id)
    i_id, _ = await _create_issue(db_session, ctx)

    # 2a: Direct SERVER_ADMIN binding
    await _bind_role(db_session, ws, server_admin, "SERVER_ADMIN")

    await bind_ctx(db_session, server_admin, ws)
    await db_session.execute(
        text("UPDATE issues SET created_by_id = :u2 WHERE id = :i"),
        {"u2": u2, "i": i_id},
    )

    row1 = (
        (
            await db_session.execute(
                text("SELECT created_by_id, creator_modified_by_id FROM issues WHERE id = :i"),
                {"i": i_id},
            )
        )
        .mappings()
        .one()
    )
    assert row1["created_by_id"] == u2
    assert row1["creator_modified_by_id"] == server_admin

    # 2b: SERVER_ADMIN through group membership
    await db_session.execute(
        text(
            "INSERT INTO principal_group_edges (member_id, group_id, workspace_id) "
            "VALUES (:u, :g, :ws)"
        ),
        {"u": group_user, "g": admin_group, "ws": ws},
    )
    await _bind_role(db_session, ws, admin_group, "SERVER_ADMIN")

    await bind_ctx(db_session, group_user, ws)
    await db_session.execute(
        text("UPDATE issues SET created_by_id = :u3 WHERE id = :i"),
        {"u3": u3, "i": i_id},
    )

    row2 = (
        (
            await db_session.execute(
                text("SELECT created_by_id, creator_modified_by_id FROM issues WHERE id = :i"),
                {"i": i_id},
            )
        )
        .mappings()
        .one()
    )
    assert row2["created_by_id"] == u3
    assert row2["creator_modified_by_id"] == group_user


async def test_03_negative_forbidden_roles(db_session: AsyncSession) -> None:
    """Test 3: Non-authorized roles raise CREATOR_OVERRIDE_FORBIDDEN."""
    ws = await _create_workspace(db_session)
    u1 = await _create_user(db_session, ws, "u1@example.com", "User One")
    u2 = await _create_user(db_session, ws, "u2@example.com", "User Two")
    member_user = await _create_user(db_session, ws, "member@example.com", "Member User")
    ws_admin = await _create_user(db_session, ws, "wsadmin@example.com", "WS Admin")
    other_proj_admin = await _create_user(db_session, ws, "otheradmin@example.com", "Other Admin")

    p1, s1, prio1 = await _create_project(db_session, ws, u1, "P1")
    p2, _, _ = await _create_project(db_session, ws, u1, "P2")

    await _bind_role(db_session, ws, member_user, "MEMBER", p1)
    await _bind_role(db_session, ws, ws_admin, "WORKSPACE_ADMIN")
    await _bind_role(db_session, ws, other_proj_admin, "PROJECT_ADMIN", p2)

    ctx1 = IssueContext(ws, p1, "P1", u1, s1, prio1)
    i_id, _ = await _create_issue(db_session, ctx1)

    # 3a: MEMBER on p1
    await bind_ctx(db_session, member_user, ws)
    with pytest.raises((IntegrityError, DBAPIError)) as exc_m:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET created_by_id = :u2 WHERE id = :i"),
                {"u2": u2, "i": i_id},
            )
    assert "CREATOR_OVERRIDE_FORBIDDEN" in str(exc_m.value)

    # 3b: WORKSPACE_ADMIN on ws
    await bind_ctx(db_session, ws_admin, ws)
    with pytest.raises((IntegrityError, DBAPIError)) as exc_ws:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET created_by_id = :u2 WHERE id = :i"),
                {"u2": u2, "i": i_id},
            )
    assert "CREATOR_OVERRIDE_FORBIDDEN" in str(exc_ws.value)

    # 3c: PROJECT_ADMIN of p2 attempting override on p1 issue
    await bind_ctx(db_session, other_proj_admin, ws)
    with pytest.raises((IntegrityError, DBAPIError)) as exc_other:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET created_by_id = :u2 WHERE id = :i"),
                {"u2": u2, "i": i_id},
            )
    assert "CREATOR_OVERRIDE_FORBIDDEN" in str(exc_other.value)

    # Verify no activity records were written
    act_count = (
        await db_session.execute(
            text("SELECT count(*) FROM activity_records WHERE object_id = :i"),
            {"i": i_id},
        )
    ).scalar_one()
    assert act_count == 0


async def test_04_negative_provenance_immutability(db_session: AsyncSession) -> None:
    """Test 4: Mutating original_created_by_id or creator_modified_* raises immutability error."""
    ws = await _create_workspace(db_session)
    u1 = await _create_user(db_session, ws, "u1@example.com", "User One")
    u2 = await _create_user(db_session, ws, "u2@example.com", "User Two")
    admin = await _create_user(db_session, ws, "admin@example.com", "Admin")
    p, state_id, prio_id = await _create_project(db_session, ws, admin, "KAN")
    await _bind_role(db_session, ws, admin, "PROJECT_ADMIN", p)

    ctx = IssueContext(ws, p, "KAN", u1, state_id, prio_id)
    i_id, _ = await _create_issue(db_session, ctx)
    await bind_ctx(db_session, admin, ws)

    # 4a: Updating original_created_by_id raises CREATOR_PROVENANCE_IMMUTABLE
    with pytest.raises((IntegrityError, DBAPIError)) as exc_orig:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET original_created_by_id = :u2 WHERE id = :i"),
                {"u2": u2, "i": i_id},
            )
    assert "CREATOR_PROVENANCE_IMMUTABLE" in str(exc_orig.value)

    # 4b: Directly updating creator_modified_by_id raises CREATOR_PROVENANCE_IMMUTABLE
    with pytest.raises((IntegrityError, DBAPIError)) as exc_mod_by:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET creator_modified_by_id = :admin WHERE id = :i"),
                {"admin": admin, "i": i_id},
            )
    assert "CREATOR_PROVENANCE_IMMUTABLE" in str(exc_mod_by.value)

    # 4c: Directly updating creator_modified_at raises CREATOR_PROVENANCE_IMMUTABLE
    with pytest.raises((IntegrityError, DBAPIError)) as exc_mod_at:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET creator_modified_at = clock_timestamp() WHERE id = :i"),
                {"i": i_id},
            )
    assert "CREATOR_PROVENANCE_IMMUTABLE" in str(exc_mod_at.value)


async def test_05_negative_context_and_workspace_mismatch(db_session: AsyncSession) -> None:
    """Test 5: Context, actor user, and workspace checks."""
    ws1 = await _create_workspace(db_session)
    ws2 = await _create_workspace(db_session)

    u1 = await _create_user(db_session, ws1, "u1@example.com", "User One")
    u_other_ws = await _create_user(db_session, ws2, "u_other@example.com", "Other WS User")
    admin = await _create_user(db_session, ws1, "admin@example.com", "Admin")

    p, state_id, prio_id = await _create_project(db_session, ws1, admin, "KAN")
    await _bind_role(db_session, ws1, admin, "PROJECT_ADMIN", p)
    ctx = IssueContext(ws1, p, "KAN", u1, state_id, prio_id)
    i_id, _ = await _create_issue(db_session, ctx)

    # 5a: No RLS context
    await bind_ctx(db_session, None, None)
    with pytest.raises((IntegrityError, DBAPIError)) as exc_no_ctx:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET created_by_id = :u2 WHERE id = :i"),
                {"u2": admin, "i": i_id},
            )
    assert "RLS_CONTEXT_REQUIRED" in str(exc_no_ctx.value)

    # 5b: Actor is not a user (e.g. an agent principal)
    agent_id = await _create_principal(
        db_session, ws1, principal_type="AGENT", display_name="AI Agent"
    )
    await _bind_role(db_session, ws1, agent_id, "PROJECT_ADMIN", p)
    await bind_ctx(db_session, agent_id, ws1)

    with pytest.raises((IntegrityError, DBAPIError)) as exc_not_user:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET created_by_id = :u2 WHERE id = :i"),
                {"u2": admin, "i": i_id},
            )
    assert "CREATOR_OVERRIDE_ACTOR_NOT_USER" in str(exc_not_user.value)

    # 5c: Target user from another workspace
    await bind_ctx(db_session, admin, ws1)
    with pytest.raises((IntegrityError, DBAPIError)) as exc_ws_mismatch:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET created_by_id = :other WHERE id = :i"),
                {"other": u_other_ws, "i": i_id},
            )
    assert "CREATOR_OVERRIDE_WORKSPACE_MISMATCH" in str(exc_ws_mismatch.value)


async def test_06_boundary_insert_sanitization_and_summary_update(
    db_session: AsyncSession,
) -> None:
    """Test 6: INSERT resets forged columns; UPDATE on summary writes no activity row."""
    ws = await _create_workspace(db_session)
    u1 = await _create_user(db_session, ws, "u1@example.com", "User One")
    u2 = await _create_user(db_session, ws, "u2@example.com", "User Two")
    p, state_id, prio_id = await _create_project(db_session, ws, u1, "KAN")

    # 6a: INSERT with forged original_created_by_id != created_by_id and non-null creator_modified_*
    ctx = IssueContext(ws, p, "KAN", u1, state_id, prio_id)
    params = IssueParams(
        summary="Forged Insert Test",
        original_creator_id=u2,
        creator_modified_by_id=u2,
        creator_modified_at=datetime.now(UTC),
    )
    i_id, _ = await _create_issue(db_session, ctx, params)

    row = (
        (
            await db_session.execute(
                text(
                    "SELECT created_by_id, original_created_by_id, creator_modified_by_id, "
                    "creator_modified_at FROM issues WHERE id = :i"
                ),
                {"i": i_id},
            )
        )
        .mappings()
        .one()
    )

    assert row["created_by_id"] == u1
    assert row["original_created_by_id"] == u1  # Forged u2 replaced by u1
    assert row["creator_modified_by_id"] is None
    assert row["creator_modified_at"] is None

    # 6b: UPDATE touching only summary does not write activity rows
    await bind_ctx(db_session, u1, ws)
    await db_session.execute(
        text("UPDATE issues SET summary = 'Safe Summary Update' WHERE id = :i"),
        {"i": i_id},
    )

    updated_row = (
        (
            await db_session.execute(
                text("SELECT summary, creator_modified_at FROM issues WHERE id = :i"),
                {"i": i_id},
            )
        )
        .mappings()
        .one()
    )
    assert updated_row["summary"] == "Safe Summary Update"
    assert updated_row["creator_modified_at"] is None

    # UPDATE with created_by_id = created_by_id (no change) also writes zero activity rows
    await db_session.execute(
        text("UPDATE issues SET created_by_id = created_by_id WHERE id = :i"),
        {"i": i_id},
    )

    act_count = (
        await db_session.execute(
            text("SELECT count(*) FROM activity_records WHERE object_id = :i"),
            {"i": i_id},
        )
    ).scalar_one()
    assert act_count == 0
