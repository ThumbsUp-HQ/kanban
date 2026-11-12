"""Unit tests for Phase 1 workspaces, objects spine, and register_object."""

import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, DBAPIError, IntegrityError, ProgrammingError
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


async def test_01_register_object_positive(db_session: AsyncSession) -> None:
    """Verify register_object creates an object with object_type and RFC 9562 v7 UUID."""
    ws_id = await _create_workspace(db_session)
    user_id = uuid.uuid4()
    proj_id = uuid.uuid4()

    res = await db_session.execute(
        text(
            "SELECT register_object("
            "  'issue'::object_kind, :ws_id, :proj_id, 'KAN-1', 'Sample Issue', :user_id"
            ")"
        ),
        {"ws_id": ws_id, "proj_id": proj_id, "user_id": user_id},
    )
    obj_id = res.scalar_one()
    assert isinstance(obj_id, uuid.UUID)

    # Verify RFC 9562 version 7 nibble and variant 10xx
    raw = obj_id.bytes
    version_nibble = (raw[6] >> 4) & 0x0F
    variant_bits = (raw[8] >> 6) & 0x03
    assert version_nibble == 7
    assert variant_bits == 2

    # Query row
    row = await db_session.execute(
        text(
            "SELECT object_type, workspace_id, project_id, canonical_key, "
            "display_title, created_by_id FROM objects WHERE id = :id"
        ),
        {"id": obj_id},
    )
    record = row.mappings().one()
    assert record["object_type"] == "issue"
    assert record["workspace_id"] == ws_id
    assert record["project_id"] == proj_id
    assert record["canonical_key"] == "KAN-1"
    assert record["display_title"] == "Sample Issue"
    assert record["created_by_id"] == user_id


async def test_02_canonical_key_independence(db_session: AsyncSession) -> None:
    """Verify same canonical_key allowed across different object_types and workspaces."""
    ws1 = await _create_workspace(db_session, slug="ws-one")
    ws2 = await _create_workspace(db_session, slug="ws-two")
    user_id = uuid.uuid4()
    proj_id = uuid.uuid4()

    # 1. Same canonical_key for two different object_types in ws1
    id_issue = await db_session.scalar(
        text("SELECT register_object('issue'::object_kind, :ws, :proj, 'SHARED-1', 'Issue 1', :u)"),
        {"ws": ws1, "proj": proj_id, "u": user_id},
    )
    id_doc = await db_session.scalar(
        text("SELECT register_object('doc'::object_kind, :ws, :proj, 'SHARED-1', 'Doc 1', :u)"),
        {"ws": ws1, "proj": proj_id, "u": user_id},
    )
    assert id_issue is not None
    assert id_doc is not None
    assert id_issue != id_doc

    # 2. Same canonical_key for same object_type in ws2
    id_ws2_issue = await db_session.scalar(
        text(
            "SELECT register_object('issue'::object_kind, :ws, :proj, 'SHARED-1', 'Issue WS2', :u)"
        ),
        {"ws": ws2, "proj": proj_id, "u": user_id},
    )
    assert id_ws2_issue is not None
    assert id_ws2_issue != id_issue


async def test_03_canonical_key_collision_raises_23505(db_session: AsyncSession) -> None:
    """Verify duplicate (workspace_id, object_type, canonical_key) raises 23505."""
    ws = await _create_workspace(db_session)
    user_id = uuid.uuid4()

    await db_session.execute(
        text("SELECT register_object('issue'::object_kind, :ws, NULL, 'DUP-1', 'Initial', :u)"),
        {"ws": ws, "u": user_id},
    )

    with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "SELECT register_object("
                    "'issue'::object_kind, :ws, NULL, 'DUP-1', 'Duplicate', :u)"
                ),
                {"ws": ws, "u": user_id},
            )
    orig = getattr(exc_info.value, "orig", None)
    pgcode = getattr(orig, "sqlstate", None) or getattr(exc_info.value, "code", None)
    assert pgcode == "23505" or "unique constraint" in str(exc_info.value).lower()


