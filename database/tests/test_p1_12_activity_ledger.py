"""Unit tests for Phase 1 activity_records hash chain and verification."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _create_workspace(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Activity Test Workspace",
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


async def _create_principal(
    session: AsyncSession,
    ws_id: uuid.UUID,
    name: str = "Test Actor",
) -> uuid.UUID:
    """Create a principal record for actor foreign key tests."""
    p_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'USER', :ws_id, :name)"
        ),
        {"id": p_id, "ws_id": ws_id, "name": name},
    )
    return p_id


async def _register_obj(
    session: AsyncSession,
    ws_id: uuid.UUID,
    obj_type: str,
    canonical_key: str,
    title: str = "Sample Title",
) -> uuid.UUID:
    """Register an object in the objects spine."""
    user_id = uuid.uuid4()
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


async def test_01_activity_hash_chain_and_verifier_positive(db_session: AsyncSession) -> None:
    """Test Case 1: Appending 5 events forms a valid SHA-256 chain under all time zones."""
    ws_id = await _create_workspace(db_session)
    user_id = await _create_principal(db_session, ws_id, "Test User")
    issue_id = await _register_obj(db_session, ws_id, "issue", "ACT-1", "First Issue")
    doc_id = await _register_obj(db_session, ws_id, "doc", "DOC-1", "System Architecture")

    # 1. Append 5 events: mixed object-bound and workspace/auth level
    ev1 = await db_session.execute(
        text(
            "SELECT append_activity("
            "  :ws_id, :obj_id, 'issue', :actor_id, 'ISSUE_CREATED', :payload"
            ")"
        ),
        {
            "ws_id": ws_id,
            "obj_id": issue_id,
            "actor_id": user_id,
            "payload": json.dumps({"action": "create", "key": "ACT-1"}),
        },
    )
    id1 = ev1.scalar_one()

    ev2 = await db_session.execute(
        text(
            "SELECT append_activity(  :ws_id, :obj_id, 'doc', :actor_id, 'DOC_CREATED', :payload)"
        ),
        {
            "ws_id": ws_id,
            "obj_id": doc_id,
            "actor_id": user_id,
            "payload": json.dumps({"title": "System Architecture"}),
        },
    )
    id2 = ev2.scalar_one()

    ev3 = await db_session.execute(
        text(
            "SELECT append_activity("
            "  :ws_id, NULL, NULL, NULL, 'LOCAL_ADMIN_LOGIN_FAILED', :payload"
            ")"
        ),
        {
            "ws_id": ws_id,
            "payload": json.dumps({"ip": "127.0.0.1", "reason": "bad_password"}),
        },
    )
    id3 = ev3.scalar_one()

    ev4 = await db_session.execute(
        text("SELECT append_activity(  :ws_id, NULL, NULL, :actor_id, 'USER_LOGGED_IN', :payload)"),
        {
            "ws_id": ws_id,
            "actor_id": user_id,
            "payload": json.dumps({"auth_provider": "local_admin"}),
        },
    )
    id4 = ev4.scalar_one()

    ev5 = await db_session.execute(
        text(
            "SELECT append_activity("
            "  :ws_id, :obj_id, 'issue', :actor_id, 'CREATOR_OVERRIDDEN', :payload"
            ")"
        ),
        {
            "ws_id": ws_id,
            "obj_id": issue_id,
            "actor_id": user_id,
            "payload": json.dumps({"old_creator": str(uuid.uuid4())}),
        },
    )
    id5 = ev5.scalar_one()

    assert all(isinstance(i, uuid.UUID) for i in (id1, id2, id3, id4, id5))

    # 2. Query all 5 rows and assert chain structure
    rows = await db_session.execute(
        text(
            "SELECT chain_seq, prev_hash, row_hash FROM activity_records "
            "WHERE workspace_id = :ws_id ORDER BY chain_seq ASC"
        ),
        {"ws_id": ws_id},
    )
    records = rows.mappings().all()
    assert len(records) == 5

    # Sequence 1..5
    for idx, r in enumerate(records, start=1):
        assert r["chain_seq"] == idx

    # Row 1 prev_hash is 32 zero bytes
    assert records[0]["prev_hash"] == bytes(32)

    # Row k prev_hash == row k-1 row_hash
    for k in range(1, 5):
        assert records[k]["prev_hash"] == records[k - 1]["row_hash"]

    # 3. Verify activity chain returns valid under default timezone
    res = await db_session.execute(
        text(
            "SELECT is_valid, checked_rows, first_broken_seq, first_broken_id, failure_reason "
            "FROM verify_activity_chain(:ws_id)"
        ),
        {"ws_id": ws_id},
    )
    report = res.mappings().one()
    assert report["is_valid"] is True
    assert report["checked_rows"] == 5
    assert report["first_broken_seq"] is None
    assert report["first_broken_id"] is None
    assert report["failure_reason"] is None

    # 4. Verify chain verification is independent of session timezone
    for tz in ("America/New_York", "Asia/Tokyo", "Europe/London", "UTC"):
        await db_session.execute(text(f"SET LOCAL TIME ZONE '{tz}'"))
        tz_res = await db_session.execute(
            text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws_id)"),
            {"ws_id": ws_id},
        )
        tz_report = tz_res.mappings().one()
        assert tz_report["is_valid"] is True
        assert tz_report["checked_rows"] == 5


async def test_02_partition_rollover_and_continuous_chain(db_session: AsyncSession) -> None:
    """Test Case 2: Partition rollover routes rows to partitions while maintaining one chain."""
    ws_id = await _create_workspace(db_session)

    # 1. Call ensure_activity_partitions for Nov 2027 + 2 months ahead (Nov, Dec 2027, Jan 2028)
    res_parts = await db_session.execute(
        text("SELECT ensure_activity_partitions('2027-11-15 00:00:00+00'::timestamptz, 0, 2)")
    )
    created = res_parts.scalar_one()
    assert created == 3

    # 2. Insert row 1 dated in Dec 2027 and row 2 dated in Jan 2028
    res1 = await db_session.execute(
        text(
            "INSERT INTO activity_records ("
            "  workspace_id, recorded_at, event_type, payload"
            ") VALUES ("
            "  :ws_id, '2027-12-15 12:00:00+00', 'YEAR_END_EVENT', :payload"
            ") RETURNING id, chain_seq, tableoid::regclass::text as part_name"
        ),
        {"ws_id": ws_id, "payload": json.dumps({"note": "December 2027"})},
    )
    row1 = res1.mappings().one()
    assert row1["chain_seq"] == 1
    assert row1["part_name"] == "activity_records_y2027m12"

    res2 = await db_session.execute(
        text(
            "INSERT INTO activity_records ("
            "  workspace_id, recorded_at, event_type, payload"
            ") VALUES ("
            "  :ws_id, '2028-01-10 10:00:00+00', 'NEW_YEAR_EVENT', :payload"
            ") RETURNING id, chain_seq, tableoid::regclass::text as part_name"
        ),
        {"ws_id": ws_id, "payload": json.dumps({"note": "January 2028"})},
    )
    row2 = res2.mappings().one()
    assert row2["chain_seq"] == 2
    assert row2["part_name"] == "activity_records_y2028m01"

    # Distinct partitions across year boundary
    assert row1["part_name"] != row2["part_name"]

    # 3. Continuous chain verification succeeds across partition boundary
    verify_res = await db_session.execute(
        text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws_id)"),
        {"ws_id": ws_id},
    )
    report = verify_res.mappings().one()
    assert report["is_valid"] is True
    assert report["checked_rows"] == 2


async def test_03_immutability_trigger_and_forgery_defense(db_session: AsyncSession) -> None:
    """Test Case 3a: Rejection of UPDATE/DELETE by trigger, and overwrite of forged hashes."""
    ws_id = await _create_workspace(db_session)

    res = await db_session.execute(
        text("SELECT append_activity(:ws_id, NULL, NULL, NULL, 'SAMPLE_EVENT', '{}'::jsonb)"),
        {"ws_id": ws_id},
    )
    rec_id = res.scalar_one()

    # 1. Superuser UPDATE rejected by trigger
    with pytest.raises(DBAPIError) as exc_up:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE activity_records SET payload = '{\"tamper\": true}' WHERE id = :id"),
                {"id": rec_id},
            )
    assert "ACTIVITY_LEDGER_IMMUTABLE" in str(exc_up.value)

    # 2. Superuser DELETE rejected by trigger
    with pytest.raises(DBAPIError) as exc_del:
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM activity_records WHERE id = :id"),
                {"id": rec_id},
            )
    assert "ACTIVITY_LEDGER_IMMUTABLE" in str(exc_del.value)

    # 3. Direct INSERT with forged chain_seq, prev_hash, and row_hash gets overwritten
    fake_prev = bytes([0xAA] * 32)
    fake_row = bytes([0xBB] * 32)
    res_fake = await db_session.execute(
        text(
            "INSERT INTO activity_records ("
            "  workspace_id, chain_seq, prev_hash, row_hash, event_type, payload"
            ") VALUES ("
            "  :ws_id, 9999, :prev_hash, :row_hash, 'FORGED_INSERT', '{}'"
            ") RETURNING chain_seq, prev_hash, row_hash"
        ),
        {"ws_id": ws_id, "prev_hash": fake_prev, "row_hash": fake_row},
    )
    forged_row = res_fake.mappings().one()
    # Stored chain_seq is 2 (correct next seq), prev_hash is row 1's row_hash, row_hash is computed
    assert forged_row["chain_seq"] == 2
    assert forged_row["prev_hash"] != fake_prev
    assert forged_row["row_hash"] != fake_row


async def test_03_privilege_rejections_as_kanban_app(app_session: AsyncSession) -> None:
    """Test Case 3b: kanban_app role UPDATE/DELETE rejected by privilege layer (42501)."""
    ws_id = await _create_workspace(app_session)

    res = await app_session.execute(
        text("SELECT append_activity(:ws_id, NULL, NULL, NULL, 'APP_EVENT', '{}'::jsonb)"),
        {"ws_id": ws_id},
    )
    rec_id = res.scalar_one()

    # 1. kanban_app role UPDATE rejected by privilege layer (42501)
    with pytest.raises((ProgrammingError, DBAPIError)) as exc_app_up:
        async with app_session.begin_nested():
            await app_session.execute(
                text("UPDATE activity_records SET payload = '{}' WHERE id = :id"),
                {"id": rec_id},
            )
    orig_up = getattr(exc_app_up.value, "orig", None)
    pgcode_up = getattr(orig_up, "pgcode", None) or getattr(orig_up, "sqlstate", None)
    assert pgcode_up == "42501"

    # 2. kanban_app role DELETE rejected by privilege layer (42501)
    with pytest.raises((ProgrammingError, DBAPIError)) as exc_app_del:
        async with app_session.begin_nested():
            await app_session.execute(
                text("DELETE FROM activity_records WHERE id = :id"),
                {"id": rec_id},
            )
    orig_del = getattr(exc_app_del.value, "orig", None)
    pgcode_del = getattr(orig_del, "pgcode", None) or getattr(orig_del, "sqlstate", None)
    assert pgcode_del == "42501"

    # 3. kanban_app direct manipulation of activity_chain_heads rejected (42501)
    with pytest.raises((ProgrammingError, DBAPIError)) as exc_head:
        async with app_session.begin_nested():
            await app_session.execute(
                text("UPDATE activity_chain_heads SET last_seq = 0 WHERE workspace_id = :ws_id"),
                {"ws_id": ws_id},
            )
    orig_head = getattr(exc_head.value, "orig", None)
    pgcode_head = getattr(orig_head, "pgcode", None) or getattr(orig_head, "sqlstate", None)
    assert pgcode_head == "42501"


async def test_04_tamper_detection(db_session: AsyncSession) -> None:
    """Test Case 4: verify_activity_chain detects mutation, hash mismatch, and row deletion."""
    ws_id = await _create_workspace(db_session)

    # Append 5 events
    ids: list[uuid.UUID] = []
    for i in range(1, 6):
        res = await db_session.execute(
            text("SELECT append_activity(:ws_id, NULL, NULL, NULL, 'EVENT_TEST', :payload)"),
            {"ws_id": ws_id, "payload": json.dumps({"step": i})},
        )
        ids.append(res.scalar_one())

    # Initial check is valid
    chk0 = await db_session.execute(
        text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws_id)"),
        {"ws_id": ws_id},
    )
    assert chk0.mappings().one()["is_valid"] is True

    # Scenario (a): Mutate payload of row 3 with triggers disabled
    await db_session.execute(text("ALTER TABLE activity_records DISABLE TRIGGER USER"))
    await db_session.execute(
        text(
            "UPDATE activity_records SET payload = '{\"tampered\": true}' "
            "WHERE workspace_id = :ws_id AND chain_seq = 3"
        ),
        {"ws_id": ws_id},
    )
    await db_session.execute(text("ALTER TABLE activity_records ENABLE TRIGGER USER"))

    res_a = await db_session.execute(
        text(
            "SELECT is_valid, checked_rows, first_broken_seq, first_broken_id, failure_reason "
            "FROM verify_activity_chain(:ws_id)"
        ),
        {"ws_id": ws_id},
    )
    rep_a = res_a.mappings().one()
    assert rep_a["is_valid"] is False
    assert rep_a["first_broken_seq"] == 3
    assert rep_a["first_broken_id"] == ids[2]
    assert rep_a["failure_reason"] == "ROW_HASH_MISMATCH"

    # Scenario (b): Recompute row 3's row_hash without updating row 4's prev_hash
    await db_session.execute(text("ALTER TABLE activity_records DISABLE TRIGGER USER"))
    row3_data = await db_session.execute(
        text(
            "SELECT prev_hash, chain_seq, id, object_id, object_type, actor_id, "
            "event_type, recorded_at, payload "
            "FROM activity_records WHERE workspace_id = :ws_id AND chain_seq = 3"
        ),
        {"ws_id": ws_id},
    )
    r3 = row3_data.mappings().one()
    new_h3 = await db_session.execute(
        text(
            "SELECT compute_activity_row_hash("
            "  :prev_hash, :ws_id, :chain_seq, :id, :obj_id, :obj_type, "
            "  :actor_id, :event_type, :recorded_at, :payload"
            ")"
        ),
        {
            "prev_hash": r3["prev_hash"],
            "ws_id": ws_id,
            "chain_seq": r3["chain_seq"],
            "id": r3["id"],
            "obj_id": r3["object_id"],
            "obj_type": r3["object_type"],
            "actor_id": r3["actor_id"],
            "event_type": r3["event_type"],
            "recorded_at": r3["recorded_at"],
            "payload": json.dumps(r3["payload"]),
        },
    )
    await db_session.execute(
        text(
            "UPDATE activity_records SET row_hash = :new_hash "
            "WHERE workspace_id = :ws_id AND chain_seq = 3"
        ),
        {"ws_id": ws_id, "new_hash": new_h3.scalar_one()},
    )
    await db_session.execute(text("ALTER TABLE activity_records ENABLE TRIGGER USER"))

    res_b = await db_session.execute(
        text(
            "SELECT is_valid, checked_rows, first_broken_seq, first_broken_id, failure_reason "
            "FROM verify_activity_chain(:ws_id)"
        ),
        {"ws_id": ws_id},
    )
    rep_b = res_b.mappings().one()
    assert rep_b["is_valid"] is False
    assert rep_b["first_broken_seq"] == 4
    assert rep_b["first_broken_id"] == ids[3]
    assert rep_b["failure_reason"] == "PREV_HASH_MISMATCH"

    # Scenario (c): Delete row 2 in a fresh workspace
    ws2_id = await _create_workspace(db_session)
    w2_ids: list[uuid.UUID] = []
    for _i in range(1, 4):
        r = await db_session.execute(
            text("SELECT append_activity(:ws_id, NULL, NULL, NULL, 'EVENT_TEST', '{}'::jsonb)"),
            {"ws_id": ws2_id},
        )
        w2_ids.append(r.scalar_one())

    await db_session.execute(text("ALTER TABLE activity_records DISABLE TRIGGER USER"))
    await db_session.execute(
        text("DELETE FROM activity_records WHERE workspace_id = :ws_id AND chain_seq = 2"),
        {"ws_id": ws2_id},
    )
    await db_session.execute(text("ALTER TABLE activity_records ENABLE TRIGGER USER"))

    res_c = await db_session.execute(
        text(
            "SELECT is_valid, checked_rows, first_broken_seq, first_broken_id, failure_reason "
            "FROM verify_activity_chain(:ws_id)"
        ),
        {"ws_id": ws2_id},
    )
    rep_c = res_c.mappings().one()
    assert rep_c["is_valid"] is False
    assert rep_c["first_broken_seq"] == 3
    assert rep_c["first_broken_id"] == w2_ids[2]
    assert rep_c["failure_reason"] == "SEQ_GAP"


async def test_06_boundary_payload_and_event_type(db_session: AsyncSession) -> None:
    """Test Case 6a: Boundary payload size limits (16384 vs 16385) and event format regex."""
    ws_id = await _create_workspace(db_session)

    # 1. Payload of 16384 bytes succeeds; 16385 bytes raises 23514
    raw_prefix = '{"k": "'
    raw_suffix = '"}'
    overhead = len(raw_prefix) + len(raw_suffix)
    exact_16384_payload = raw_prefix + ("a" * (16384 - overhead)) + raw_suffix
    assert len(exact_16384_payload.encode("utf-8")) == 16384

    await db_session.execute(
        text("SELECT append_activity(:ws_id, NULL, NULL, NULL, 'MAX_PAYLOAD', CAST(:p AS jsonb))"),
        {"ws_id": ws_id, "p": exact_16384_payload},
    )

    exact_16385_payload = raw_prefix + ("a" * (16385 - overhead)) + raw_suffix
    assert len(exact_16385_payload.encode("utf-8")) == 16385

    with pytest.raises(IntegrityError) as exc_oversize:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "SELECT append_activity("
                    "  :ws_id, NULL, NULL, NULL, 'OVERSIZE_PAYLOAD', CAST(:p AS jsonb)"
                    ")"
                ),
                {"ws_id": ws_id, "p": exact_16385_payload},
            )
    orig_over = getattr(exc_oversize.value, "orig", None)
    pgcode_over = getattr(orig_over, "pgcode", None) or getattr(orig_over, "sqlstate", None)
    assert pgcode_over == "23514"

    # 2. Invalid event_type format raises 23514
    with pytest.raises(IntegrityError) as exc_evt:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT append_activity(:ws_id, NULL, NULL, NULL, 'lowercase_event')"),
                {"ws_id": ws_id},
            )
    orig_evt = getattr(exc_evt.value, "orig", None)
    pgcode_evt = getattr(orig_evt, "pgcode", None) or getattr(orig_evt, "sqlstate", None)
    assert pgcode_evt == "23514"


async def test_06_boundary_null_pairs_and_mismatches(db_session: AsyncSession) -> None:
    """Test Case 6b: Null pairing constraints, object mismatches, and partition bounds."""
    ws1_id = await _create_workspace(db_session, name="Workspace 1")
    ws2_id = await _create_workspace(db_session, name="Workspace 2")

    # 1. Null pairing: non-null object_id with NULL object_type raises 23514
    with pytest.raises(IntegrityError) as exc_null_pair:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO activity_records ("
                    "  workspace_id, object_id, object_type, event_type"
                    ") VALUES ("
                    "  :ws_id, :obj_id, NULL, 'TEST_NULL_PAIR'"
                    ")"
                ),
                {"ws_id": ws1_id, "obj_id": uuid.uuid4()},
            )
    orig_np = getattr(exc_null_pair.value, "orig", None)
    pgcode_np = getattr(orig_np, "pgcode", None) or getattr(orig_np, "sqlstate", None)
    assert pgcode_np == "23514"

    # 2. Null pairing: NULL object_id with non-null object_type raises 23514
    with pytest.raises(IntegrityError) as exc_null_pair2:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO activity_records ("
                    "  workspace_id, object_id, object_type, event_type"
                    ") VALUES ("
                    "  :ws_id, NULL, 'issue'::object_kind, 'TEST_NULL_PAIR_2'"
                    ")"
                ),
                {"ws_id": ws1_id},
            )
    orig_np2 = getattr(exc_null_pair2.value, "orig", None)
    pgcode_np2 = getattr(orig_np2, "pgcode", None) or getattr(orig_np2, "sqlstate", None)
    assert pgcode_np2 == "23514"

    # 3. Cross-workspace object link in activity event raises ACTIVITY_OBJECT_MISMATCH
    obj_ws2_id = await _register_obj(db_session, ws2_id, "issue", "W2-ISSUE")
    with pytest.raises(DBAPIError) as exc_obj_ws:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT append_activity(:ws_id, :obj_id, 'issue', NULL, 'CROSS_WS_EVENT')"),
                {"ws_id": ws1_id, "obj_id": obj_ws2_id},
            )
    assert "ACTIVITY_OBJECT_MISMATCH" in str(exc_obj_ws.value)

    # 4. Non-existent object in same workspace raises ACTIVITY_OBJECT_MISMATCH
    with pytest.raises(DBAPIError) as exc_nonexistent:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "SELECT append_activity("
                    "  :ws_id, :obj_id, 'issue', NULL, 'NONEXISTENT_OBJ_EVENT'"
                    ")"
                ),
                {"ws_id": ws1_id, "obj_id": uuid.uuid4()},
            )
    assert "ACTIVITY_OBJECT_MISMATCH" in str(exc_nonexistent.value)

    # 5. ensure_activity_partitions invalid range parameters
    with pytest.raises(DBAPIError) as exc_part_range:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT ensure_activity_partitions(clock_timestamp(), -1, 6)")
            )
    assert "PARTITION_RANGE_INVALID" in str(exc_part_range.value)

    # 6. Empty workspace verify_activity_chain returns is_valid = true, checked_rows = 0
    empty_ws_id = await _create_workspace(db_session, name="Empty Workspace")
    res_empty = await db_session.execute(
        text("SELECT is_valid, checked_rows, first_broken_seq FROM verify_activity_chain(:ws_id)"),
        {"ws_id": empty_ws_id},
    )
    rep_empty = res_empty.mappings().one()
    assert rep_empty["is_valid"] is True
    assert rep_empty["checked_rows"] == 0
    assert rep_empty["first_broken_seq"] is None
