"""Unit tests for Phase 1 object_links, link_kind enum, and link_type_matrix allowlist."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from database.tests.conftest import bind_workspace_admin, bootstrap_workspace_admin

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

EXPECTED_LINK_KIND_LABELS: list[str] = [
    "BLOCKS",
    "BLOCKED_BY",
    "RELATES_TO",
    "DUPLICATES",
    "PARENT_OF",
    "ASSIGNED_TO",
    "IN_CYCLE",
    "IN_MODULE",
    "PROMOTED_TO_DOC",
    "VERIFIED_BY_DOC",
    "DERIVED_FROM_STICKY",
    "EMBEDS_OBJECT",
    "GOVERNED_BY_VIEW",
    "IMPLEMENTED_IN_PR",
    "REFERENCED_BY_COMMIT",
    "TRACKED_ON_BRANCH",
]

EXPECTED_USER_LINK_KINDS: set[str] = {
    "BLOCKS",
    "BLOCKED_BY",
    "DUPLICATES",
    "RELATES_TO",
    "VERIFIED_BY_DOC",
    "DERIVED_FROM_STICKY",
}

EXPECTED_SYSTEM_LINK_KINDS: set[str] = {
    "PROMOTED_TO_DOC",
    "PARENT_OF",
    "ASSIGNED_TO",
    "IN_CYCLE",
    "IN_MODULE",
    "EMBEDS_OBJECT",
    "GOVERNED_BY_VIEW",
    "IMPLEMENTED_IN_PR",
    "REFERENCED_BY_COMMIT",
    "TRACKED_ON_BRANCH",
}


async def _create_workspace(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Test Workspace",
) -> uuid.UUID:
    """Create a test workspace."""
    ws_id, _ = await bootstrap_workspace_admin(session, slug=slug, name=name)
    return ws_id


async def _register_obj(
    session: AsyncSession,
    ws_id: uuid.UUID,
    obj_type: str,
    canonical_key: str,
    *,
    title: str = "Sample Title",
) -> uuid.UUID:
    """Register an object in the objects spine."""
    admin_id = await bind_workspace_admin(session, ws_id)
    user_id = admin_id
    row = await session.execute(
        text(
            "SELECT register_object("
            "  CAST(:obj_type AS object_kind), :ws_id, NULL, :canonical_key, :title, :user_id"
            ")"
        ),
        {
            "obj_type": obj_type,
            "ws_id": ws_id,
            "canonical_key": canonical_key,
            "title": title,
            "user_id": user_id,
        },
    )
    val = row.scalar_one()
    assert isinstance(val, uuid.UUID)
    return val


async def test_01_link_objects_positive_snapshots_and_active_state(
    db_session: AsyncSession,
) -> None:
    """Test Case 1: Linking issue->BLOCKS->issue and sticky->PROMOTED_TO_DOC->doc succeeds."""
    ws_id = await _create_workspace(db_session)
    user_id = uuid.uuid4()

    issue1_id = await _register_obj(db_session, ws_id, "issue", "KAN-1", title="First Issue")
    issue2_id = await _register_obj(db_session, ws_id, "issue", "KAN-2", title="Second Issue")
    sticky_id = await _register_obj(db_session, ws_id, "sticky", "STK-1", title="Quick Sticky")
    doc_id = await _register_obj(db_session, ws_id, "doc", "DOC-1", title="Architecture Doc")

    # Link issue1 -> BLOCKS -> issue2 (pass dummy snapshots to verify trigger overwrites them)
    res1 = await db_session.execute(
        text(
            "INSERT INTO object_links ("
            "  workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, source_key_snapshot, target_key_snapshot, created_by_id, link_state"
            ") VALUES ("
            "  :ws_id, :src_id, 'issue', :tgt_id, 'issue', "
            "  'BLOCKS', 'DUMMY_SRC', 'DUMMY_TGT', :user_id, 'FLAGGED_INVALID'"
            ") RETURNING id, source_key_snapshot, target_key_snapshot, link_state"
        ),
        {
            "ws_id": ws_id,
            "src_id": issue1_id,
            "tgt_id": issue2_id,
            "user_id": user_id,
        },
    )
    link1 = res1.mappings().one()
    assert isinstance(link1["id"], uuid.UUID)
    assert link1["source_key_snapshot"] == "KAN-1"
    assert link1["target_key_snapshot"] == "KAN-2"
    assert link1["link_state"] == "ACTIVE"

    # Link sticky -> PROMOTED_TO_DOC -> doc
    res2 = await db_session.execute(
        text(
            "INSERT INTO object_links ("
            "  workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
            ") VALUES ("
            "  :ws_id, :src_id, 'sticky', :tgt_id, 'doc', "
            "  'PROMOTED_TO_DOC', 'IGNORE', 'IGNORE', :user_id"
            ") RETURNING id, source_key_snapshot, target_key_snapshot, link_state"
        ),
        {
            "ws_id": ws_id,
            "src_id": sticky_id,
            "tgt_id": doc_id,
            "user_id": user_id,
        },
    )
    link2 = res2.mappings().one()
    assert isinstance(link2["id"], uuid.UUID)
    assert link2["source_key_snapshot"] == "STK-1"
    assert link2["target_key_snapshot"] == "DOC-1"
    assert link2["link_state"] == "ACTIVE"


async def test_02_update_link_state_preserves_snapshots(db_session: AsyncSession) -> None:
    """Test Case 2: Updating link_state to FLAGGED_INVALID succeeds and preserves snapshots."""
    ws_id = await _create_workspace(db_session)
    user_id = uuid.uuid4()

    issue1_id = await _register_obj(db_session, ws_id, "issue", "KAN-10", title="Issue 10")
    issue2_id = await _register_obj(db_session, ws_id, "issue", "KAN-11", title="Issue 11")

    res = await db_session.execute(
        text(
            "INSERT INTO object_links ("
            "  workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
            ") VALUES ("
            "  :ws_id, :src_id, 'issue', :tgt_id, 'issue', "
            "  'BLOCKS', 'SNAP_1', 'SNAP_2', :user_id"
            ") RETURNING id"
        ),
        {"ws_id": ws_id, "src_id": issue1_id, "tgt_id": issue2_id, "user_id": user_id},
    )
    link_id = res.scalar_one()

    # Mutate objects display_title
    await db_session.execute(
        text("UPDATE objects SET display_title = 'Renamed Issue 10' WHERE id = :id"),
        {"id": issue1_id},
    )

    # Update link_state to FLAGGED_INVALID
    await db_session.execute(
        text("UPDATE object_links SET link_state = 'FLAGGED_INVALID' WHERE id = :id"),
        {"id": link_id},
    )

    row = await db_session.execute(
        text(
            "SELECT link_state, source_key_snapshot, target_key_snapshot "
            "FROM object_links WHERE id = :id"
        ),
        {"id": link_id},
    )
    record = row.mappings().one()
    assert record["link_state"] == "FLAGGED_INVALID"
    assert record["source_key_snapshot"] == "KAN-10"
    assert record["target_key_snapshot"] == "KAN-11"


async def test_03_negative_matrix_and_self_link_guards(db_session: AsyncSession) -> None:
    """Test Case 3: Matrix violation, self-link, and duplicate link rejections."""
    ws_id = await _create_workspace(db_session)
    user_id = uuid.uuid4()

    user_obj_id = await _register_obj(db_session, ws_id, "user", "USR-1", title="Alice")
    doc_id = await _register_obj(db_session, ws_id, "doc", "DOC-2", title="Guide")
    proj_id = await _register_obj(db_session, ws_id, "project", "PRJ-1", title="Platform")
    issue_id = await _register_obj(db_session, ws_id, "issue", "KAN-20", title="Issue 20")
    issue2_id = await _register_obj(db_session, ws_id, "issue", "KAN-21", title="Issue 21")

    # 1. user -> IN_CYCLE -> doc (disallowed pair)
    with pytest.raises(DBAPIError) as exc_matrix:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO object_links ("
                    "  workspace_id, source_id, source_type, target_id, target_type, "
                    "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
                    ") VALUES ("
                    "  :ws_id, :src_id, 'user', :tgt_id, 'doc', "
                    "  'IN_CYCLE', 'X', 'Y', :user_id"
                    ")"
                ),
                {"ws_id": ws_id, "src_id": user_obj_id, "tgt_id": doc_id, "user_id": user_id},
            )
    assert "LINK_TYPE_NOT_ALLOWED" in str(exc_matrix.value)

    # 2. project -> BLOCKS -> issue (disallowed pair)
    with pytest.raises(DBAPIError) as exc_matrix2:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO object_links ("
                    "  workspace_id, source_id, source_type, target_id, target_type, "
                    "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
                    ") VALUES ("
                    "  :ws_id, :src_id, 'project', :tgt_id, 'issue', "
                    "  'BLOCKS', 'X', 'Y', :user_id"
                    ")"
                ),
                {"ws_id": ws_id, "src_id": proj_id, "tgt_id": issue_id, "user_id": user_id},
            )
    assert "LINK_TYPE_NOT_ALLOWED" in str(exc_matrix2.value)

    # 3. self-link source_id = target_id raises 23514
    with pytest.raises(IntegrityError) as exc_self:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO object_links ("
                    "  workspace_id, source_id, source_type, target_id, target_type, "
                    "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
                    ") VALUES ("
                    "  :ws_id, :src_id, 'issue', :src_id, 'issue', "
                    "  'BLOCKS', 'X', 'Y', :user_id"
                    ")"
                ),
                {"ws_id": ws_id, "src_id": issue_id, "user_id": user_id},
            )
    orig = getattr(exc_self.value, "orig", None)
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    assert pgcode == "23514"

    # 4. duplicate link (source_id, target_id, link_type) raises 23505
    await db_session.execute(
        text(
            "INSERT INTO object_links ("
            "  workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
            ") VALUES ("
            "  :ws_id, :src_id, 'issue', :tgt_id, 'issue', "
            "  'DUPLICATES', 'X', 'Y', :user_id"
            ")"
        ),
        {"ws_id": ws_id, "src_id": issue_id, "tgt_id": issue2_id, "user_id": user_id},
    )

    with pytest.raises(IntegrityError) as exc_dup:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO object_links ("
                    "  workspace_id, source_id, source_type, target_id, target_type, "
                    "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
                    ") VALUES ("
                    "  :ws_id, :src_id, 'issue', :tgt_id, 'issue', "
                    "  'DUPLICATES', 'X', 'Y', :user_id"
                    ")"
                ),
                {"ws_id": ws_id, "src_id": issue_id, "tgt_id": issue2_id, "user_id": user_id},
            )
    orig_dup = getattr(exc_dup.value, "orig", None)
    pgcode_dup = getattr(orig_dup, "pgcode", None) or getattr(orig_dup, "sqlstate", None)
    assert pgcode_dup == "23505"


async def test_04_negative_cross_workspace_and_foreign_key_guards(
    db_session: AsyncSession,
    app_session: AsyncSession,
) -> None:
    """Test Case 4: Cross-workspace link, composite FK, RESTRICT delete, and permissions."""
    await db_session.execute(text("RESET SESSION AUTHORIZATION"))
    ws1_id = await _create_workspace(db_session, name="Workspace 1")
    ws2_id = await _create_workspace(db_session, name="Workspace 2")
    user_id = uuid.uuid4()

    issue_ws1_id = await _register_obj(db_session, ws1_id, "issue", "W1-1")
    issue_ws2_id = await _register_obj(db_session, ws2_id, "issue", "W2-1")
    await db_session.execute(text("RESET SESSION AUTHORIZATION"))

    # 1. Cross-workspace link raises LINK_CROSS_WORKSPACE_FORBIDDEN
    with pytest.raises(DBAPIError) as exc_cross:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO object_links ("
                    "  workspace_id, source_id, source_type, target_id, target_type, "
                    "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
                    ") VALUES ("
                    "  :ws_id, :src_id, 'issue', :tgt_id, 'issue', "
                    "  'BLOCKS', 'X', 'Y', :user_id"
                    ")"
                ),
                {
                    "ws_id": ws1_id,
                    "src_id": issue_ws1_id,
                    "tgt_id": issue_ws2_id,
                    "user_id": user_id,
                },
            )
    assert "LINK_CROSS_WORKSPACE_FORBIDDEN" in str(exc_cross.value)

    # 2. Endpoint missing entirely raises LINK_ENDPOINT_NOT_FOUND
    missing_id = uuid.uuid4()
    with pytest.raises(DBAPIError) as exc_missing:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO object_links ("
                    "  workspace_id, source_id, source_type, target_id, target_type, "
                    "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
                    ") VALUES ("
                    "  :ws_id, :src_id, 'issue', :tgt_id, 'issue', "
                    "  'BLOCKS', 'X', 'Y', :user_id"
                    ")"
                ),
                {"ws_id": ws1_id, "src_id": issue_ws1_id, "tgt_id": missing_id, "user_id": user_id},
            )
    assert "LINK_ENDPOINT_NOT_FOUND" in str(exc_missing.value)

    # 3. Composite FK mismatch: source_id is issue, but source_type passed as 'doc'
    doc_ws1_id = await _register_obj(db_session, ws1_id, "doc", "DOC-W1")
    with pytest.raises((IntegrityError, DBAPIError)) as exc_fk:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO object_links ("
                    "  workspace_id, source_id, source_type, target_id, target_type, "
                    "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
                    ") VALUES ("
                    "  :ws_id, :src_id, 'doc', :tgt_id, 'doc', "
                    "  'RELATES_TO', 'X', 'Y', :user_id"
                    ")"
                ),
                {"ws_id": ws1_id, "src_id": issue_ws1_id, "tgt_id": doc_ws1_id, "user_id": user_id},
            )
    orig_fk = getattr(exc_fk.value, "orig", None)
    pgcode_fk = getattr(orig_fk, "pgcode", None) or getattr(orig_fk, "sqlstate", None)
    assert pgcode_fk == "23503"

    # 4. ON DELETE RESTRICT on objects when linked
    issue_a_id = await _register_obj(db_session, ws1_id, "issue", "KAN-A")
    issue_b_id = await _register_obj(db_session, ws1_id, "issue", "KAN-B")
    await db_session.execute(
        text(
            "INSERT INTO object_links ("
            "  workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
            ") VALUES ("
            "  :ws_id, :src_id, 'issue', :tgt_id, 'issue', "
            "  'BLOCKS', 'X', 'Y', :user_id"
            ")"
        ),
        {"ws_id": ws1_id, "src_id": issue_a_id, "tgt_id": issue_b_id, "user_id": user_id},
    )

    with pytest.raises(IntegrityError) as exc_del:
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM objects WHERE id = :id"),
                {"id": issue_a_id},
            )
    orig_del = getattr(exc_del.value, "orig", None)
    pgcode_del = getattr(orig_del, "pgcode", None) or getattr(orig_del, "sqlstate", None)
    assert pgcode_del == "23503"

    # 5. As kanban_app, INSERT INTO link_type_matrix raises 42501
    await app_session.execute(text("SET LOCAL SESSION AUTHORIZATION kanban_app"))
    with pytest.raises((ProgrammingError, DBAPIError)) as exc_perm:
        async with app_session.begin_nested():
            await app_session.execute(
                text(
                    "INSERT INTO link_type_matrix ("
                    "  source_type, link_type, target_type, is_user_creatable"
                    ") VALUES ('issue', 'BLOCKS', 'doc', true)"
                )
            )
    orig_perm = getattr(exc_perm.value, "orig", None)
    pgcode_perm = getattr(orig_perm, "pgcode", None) or getattr(orig_perm, "sqlstate", None)
    assert pgcode_perm == "42501"


async def test_05_negative_immutability_and_invalid_state(db_session: AsyncSession) -> None:
    """Test Case 5: Immutability of object_links attributes and check constraint on link_state."""
    ws_id = await _create_workspace(db_session)
    user_id = uuid.uuid4()

    issue1_id = await _register_obj(db_session, ws_id, "issue", "KAN-50")
    issue2_id = await _register_obj(db_session, ws_id, "issue", "KAN-51")
    issue3_id = await _register_obj(db_session, ws_id, "issue", "KAN-52")

    res = await db_session.execute(
        text(
            "INSERT INTO object_links ("
            "  workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, source_key_snapshot, target_key_snapshot, created_by_id"
            ") VALUES ("
            "  :ws_id, :src_id, 'issue', :tgt_id, 'issue', "
            "  'BLOCKS', 'X', 'Y', :user_id"
            ") RETURNING id"
        ),
        {"ws_id": ws_id, "src_id": issue1_id, "tgt_id": issue2_id, "user_id": user_id},
    )
    link_id = res.scalar_one()

    # 1. Mutate target_id raises OBJECT_LINK_IMMUTABLE
    with pytest.raises(DBAPIError) as exc_mut_target:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE object_links SET target_id = :new_tgt WHERE id = :id"),
                {"id": link_id, "new_tgt": issue3_id},
            )
    assert "OBJECT_LINK_IMMUTABLE" in str(exc_mut_target.value)

    # 2. Mutate target_key_snapshot raises OBJECT_LINK_IMMUTABLE
    with pytest.raises(DBAPIError) as exc_mut_snap:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE object_links SET target_key_snapshot = 'FAKE' WHERE id = :id"),
                {"id": link_id},
            )
    assert "OBJECT_LINK_IMMUTABLE" in str(exc_mut_snap.value)

    # 3. Mutate source_key_snapshot raises OBJECT_LINK_IMMUTABLE
    with pytest.raises(DBAPIError) as exc_mut_src_snap:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE object_links SET source_key_snapshot = 'FAKE' WHERE id = :id"),
                {"id": link_id},
            )
    assert "OBJECT_LINK_IMMUTABLE" in str(exc_mut_src_snap.value)

    # 4. Mutate link_type raises OBJECT_LINK_IMMUTABLE
    with pytest.raises(DBAPIError) as exc_mut_type:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE object_links SET link_type = 'DUPLICATES' WHERE id = :id"),
                {"id": link_id},
            )
    assert "OBJECT_LINK_IMMUTABLE" in str(exc_mut_type.value)

    # 5. Invalid link_state = 'DELETED' raises 23514
    with pytest.raises(IntegrityError) as exc_state:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE object_links SET link_state = 'DELETED' WHERE id = :id"),
                {"id": link_id},
            )
    orig_state = getattr(exc_state.value, "orig", None)
    pgcode_state = getattr(orig_state, "pgcode", None) or getattr(orig_state, "sqlstate", None)
    assert pgcode_state == "23514"


async def test_06_boundary_enum_order_and_link_type_matrix(db_session: AsyncSession) -> None:
    """Test Case 6: pg_enum link_kind order and link_type_matrix user/system partition."""
    # 1. Assert pg_enum for link_kind has exactly 13 values in authoritative order
    rows = await db_session.execute(
        text(
            "SELECT e.enumlabel "
            "FROM pg_enum e "
            "JOIN pg_type t ON e.enumtypid = t.oid "
            "WHERE t.typname = 'link_kind' "
            "ORDER BY e.enumsortorder"
        )
    )
    labels = [r[0] for r in rows.all()]
    assert labels == EXPECTED_LINK_KIND_LABELS

    # 2. Check link_type_matrix partition
    matrix_rows = await db_session.execute(
        text("SELECT DISTINCT link_type, is_user_creatable FROM link_type_matrix")
    )
    user_kinds: set[str] = set()
    system_kinds: set[str] = set()

    for link_type, is_user in matrix_rows.all():
        if is_user:
            user_kinds.add(link_type)
        else:
            system_kinds.add(link_type)

    # Exactly the 6 S7.2 8m user kinds are is_user_creatable = TRUE
    assert user_kinds == EXPECTED_USER_LINK_KINDS
    # All 7 system kinds are is_user_creatable = FALSE
    assert system_kinds == EXPECTED_SYSTEM_LINK_KINDS
    # Zero intersection between user and system sets
    assert user_kinds.isdisjoint(system_kinds)
    # Union covers all 13 enum kinds
    assert (user_kinds | system_kinds) == set(EXPECTED_LINK_KIND_LABELS)

    # Total row count in link_type_matrix: 57 user-creatable + 45 system = 102 rows
    total_count = await db_session.execute(text("SELECT count(*) FROM link_type_matrix"))
    assert total_count.scalar_one() == 102