async def test_04_invalid_enum_raises_22p02(db_session: AsyncSession) -> None:
    """Verify invalid object_kind enum literal raises 22P02."""
    ws = await _create_workspace(db_session)
    user_id = uuid.uuid4()

    with pytest.raises((DataError, DBAPIError)) as exc_info:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO objects (object_type, workspace_id, "
                    "canonical_key, display_title, created_by_id) "
                    "VALUES ('epic'::object_kind, :ws, 'EPIC-1', 'Invalid Enum', :u)"
                ),
                {"ws": ws, "u": user_id},
            )
    orig = getattr(exc_info.value, "orig", None)
    pgcode = getattr(orig, "sqlstate", None) or getattr(exc_info.value, "code", None)
    assert pgcode == "22P02" or "invalid input value for enum" in str(exc_info.value).lower()


async def test_05_immutability_and_registration_guards(db_session: AsyncSession) -> None:
    """Verify objects_guard_bu trigger and register_object argument validations."""
    ws = await _create_workspace(db_session)
    user_id = uuid.uuid4()
    proj_id = uuid.uuid4()

    obj_id = await db_session.scalar(
        text("SELECT register_object('issue'::object_kind, :ws, :proj, 'IMM-1', 'Original', :u)"),
        {"ws": ws, "proj": proj_id, "u": user_id},
    )
    assert obj_id is not None

    # Guard 1: object_type cannot be modified
    with pytest.raises((ProgrammingError, DBAPIError)) as exc_type:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE objects SET object_type = 'doc'::object_kind WHERE id = :id"),
                {"id": obj_id},
            )
    assert "OBJECT_TYPE_IMMUTABLE" in str(exc_type.value)

    # Guard 2: id cannot be modified
    with pytest.raises((ProgrammingError, DBAPIError)) as exc_id:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE objects SET id = :new_id WHERE id = :id"),
                {"new_id": uuid.uuid4(), "id": obj_id},
            )
    assert "OBJECT_ID_IMMUTABLE" in str(exc_id.value)

    # Guard 3: project/user object_type cannot have non-null project_id
    with pytest.raises((ProgrammingError, DBAPIError)) as exc_proj:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "SELECT register_object("
                    "'project'::object_kind, :ws, :proj, 'PRJ-1', 'Project', :u)"
                ),
                {"ws": ws, "proj": proj_id, "u": user_id},
            )
    assert "REGISTER_OBJECT_PROJECT_NOT_ALLOWED" in str(exc_proj.value)

    # Guard 4: NULL display_title raises REGISTER_OBJECT_NULL_ARGUMENT
    with pytest.raises((ProgrammingError, DBAPIError)) as exc_null:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "SELECT register_object('issue'::object_kind, :ws, :proj, 'NULL-1', NULL, :u)"
                ),
                {"ws": ws, "proj": proj_id, "u": user_id},
            )
    assert "REGISTER_OBJECT_NULL_ARGUMENT" in str(exc_null.value)


