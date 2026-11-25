# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for link auditor admin REST endpoints (KB-P4-11, S12.3)."""

from __future__ import annotations

import base64
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.services.link_auditor_admin import _decode_cursor, purge_flagged_links
from kanban.tests.security.helpers import add_role_binding

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


@pytest.fixture(autouse=True)
def setup_test_key_material(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up valid test key material in environment."""
    monkeypatch.delenv("KANBAN_KEYRING_FILE", raising=False)
    monkeypatch.setenv("KANBAN_MASTER_KEK", _b64(b"k" * 32))
    monkeypatch.setenv("KANBAN_AUTH_PEPPER", _b64(b"p" * 32))
    monkeypatch.setenv("KANBAN_SESSION_HMAC_KEY", _b64(b"s" * 32))
    monkeypatch.setenv("KANBAN_MASTER_KEK_KID", "test-kid-1")


async def _enroll_totp(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Enroll and confirm TOTP factor for user so AAL2 passes."""
    await session.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": user_id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await session.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": user_id},
    )
    p_row = res.mappings().first()
    if p_row:
        await session.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await session.commit()


async def _create_test_project_and_issues(
    session: AsyncSession,
    ws_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create test project and two issues."""
    u_id = uuid.uuid4()
    p_reg = await session.execute(
        text("SELECT register_object('project'::object_kind, :ws_id, NULL, 'PRJ', 'Test', :u_id)"),
        {"ws_id": ws_id, "u_id": u_id},
    )
    proj_id = p_reg.scalar_one()
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws_id, 'PRJ', 'Test')"
        ),
        {"id": proj_id, "ws_id": ws_id},
    )

    st_res = await session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"),
        {"p": proj_id},
    )
    st_id = st_res.scalar_one()

    # Issue 1
    seq1 = await session.scalar(
        text("SELECT allocate_issue_sequence(:pid)"),
        {"pid": proj_id},
    )
    i1_reg = await session.execute(
        text(
            "SELECT register_object("
            "  'issue'::object_kind, :ws_id, :proj_id, :ckey, 'Issue 1', :u_id"
            ")"
        ),
        {"ws_id": ws_id, "proj_id": proj_id, "ckey": f"PRJ-{seq1}", "u_id": user_id},
    )
    iss1 = i1_reg.scalar_one()
    await session.execute(
        text(
            "INSERT INTO issues ("
            "  id, workspace_id, project_id, sequence_id, summary, "
            "  description_markdown, state_id, priority_id, "
            "  created_by_id, original_created_by_id, board_rank"
            ") VALUES ("
            "  :id, :ws_id, :proj_id, :seq, 'Issue 1', 'Desc', :st_id, "
            "  (SELECT id FROM project_priorities WHERE project_id = :proj_id AND slug = 'none'), "
            "  :user_id, :user_id, 1.0"
            ")"
        ),
        {
            "id": iss1,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "seq": seq1,
            "st_id": st_id,
            "user_id": user_id,
        },
    )

    # Issue 2
    seq2 = await session.scalar(
        text("SELECT allocate_issue_sequence(:pid)"),
        {"pid": proj_id},
    )
    i2_reg = await session.execute(
        text(
            "SELECT register_object("
            "  'issue'::object_kind, :ws_id, :proj_id, :ckey, 'Issue 2', :u_id"
            ")"
        ),
        {"ws_id": ws_id, "proj_id": proj_id, "ckey": f"PRJ-{seq2}", "u_id": user_id},
    )
    iss2 = i2_reg.scalar_one()
    await session.execute(
        text(
            "INSERT INTO issues ("
            "  id, workspace_id, project_id, sequence_id, summary, "
            "  description_markdown, state_id, priority_id, "
            "  created_by_id, original_created_by_id, board_rank"
            ") VALUES ("
            "  :id, :ws_id, :proj_id, :seq, 'Issue 2', 'Desc', :st_id, "
            "  (SELECT id FROM project_priorities WHERE project_id = :proj_id AND slug = 'none'), "
            "  :user_id, :user_id, 2.0"
            ")"
        ),
        {
            "id": iss2,
            "ws_id": ws_id,
            "proj_id": proj_id,
            "seq": seq2,
            "st_id": st_id,
            "user_id": user_id,
        },
    )

    # Link 1 -> 2 (BLOCKS)
    await session.execute(
        text(
            "INSERT INTO object_links ("
            "  workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, created_by_id"
            ") VALUES ("
            "  :ws_id, :s_id, 'issue', :t_id, 'issue', 'BLOCKS', :user_id"
            ")"
        ),
        {"ws_id": ws_id, "s_id": iss1, "t_id": iss2, "user_id": user_id},
    )
    # Link 2 -> 1 (RELATES_TO)
    await session.execute(
        text(
            "INSERT INTO object_links ("
            "  workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, created_by_id"
            ") VALUES ("
            "  :ws_id, :s_id, 'issue', :t_id, 'issue', 'RELATES_TO', :user_id"
            ")"
        ),
        {"ws_id": ws_id, "s_id": iss2, "t_id": iss1, "user_id": user_id},
    )
    await session.commit()
    return proj_id, iss1, iss2


@pytest.mark.asyncio
async def test_admin_link_auditor_security_gates(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    contract_recorder: ContractRecorder,
) -> None:
    """Verify 401 unauth, 403 AAL2_REQUIRED on AAL1, and 403 FORBIDDEN on non-admin."""
    admin_user = await make_user("link_admin_sec", workspace_role="WORKSPACE_ADMIN")
    member_user = await make_user("link_member_sec", workspace_role="WORKSPACE_MEMBER")
    await _enroll_totp(api_env.seed, admin_user.id)
    await _enroll_totp(api_env.seed, member_user.id)

    client = api_env.client

    # 1. Unauthenticated -> 401
    api_env.resolver.principal = None
    r1 = await client.post("/api/v1/admin/object-links:audit")
    assert r1.status_code == 401
    r2 = await client.get("/api/v1/admin/object-links/audits")
    assert r2.status_code == 401
    r3 = await client.post(
        "/api/v1/admin/object-links:purge",
        json={"audit_ids": [str(uuid.uuid4())], "reason": "Administrative link purge test"},
    )
    assert r3.status_code == 401

    # 2. AAL1 -> 403 AAL2_REQUIRED
    api_env.resolver.principal = PrincipalContext(
        principal_id=admin_user.id,
        workspace_id=admin_user.workspace_id,
        aal_level=1,
    )
    r1 = await client.post("/api/v1/admin/object-links:audit")
    assert r1.status_code == 403
    assert r1.json()["code"] == "AAL2_REQUIRED"
    contract_recorder.record("admin_link_auditor_aal2_required_403", r1.request, r1)
    r2 = await client.get("/api/v1/admin/object-links/audits")
    assert r2.status_code == 403
    assert r2.json()["code"] == "AAL2_REQUIRED"
    r3 = await client.post(
        "/api/v1/admin/object-links:purge",
        json={"audit_ids": [str(uuid.uuid4())], "reason": "Administrative link purge test"},
    )
    assert r3.status_code == 403
    assert r3.json()["code"] == "AAL2_REQUIRED"

    # 3. Non-admin with AAL2 -> 403 FORBIDDEN
    api_env.resolver.principal = PrincipalContext(
        principal_id=member_user.id,
        workspace_id=member_user.workspace_id,
        aal_level=2,
    )
    r1 = await client.post("/api/v1/admin/object-links:audit")
    assert r1.status_code == 403
    assert r1.json()["code"] == "FORBIDDEN"
    r2 = await client.get("/api/v1/admin/object-links/audits")
    assert r2.status_code == 403
    assert r2.json()["code"] == "FORBIDDEN"
    r3 = await client.post(
        "/api/v1/admin/object-links:purge",
        json={"audit_ids": [str(uuid.uuid4())], "reason": "Administrative link purge test"},
    )
    assert r3.status_code == 403
    assert r3.json()["code"] == "FORBIDDEN"

    # 4. Project Admin with AAL2 passes require_admin_aal2
    # but fails require_workspace_or_server_admin -> 403 INSUFFICIENT_CAPABILITY
    proj_id, _, _ = await _create_test_project_and_issues(
        api_env.seed, admin_user.workspace_id, admin_user.id
    )
    proj_admin_user = await make_user("link_proj_admin", workspace_role="WORKSPACE_MEMBER")
    await add_role_binding(
        api_env.seed,
        proj_admin_user.workspace_id,
        proj_admin_user.id,
        "PROJECT_ADMIN",
        project_id=proj_id,
    )
    await _enroll_totp(api_env.seed, proj_admin_user.id)
    api_env.resolver.principal = PrincipalContext(
        principal_id=proj_admin_user.id,
        workspace_id=proj_admin_user.workspace_id,
        aal_level=2,
    )
    r_pa = await client.post("/api/v1/admin/object-links:audit")
    assert r_pa.status_code == 403
    assert r_pa.json()["code"] == "INSUFFICIENT_CAPABILITY"
    contract_recorder.record("admin_link_auditor_insufficient_capability_403", r_pa.request, r_pa)


@pytest.mark.asyncio
async def test_admin_link_auditor_scan_and_list(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    contract_recorder: ContractRecorder,
) -> None:
    """Verify run audit scan and query list of flagged invalid links."""
    admin_user = await make_user("link_admin_scan", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin_user.id)

    _, iss1, _ = await _create_test_project_and_issues(
        api_env.seed, admin_user.workspace_id, admin_user.id
    )

    # Trigger ARCHIVED_POLICY_VIOLATION by setting archived_at on issue1
    await api_env.seed.execute(
        text("UPDATE objects SET archived_at = clock_timestamp() WHERE id = :id"),
        {"id": iss1},
    )
    await api_env.seed.commit()

    api_env.resolver.principal = PrincipalContext(
        principal_id=admin_user.id,
        workspace_id=admin_user.workspace_id,
        aal_level=2,
    )
    client = api_env.client

    # 1. Run audit scan
    resp_scan = await client.post("/api/v1/admin/object-links:audit")
    assert resp_scan.status_code == 200
    contract_recorder.record("admin_link_auditor_scan_200", resp_scan.request, resp_scan)
    scan_data = resp_scan.json()
    assert scan_data["flagged_total"] >= 1
    assert "ARCHIVED_POLICY_VIOLATION" in scan_data["by_reason"]
    assert scan_data["by_reason"]["ARCHIVED_POLICY_VIOLATION"] >= 1

    # 2. List audits (default unpurged)
    resp_list = await client.get("/api/v1/admin/object-links/audits?limit=10")
    assert resp_list.status_code == 200
    contract_recorder.record("admin_link_auditor_list_200", resp_list.request, resp_list)
    list_data = resp_list.json()
    assert len(list_data["items"]) >= 1
    item = list_data["items"][0]
    assert item["reason"] == "ARCHIVED_POLICY_VIOLATION"
    assert item["purged_at"] is None
    assert "link_snapshot" in item

    # 3. Filter by reason_code
    resp_filtered = await client.get(
        "/api/v1/admin/object-links/audits?reason_code=ARCHIVED_POLICY_VIOLATION"
    )
    assert resp_filtered.status_code == 200
    assert len(resp_filtered.json()["items"]) >= 1

    # Non-matching reason
    resp_empty = await client.get(
        "/api/v1/admin/object-links/audits?reason_code=CROSS_WORKSPACE_LEAK"
    )
    assert resp_empty.status_code == 200
    assert len(resp_empty.json()["items"]) == 0

    # 4. Status filter: purged should be 0 before purge
    resp_purged = await client.get("/api/v1/admin/object-links/audits?status=purged")
    assert resp_purged.status_code == 200
    assert len(resp_purged.json()["items"]) == 0

    # 5. Status filter: resolved and all
    resp_all = await client.get("/api/v1/admin/object-links/audits?status=all")
    assert resp_all.status_code == 200
    assert len(resp_all.json()["items"]) >= 1

    first_item_id = resp_all.json()["items"][0]["id"]
    await api_env.seed.execute(
        text(
            "UPDATE invalid_object_link_audits SET resolved_at = clock_timestamp() WHERE id = :id"
        ),
        {"id": first_item_id},
    )
    await api_env.seed.commit()
    resp_res = await client.get("/api/v1/admin/object-links/audits?status=resolved")
    assert resp_res.status_code == 200
    assert len(resp_res.json()["items"]) >= 1

    # Reset resolved_at
    await api_env.seed.execute(
        text("UPDATE invalid_object_link_audits SET resolved_at = NULL WHERE id = :id"),
        {"id": first_item_id},
    )
    await api_env.seed.commit()

    # 6. Seed second audit record to test pagination with cursor
    second_audit_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "INSERT INTO invalid_object_link_audits ("
            "  id, workspace_id, link_id, reason, detected_at, link_snapshot"
            ") VALUES ("
            "  :id, :ws_id, :link_id, 'PERMISSION_SEVERED', "
            "  clock_timestamp() - interval '5 minutes', '{}'"
            ")"
        ),
        {
            "id": second_audit_id,
            "ws_id": admin_user.workspace_id,
            "link_id": uuid.uuid4(),
        },
    )
    await api_env.seed.commit()

    resp_page1 = await client.get("/api/v1/admin/object-links/audits?limit=1")
    assert resp_page1.status_code == 200
    p1_data = resp_page1.json()
    assert len(p1_data["items"]) == 1
    assert p1_data["has_more"] is True
    assert p1_data["next_cursor"] is not None

    resp_page2 = await client.get(
        f"/api/v1/admin/object-links/audits?limit=1&cursor={p1_data['next_cursor']}"
    )
    assert resp_page2.status_code == 200
    p2_data = resp_page2.json()
    assert len(p2_data["items"]) >= 1
    assert p2_data["items"][0]["id"] != p1_data["items"][0]["id"]

    # 7. Validation errors
    bad_reason = await client.get("/api/v1/admin/object-links/audits?reason_code=INVALID_ENUM")
    assert bad_reason.status_code == 422

    bad_status = await client.get("/api/v1/admin/object-links/audits?status=invalid_status")
    assert bad_status.status_code == 422

    bad_cursor = await client.get("/api/v1/admin/object-links/audits?cursor=not-a-valid-cursor!!!")
    assert bad_cursor.status_code == 422

    bad_cursor_colon = await client.get("/api/v1/admin/object-links/audits?cursor=bm9fc2VwYXJhdG9y")
    assert bad_cursor_colon.status_code == 422

    bad_cursor_content = await client.get(
        "/api/v1/admin/object-links/audits?cursor=bm90YWRhdGU6bm90YXV1aWQ="
    )
    assert bad_cursor_content.status_code == 422


@pytest.mark.asyncio
async def test_admin_link_auditor_purge_lifecycle(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    contract_recorder: ContractRecorder,
) -> None:
    """Verify purge invalid links, conflict validation, and activity ledger logging."""
    admin_user = await make_user("link_admin_purge", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin_user.id)

    _, iss1, _ = await _create_test_project_and_issues(
        api_env.seed, admin_user.workspace_id, admin_user.id
    )

    # Trigger ARCHIVED_POLICY_VIOLATION
    await api_env.seed.execute(
        text("UPDATE objects SET archived_at = clock_timestamp() WHERE id = :id"),
        {"id": iss1},
    )
    await api_env.seed.commit()

    api_env.resolver.principal = PrincipalContext(
        principal_id=admin_user.id,
        workspace_id=admin_user.workspace_id,
        aal_level=2,
    )
    client = api_env.client

    # Scan to produce invalid link audit records
    await client.post("/api/v1/admin/object-links:audit")

    # Get flagged audit ID
    resp_list = await client.get("/api/v1/admin/object-links/audits?status=unpurged")
    items = resp_list.json()["items"]
    assert len(items) >= 1
    target_audit_id = items[0]["id"]
    target_link_id = items[0]["link_id"]

    # 1. Validation error: reason too short (< 10 chars)
    resp_short = await client.post(
        "/api/v1/admin/object-links:purge",
        json={"audit_ids": [target_audit_id], "reason": "short"},
    )
    assert resp_short.status_code == 422

    # Validation error: reason too long (> 500 chars)
    resp_long = await client.post(
        "/api/v1/admin/object-links:purge",
        json={"audit_ids": [target_audit_id], "reason": "x" * 501},
    )
    assert resp_long.status_code == 422

    # Validation error: empty audit_ids
    resp_empty_ids = await client.post(
        "/api/v1/admin/object-links:purge",
        json={"audit_ids": [], "reason": "Administrative purge of invalid links"},
    )
    assert resp_empty_ids.status_code == 422

    # 2. Conflict: 409 LINK_NOT_FLAGGED on non-existent / active link
    fake_id = str(uuid.uuid4())
    resp_conflict = await client.post(
        "/api/v1/admin/object-links:purge",
        json={"audit_ids": [fake_id], "reason": "Purge non-existent link audit record"},
    )
    assert resp_conflict.status_code == 409
    assert resp_conflict.json()["code"] == "LINK_NOT_FLAGGED"
    contract_recorder.record(
        "admin_link_auditor_conflict_409", resp_conflict.request, resp_conflict
    )

    # 3. Successful purge
    resp_purge = await client.post(
        "/api/v1/admin/object-links:purge",
        json={
            "audit_ids": [target_audit_id],
            "reason": "Administrative remediation of archived policy violation",
        },
    )
    assert resp_purge.status_code == 200
    contract_recorder.record("admin_link_auditor_purge_200", resp_purge.request, resp_purge)
    purge_data = resp_purge.json()
    assert purge_data["purged_count"] == 1
    assert len(purge_data["activity_ids"]) >= 1

    # 4. Verify link was deleted from object_links
    link_check = await api_env.seed.execute(
        text("SELECT id FROM object_links WHERE id = :id"),
        {"id": target_link_id},
    )
    assert link_check.first() is None

    # 5. Verify audit record is now marked purged
    resp_after = await client.get("/api/v1/admin/object-links/audits?status=purged")
    purged_items = resp_after.json()["items"]
    assert any(p["id"] == target_audit_id for p in purged_items)

    # 6. Re-purging the same audit ID fails with 409 LINK_NOT_FLAGGED
    resp_re_purge = await client.post(
        "/api/v1/admin/object-links:purge",
        json={
            "audit_ids": [target_audit_id],
            "reason": "Attempting duplicate purge on already purged record",
        },
    )
    assert resp_re_purge.status_code == 409
    assert resp_re_purge.json()["code"] == "LINK_NOT_FLAGGED"


@pytest.mark.asyncio
async def test_admin_link_auditor_service_direct_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test direct service functions for defensive parameter validation."""
    admin_user = await make_user("link_srv_edge", workspace_role="WORKSPACE_ADMIN")
    caller = PrincipalContext(
        principal_id=admin_user.id,
        workspace_id=admin_user.workspace_id,
        aal_level=2,
    )

    # 1. Invalid reason length in service
    with pytest.raises(ProblemException) as exc1:
        await purge_flagged_links(
            api_env.seed,
            caller,
            admin_user.workspace_id,
            audit_ids=[uuid.uuid4()],
            reason="short",
        )
    assert exc1.value.status == 422

    with pytest.raises(ProblemException) as exc2:
        await purge_flagged_links(
            api_env.seed,
            caller,
            admin_user.workspace_id,
            audit_ids=[uuid.uuid4()],
            reason="x" * 501,
        )
    assert exc2.value.status == 422

    # 2. Empty audit IDs in service
    with pytest.raises(ProblemException) as exc3:
        await purge_flagged_links(
            api_env.seed,
            caller,
            admin_user.workspace_id,
            audit_ids=[],
            reason="Valid length justification text",
        )
    assert exc3.value.status == 422

    # 3. Direct cursor decode error
    with pytest.raises(ProblemException) as exc4:
        _decode_cursor("not_valid_base64_!!!")
    assert exc4.value.status == 422


@pytest.mark.asyncio
async def test_require_workspace_or_server_admin_forbidden(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Test require_workspace_or_server_admin raises 403 INSUFFICIENT_CAPABILITY."""
    from kanban.api.v1.admin.link_auditor import require_workspace_or_server_admin

    member_user = await make_user("link_member_unauth", workspace_role="WORKSPACE_MEMBER")
    caller = PrincipalContext(
        principal_id=member_user.id,
        workspace_id=member_user.workspace_id,
        aal_level=2,
    )
    with pytest.raises(ProblemException) as exc:
        await require_workspace_or_server_admin(caller, api_env.seed)
    assert exc.value.status == 403
    assert exc.value.code == "INSUFFICIENT_CAPABILITY"
