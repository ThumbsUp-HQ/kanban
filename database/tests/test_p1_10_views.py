"""Unit tests for Phase 1 views table, view_layout enum, and filter/WIP JSON validators."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from database.tests.conftest import bind_workspace_admin, bootstrap_workspace_admin

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _is_check_violation(exc: IntegrityError) -> bool:
    """Return True if exception indicates a PostgreSQL check_violation (23514)."""
    sqlstate = getattr(exc.orig, "sqlstate", None)
    return sqlstate == "23514" or "checkviolation" in str(exc).lower() or "23514" in str(exc)


async def _create_workspace(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Test Workspace",
) -> uuid.UUID:
    """Create a test workspace."""
    ws_id, _ = await bootstrap_workspace_admin(session, slug=slug, name=name)
    return ws_id


async def _create_principal(
    session: AsyncSession,
    ws_id: uuid.UUID,
    *,
    principal_type: str = "USER",
    display_name: str = "Test Principal",
) -> uuid.UUID:
    """Create a principal in the principals table."""
    await bind_workspace_admin(session, ws_id)
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


async def _create_project(
    session: AsyncSession,
    ws_id: uuid.UUID,
    *,
    identifier: str = "PRJ",
    name: str = "Test Project",
) -> uuid.UUID:
    """Register and create a project in the database."""
    await bind_workspace_admin(session, ws_id)
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


async def _register_view_object(
    session: AsyncSession,
    ws_id: uuid.UUID,
    project_id: uuid.UUID | None,
    canonical_key: str,
    title: str,
) -> uuid.UUID:
    """Register a view entity in the objects spine."""
    await session.execute(text("RESET SESSION AUTHORIZATION"))
    u_id = uuid.uuid4()
    row = await session.execute(
        text(
            "SELECT register_object(  'view'::object_kind, :ws_id, :proj_id, :key, :title, :u_id)"
        ),
        {
            "ws_id": ws_id,
            "proj_id": project_id,
            "key": canonical_key,
            "title": title,
            "u_id": u_id,
        },
    )
    val = row.scalar_one()
    assert isinstance(val, uuid.UUID)
    await session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    await bind_workspace_admin(session, ws_id)
    return val


async def test_01_views_layouts_and_sha256(app_session: AsyncSession) -> None:
    """Test inserting views across all 5 layouts, 2D swimlanes, and SHA-256 generation."""
    ws_id = await _create_workspace(app_session)
    user_id = await _create_principal(app_session, ws_id, principal_type="USER")
    proj_id = await _create_project(app_session, ws_id, identifier="LAY")

    layouts = ["list", "board", "table", "calendar", "timeline"]
    state_uuid = str(uuid.uuid4())
    wip_json = json.dumps({state_uuid: {"soft": 4, "hard": 6}})
    filter_json = json.dumps(
        {
            "state_groups": ["started"],
            "priority_ids": [str(uuid.uuid4())],
            "search_query": "perf regression",
        }
    )

    for idx, layout in enumerate(layouts):
        v_key = f"VIEW-L{idx}"
        v_title = f"{layout.capitalize()} View"
        v_summary = f"Summary for {layout} view with details."
        v_id = await _register_view_object(app_session, ws_id, proj_id, v_key, v_title)

        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, visibility, "
                "  name, summary_markdown, layout, group_by, sub_group_by, "
                "  filters_json, wip_limits_json"
                ") VALUES ("
                "  :id, :ws_id, :proj_id, :owner_id, 'project', "
                "  :name, :summary, CAST(:layout AS view_layout), 'state', 'assignee', "
                "  CAST(:filters AS jsonb), CAST(:wip AS jsonb)"
                ")"
            ),
            {
                "id": v_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "owner_id": user_id,
                "name": v_title,
                "summary": v_summary,
                "layout": layout,
                "filters": filter_json,
                "wip": wip_json,
            },
        )

        # Verify query and summary_sha256 digest match
        res = await app_session.execute(
            text("SELECT layout, group_by, sub_group_by, summary_sha256 FROM views WHERE id = :id"),
            {"id": v_id},
        )
        row = res.fetchone()
        assert row is not None
        assert row.layout == layout
        assert row.group_by == "state"
        assert row.sub_group_by == "assignee"
        expected_digest = hashlib.sha256(v_summary.encode("utf-8")).digest()
        assert bytes(row.summary_sha256) == expected_digest


async def test_02_views_visibility_and_scope(app_session: AsyncSession) -> None:
    """Test workspace-scoped views (NULL project_id) and private project views."""
    ws_id = await _create_workspace(app_session)
    user_id = await _create_principal(app_session, ws_id, principal_type="USER")
    proj_id = await _create_project(app_session, ws_id, identifier="SCP")

    # Workspace-scoped view (project_id IS NULL, visibility = 'workspace')
    ws_view_id = await _register_view_object(
        app_session, ws_id, None, "VIEW-WS", "Workspace Global View"
    )
    await app_session.execute(
        text(
            "INSERT INTO views ("
            "  id, workspace_id, project_id, owner_principal_id, visibility, name"
            ") VALUES (:id, :ws_id, NULL, :owner_id, 'workspace', 'Workspace Global View')"
        ),
        {"id": ws_view_id, "ws_id": ws_id, "owner_id": user_id},
    )

    # Private project view (project_id NOT NULL, visibility = 'private')
    priv_view_id = await _register_view_object(
        app_session, ws_id, proj_id, "VIEW-PRIV", "Private Project View"
    )
    await app_session.execute(
        text(
            "INSERT INTO views ("
            "  id, workspace_id, project_id, owner_principal_id, visibility, name"
            ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'private', 'Private Project View')"
        ),
        {"id": priv_view_id, "ws_id": ws_id, "proj_id": proj_id, "owner_id": user_id},
    )

    res_ws = await app_session.execute(
        text("SELECT project_id, visibility FROM views WHERE id = :id"),
        {"id": ws_view_id},
    )
    r_ws = res_ws.fetchone()
    assert r_ws is not None
    assert r_ws.project_id is None
    assert r_ws.visibility == "workspace"

    res_priv = await app_session.execute(
        text("SELECT project_id, visibility FROM views WHERE id = :id"),
        {"id": priv_view_id},
    )
    r_priv = res_priv.fetchone()
    assert r_priv is not None
    assert r_priv.project_id == proj_id
    assert r_priv.visibility == "private"


async def test_03_views_layout_and_filter_checks(app_session: AsyncSession) -> None:
    """Test CHECK constraint rejections on layouts, visibility, and filter JSON."""
    ws_id = await _create_workspace(app_session)
    user_id = await _create_principal(app_session, ws_id, principal_type="USER")
    proj_id = await _create_project(app_session, ws_id, identifier="CHK")

    # 1. group_by = sub_group_by raises 23514
    sp1 = await app_session.begin_nested()
    v1_id = await _register_view_object(app_session, ws_id, proj_id, "VIEW-CHK1", "Same Swimlane")
    with pytest.raises(IntegrityError) as exc1:
        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, name, group_by, sub_group_by"
                ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'Same Swimlane', 'state', 'state')"
            ),
            {"id": v1_id, "ws_id": ws_id, "proj_id": proj_id, "owner_id": user_id},
        )
    assert _is_check_violation(exc1.value)
    await sp1.rollback()

    # 2. visibility = 'project' with project_id IS NULL raises 23514
    sp2 = await app_session.begin_nested()
    v2_id = await _register_view_object(
        app_session, ws_id, None, "VIEW-CHK2", "Null Project Visible"
    )
    with pytest.raises(IntegrityError) as exc2:
        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, visibility, name"
                ") VALUES (:id, :ws_id, NULL, :owner_id, 'project', 'Null Project Visible')"
            ),
            {"id": v2_id, "ws_id": ws_id, "owner_id": user_id},
        )
    assert _is_check_violation(exc2.value)
    await sp2.rollback()

    # 3. Unknown filter key raises 23514
    sp3 = await app_session.begin_nested()
    v3_id = await _register_view_object(app_session, ws_id, proj_id, "VIEW-CHK3", "Bad Filter Key")
    with pytest.raises(IntegrityError) as exc3:
        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, name, filters_json"
                ") VALUES ("
                "  :id, :ws_id, :proj_id, :owner_id, 'Bad Filter Key', '{\"raw_sql\": \"1=1\"}'"
                ")"
            ),
            {"id": v3_id, "ws_id": ws_id, "proj_id": proj_id, "owner_id": user_id},
        )
    assert _is_check_violation(exc3.value)
    await sp3.rollback()

    # 4. Array filters_json raises 23514
    sp4 = await app_session.begin_nested()
    v4_id = await _register_view_object(app_session, ws_id, proj_id, "VIEW-CHK4", "Array Filter")
    with pytest.raises(IntegrityError) as exc4:
        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, name, filters_json"
                ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'Array Filter', '[1, 2, 3]')"
            ),
            {"id": v4_id, "ws_id": ws_id, "proj_id": proj_id, "owner_id": user_id},
        )
    assert _is_check_violation(exc4.value)
    await sp4.rollback()


async def test_03_views_wip_limits_checks(app_session: AsyncSession) -> None:
    """Test CHECK constraint rejections on WIP limits JSON."""
    ws_id = await _create_workspace(app_session)
    user_id = await _create_principal(app_session, ws_id, principal_type="USER")
    proj_id = await _create_project(app_session, ws_id, identifier="WIP")

    # 5. WIP limits: hard < soft raises 23514
    st_uuid = str(uuid.uuid4())
    sp5 = await app_session.begin_nested()
    v5_id = await _register_view_object(app_session, ws_id, proj_id, "VIEW-CHK5", "WIP Hard < Soft")
    with pytest.raises(IntegrityError) as exc5:
        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, name, wip_limits_json"
                ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'WIP Hard < Soft', :wip)"
            ),
            {
                "id": v5_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "owner_id": user_id,
                "wip": json.dumps({st_uuid: {"soft": 5, "hard": 3}}),
            },
        )
    assert _is_check_violation(exc5.value)
    await sp5.rollback()

    # 6. WIP limits: soft = 0 raises 23514
    sp6 = await app_session.begin_nested()
    v6_id = await _register_view_object(app_session, ws_id, proj_id, "VIEW-CHK6", "WIP Soft 0")
    with pytest.raises(IntegrityError) as exc6:
        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, name, wip_limits_json"
                ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'WIP Soft 0', :wip)"
            ),
            {
                "id": v6_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "owner_id": user_id,
                "wip": json.dumps({st_uuid: {"soft": 0, "hard": 5}}),
            },
        )
    assert _is_check_violation(exc6.value)
    await sp6.rollback()

    # 7. WIP limits: non-UUID key raises 23514
    sp7 = await app_session.begin_nested()
    v7_id = await _register_view_object(app_session, ws_id, proj_id, "VIEW-CHK7", "WIP Non-UUID")
    with pytest.raises(IntegrityError) as exc7:
        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, name, wip_limits_json"
                ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'WIP Non-UUID', :wip)"
            ),
            {
                "id": v7_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "owner_id": user_id,
                "wip": json.dumps({"not-a-uuid": {"soft": 1, "hard": 2}}),
            },
        )
    assert _is_check_violation(exc7.value)
    await sp7.rollback()

    # 8. WIP limits: extra key 'override' raises 23514
    sp8 = await app_session.begin_nested()
    v8_id = await _register_view_object(app_session, ws_id, proj_id, "VIEW-CHK8", "WIP Extra Key")
    with pytest.raises(IntegrityError) as exc8:
        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, name, wip_limits_json"
                ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'WIP Extra Key', :wip)"
            ),
            {
                "id": v8_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "owner_id": user_id,
                "wip": json.dumps({st_uuid: {"soft": 1, "hard": 2, "override": True}}),
            },
        )
    assert _is_check_violation(exc8.value)
    await sp8.rollback()


async def test_04_views_security_and_spine_mismatches(app_session: AsyncSession) -> None:
    """Test security trigger enforcements on owner principal, spine, and project."""
    ws1 = await _create_workspace(app_session)
    ws2 = await _create_workspace(app_session)
    user_ws1 = await _create_principal(app_session, ws1, principal_type="USER")
    user_ws2 = await _create_principal(app_session, ws2, principal_type="USER")
    group_ws1 = await _create_principal(app_session, ws1, principal_type="GROUP")
    proj_ws1 = await _create_project(app_session, ws1, identifier="SEC1")
    proj_ws2 = await _create_project(app_session, ws2, identifier="SEC2")
    await bind_workspace_admin(app_session, ws1)

    # 1. owner_principal_id pointing to a GROUP raises VIEW_INVALID_OWNER
    sp1 = await app_session.begin_nested()
    v1_id = await _register_view_object(app_session, ws1, proj_ws1, "VIEW-SEC1", "Group Owner View")
    with pytest.raises(DBAPIError) as exc1:
        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, name"
                ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'Group Owner View')"
            ),
            {"id": v1_id, "ws_id": ws1, "proj_id": proj_ws1, "owner_id": group_ws1},
        )
    assert "VIEW_INVALID_OWNER" in str(exc1.value)
    await sp1.rollback()

    # 2. owner_principal_id from another workspace raises VIEW_INVALID_OWNER
    sp2 = await app_session.begin_nested()
    v2_id = await _register_view_object(
        app_session, ws1, proj_ws1, "VIEW-SEC2", "Other WS Owner View"
    )
    with pytest.raises(DBAPIError) as exc2:
        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, name"
                ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'Other WS Owner View')"
            ),
            {"id": v2_id, "ws_id": ws1, "proj_id": proj_ws1, "owner_id": user_ws2},
        )
    assert "VIEW_INVALID_OWNER" in str(exc2.value)
    await sp2.rollback()

    # 3. Mismatching objects.project_id raises VIEW_SPINE_MISMATCH
    # Register view with NULL project_id, but insert views with proj_ws1
    sp3 = await app_session.begin_nested()
    v3_id = await _register_view_object(app_session, ws1, None, "VIEW-SEC3", "Spine Mismatch View")
    with pytest.raises(DBAPIError) as exc3:
        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, name"
                ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'Spine Mismatch View')"
            ),
            {"id": v3_id, "ws_id": ws1, "proj_id": proj_ws1, "owner_id": user_ws1},
        )
    assert "VIEW_SPINE_MISMATCH" in str(exc3.value)
    await sp3.rollback()

    # 4. project from another workspace raises VIEW_PROJECT_WORKSPACE_MISMATCH
    # Register view in ws1 with proj_ws2 (which belongs to ws2) -> raises during views insert
    sp4 = await app_session.begin_nested()
    v4_id = await _register_view_object(
        app_session, ws1, proj_ws2, "VIEW-SEC4", "Cross WS Project View"
    )
    with pytest.raises(DBAPIError) as exc4:
        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, name"
                ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'Cross WS Project View')"
            ),
            {"id": v4_id, "ws_id": ws1, "proj_id": proj_ws2, "owner_id": user_ws1},
        )
    assert "VIEW_PROJECT_WORKSPACE_MISMATCH" in str(exc4.value)
    await sp4.rollback()


async def test_05_views_boundary_conditions(app_session: AsyncSession) -> None:
    """Test boundary conditions on filter size, WIP soft/hard equality, and catalog columns."""
    ws_id = await _create_workspace(app_session)
    user_id = await _create_principal(app_session, ws_id, principal_type="USER")
    proj_id = await _create_project(app_session, ws_id, identifier="BND")

    # 1. filters_json exactly 16384 bytes accepted
    prefix = '{"search_query": "'
    suffix = '"}'
    target_bytes = 16384
    pad_len = target_bytes - len(prefix) - len(suffix)
    filters_exact = prefix + ("x" * pad_len) + suffix
    assert len(filters_exact.encode("utf-8")) == 16384

    v1_id = await _register_view_object(
        app_session, ws_id, proj_id, "VIEW-BND1", "Exact 16K Filter"
    )
    await app_session.execute(
        text(
            "INSERT INTO views ("
            "  id, workspace_id, project_id, owner_principal_id, name, filters_json"
            ") VALUES ("
            "  :id, :ws_id, :proj_id, :owner_id, 'Exact 16K Filter', CAST(:filters AS jsonb)"
            ")"
        ),
        {
            "id": v1_id,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "owner_id": user_id,
            "filters": filters_exact,
        },
    )

    # 2. filters_json 16385 bytes rejected
    filters_oversized = prefix + ("x" * (pad_len + 1)) + suffix
    assert len(filters_oversized.encode("utf-8")) == 16385
    sp2 = await app_session.begin_nested()
    v2_id = await _register_view_object(
        app_session, ws_id, proj_id, "VIEW-BND2", "Oversized 16K Filter"
    )
    with pytest.raises(IntegrityError) as exc2:
        await app_session.execute(
            text(
                "INSERT INTO views ("
                "  id, workspace_id, project_id, owner_principal_id, name, filters_json"
                ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'Oversized', CAST(:filters AS jsonb))"
            ),
            {
                "id": v2_id,
                "ws_id": ws_id,
                "proj_id": proj_id,
                "owner_id": user_id,
                "filters": filters_oversized,
            },
        )
    assert _is_check_violation(exc2.value)
    await sp2.rollback()

    # 3. WIP limits: soft = hard (equal) accepted
    st_uuid1 = str(uuid.uuid4())
    v3_id = await _register_view_object(app_session, ws_id, proj_id, "VIEW-BND3", "Equal Soft Hard")
    await app_session.execute(
        text(
            "INSERT INTO views ("
            "  id, workspace_id, project_id, owner_principal_id, name, wip_limits_json"
            ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'Equal Soft Hard', :wip)"
        ),
        {
            "id": v3_id,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "owner_id": user_id,
            "wip": json.dumps({st_uuid1: {"soft": 5, "hard": 5}}),
        },
    )

    # 4. WIP limits: {"soft": 5, "hard": null} accepted
    st_uuid2 = str(uuid.uuid4())
    v4_id = await _register_view_object(app_session, ws_id, proj_id, "VIEW-BND4", "Null Hard WIP")
    await app_session.execute(
        text(
            "INSERT INTO views ("
            "  id, workspace_id, project_id, owner_principal_id, name, wip_limits_json"
            ") VALUES (:id, :ws_id, :proj_id, :owner_id, 'Null Hard WIP', :wip)"
        ),
        {
            "id": v4_id,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "owner_id": user_id,
            "wip": json.dumps({st_uuid2: {"soft": 5, "hard": None}}),
        },
    )

    # 5. Schema verification: views has no prohibited body/description/content columns
    cols_res = await app_session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'views' "
            "  AND column_name IN ('body', 'description', 'content')"
        )
    )
    assert len(cols_res.fetchall()) == 0