async def test_06_boundary_lengths_and_slug_pattern(db_session: AsyncSession) -> None:
    """Verify CHECK constraints on canonical_key (200), display_title (500), and slug regex."""
    ws = await _create_workspace(db_session)
    user_id = uuid.uuid4()

    # canonical_key: 200 chars accepted, 201 rejected
    key_200 = "k" * 200
    obj_200 = await db_session.scalar(
        text("SELECT register_object('issue'::object_kind, :ws, NULL, :k, 'Title', :u)"),
        {"ws": ws, "k": key_200, "u": user_id},
    )
    assert obj_200 is not None

    key_201 = "k" * 201
    with pytest.raises((IntegrityError, DBAPIError)) as exc_key:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT register_object('issue'::object_kind, :ws, NULL, :k, 'Title', :u)"),
                {"ws": ws, "k": key_201, "u": user_id},
            )
    orig_key = getattr(exc_key.value, "orig", None)
    pgcode_key = getattr(orig_key, "sqlstate", None) or getattr(exc_key.value, "code", None)
    assert pgcode_key == "23514" or "check constraint" in str(exc_key.value).lower()

    # display_title: 500 chars accepted, 501 rejected
    title_500 = "t" * 500
    obj_500 = await db_session.scalar(
        text("SELECT register_object('issue'::object_kind, :ws, NULL, 'KEY-500', :t, :u)"),
        {"ws": ws, "t": title_500, "u": user_id},
    )
    assert obj_500 is not None

    title_501 = "t" * 501
    with pytest.raises((IntegrityError, DBAPIError)) as exc_title:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT register_object('issue'::object_kind, :ws, NULL, 'KEY-501', :t, :u)"),
                {"ws": ws, "t": title_501, "u": user_id},
            )
    orig_title = getattr(exc_title.value, "orig", None)
    pgcode_title = getattr(orig_title, "sqlstate", None) or getattr(exc_title.value, "code", None)
    assert pgcode_title == "23514" or "check constraint" in str(exc_title.value).lower()

    # workspace slug: 1 char rejected (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$')
    with pytest.raises((IntegrityError, DBAPIError)) as exc_slug_short:
        async with db_session.begin_nested():
            await _create_workspace(db_session, slug="a")
    orig_short = getattr(exc_slug_short.value, "orig", None)
    code_short = getattr(orig_short, "sqlstate", None) or getattr(
        exc_slug_short.value, "code", None
    )
    assert code_short == "23514" or "check constraint" in str(exc_slug_short.value).lower()

    # 63 chars accepted
    slug_63 = "a" + ("b" * 62)
    ws_63 = await _create_workspace(db_session, slug=slug_63)
    assert ws_63 is not None

    # 64 chars rejected
    slug_64 = "a" + ("b" * 63)
    with pytest.raises((IntegrityError, DBAPIError)) as exc_slug_long:
        async with db_session.begin_nested():
            await _create_workspace(db_session, slug=slug_64)
    orig_long = getattr(exc_slug_long.value, "orig", None)
    code_long = getattr(orig_long, "sqlstate", None) or getattr(exc_slug_long.value, "code", None)
    assert code_long == "23514" or "check constraint" in str(exc_slug_long.value).lower()


async def test_07_updated_at_trigger_and_fk_constraint(db_session: AsyncSession) -> None:
    """Verify updated_at triggers fire and non-existent workspace FK raises 23503."""
    ws = await _create_workspace(db_session, name="Original Workspace")
    user_id = uuid.uuid4()

    # Part A: Workspace updated_at > created_at
    await asyncio.sleep(0.005)
    await db_session.execute(
        text("UPDATE workspaces SET name = 'Updated Workspace' WHERE id = :id"),
        {"id": ws},
    )
    ws_times = (
        await db_session.execute(
            text("SELECT created_at, updated_at FROM workspaces WHERE id = :id"),
            {"id": ws},
        )
    ).one()
    assert ws_times[1] > ws_times[0]

    # Part B: Object updated_at > created_at
    obj_id = await db_session.scalar(
        text("SELECT register_object('issue'::object_kind, :ws, NULL, 'TRG-1', 'Initial', :u)"),
        {"ws": ws, "u": user_id},
    )
    assert obj_id is not None

    await asyncio.sleep(0.005)
    await db_session.execute(
        text("UPDATE objects SET display_title = 'Updated Title' WHERE id = :id"),
        {"id": obj_id},
    )
    obj_times = (
        await db_session.execute(
            text("SELECT created_at, updated_at FROM objects WHERE id = :id"),
            {"id": obj_id},
        )
    ).one()
    assert obj_times[1] > obj_times[0]

    # Part C: Non-existent workspace FK raises 23503
    non_existent_ws = uuid.uuid4()
    with pytest.raises((IntegrityError, DBAPIError)) as exc_fk:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO objects (workspace_id, object_type, "
                    "canonical_key, display_title, created_by_id) "
                    "VALUES (:ws, 'issue'::object_kind, 'NO-WS', 'Title', :u)"
                ),
                {"ws": non_existent_ws, "u": user_id},
            )
    orig_fk = getattr(exc_fk.value, "orig", None)
    pgcode_fk = getattr(orig_fk, "sqlstate", None) or getattr(exc_fk.value, "code", None)
    assert pgcode_fk == "23503" or "foreign key constraint" in str(exc_fk.value).lower()
