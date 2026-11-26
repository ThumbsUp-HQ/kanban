# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for Admin Trash Studio and Retention API (KAN-30 / KB-P3-AUDIT-24)."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from database.models import ObjectRecord
from kanban.api.deps import PrincipalContext

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

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


async def _as_admin_aal2(
    api_env: ApiEnv,
    user: SeededUser,
    *,
    aal2_verified_at: datetime | None = None,
) -> None:
    """Enroll confirmed TOTP factor and elevate test client to AAL2 session."""
    await api_env.seed.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'test-kid-1')"),
        {
            "p_id": user.id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await api_env.seed.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": user.id},
    )
    p_row = res.mappings().first()
    if p_row:
        await api_env.seed.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await api_env.seed.commit()

    v_time = aal2_verified_at if aal2_verified_at is not None else datetime.now(UTC)
    api_env.resolver.principal = PrincipalContext(
        principal_id=user.id,
        workspace_id=user.workspace_id,
        token_scopes=("session",),
        aal_level=2,
        aal2_verified_at=v_time,
    )


@pytest.mark.asyncio
async def test_admin_trash_listing_and_filtering(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """GET /api/v1/admin/trash lists soft-deleted objects with filters."""
    admin = await make_user("trash_ws_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("TRASH", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)
    await _as_admin_aal2(api_env, admin)

    # Create issues
    r_iss1 = await client.post("/api/v1/projects/TRASH/issues", json={"summary": "Alpha Issue"})
    assert r_iss1.status_code == 201
    iss1_id = uuid.UUID(r_iss1.json()["id"])
    iss1_key = r_iss1.json()["key"]

    r_iss2 = await client.post("/api/v1/projects/TRASH/issues", json={"summary": "Beta Issue"})
    assert r_iss2.status_code == 201
    iss2_id = uuid.UUID(r_iss2.json()["id"])

    # Create sticky
    r_sticky = await client.post(
        "/api/v1/projects/TRASH/stickies",
        json={"body_markdown": "Note to be trashed"},
    )
    assert r_sticky.status_code == 201
    sticky_id = uuid.UUID(r_sticky.json()["id"])

    # Soft-delete iss1 and sticky
    t_del = datetime.now(UTC) - timedelta(days=2)
    await api_env.seed.execute(
        text("UPDATE objects SET deleted_at = :ts WHERE id IN (:i1, :s1)"),
        {"ts": t_del, "i1": iss1_id, "s1": sticky_id},
    )
    await api_env.seed.commit()

    # 1. GET /api/v1/admin/trash (kind=all)
    resp_all = await api_env.client.get("/api/v1/admin/trash")
    assert resp_all.status_code == 200
    data_all = resp_all.json()
    assert "items" in data_all
    assert data_all["retention_days"] == 30
    trashed_ids = [item["id"] for item in data_all["items"]]
    assert str(iss1_id) in trashed_ids
    assert str(sticky_id) in trashed_ids
    assert str(iss2_id) not in trashed_ids  # Active issue not in trash

    # 2. Filter by kind=issue
    resp_issue = await api_env.client.get("/api/v1/admin/trash?kind=issue")
    assert resp_issue.status_code == 200
    data_issue = resp_issue.json()
    kinds = [item["kind"] for item in data_issue["items"]]
    assert all(k == "issue" for k in kinds)
    assert str(iss1_id) in [item["id"] for item in data_issue["items"]]
    assert str(sticky_id) not in [item["id"] for item in data_issue["items"]]

    # 3. Filter by kind=sticky
    resp_stk = await api_env.client.get("/api/v1/admin/trash?kind=sticky")
    assert resp_stk.status_code == 200
    data_stk = resp_stk.json()
    assert len(data_stk["items"]) >= 1
    assert data_stk["items"][0]["kind"] == "sticky"

    # 4. Search filter by q
    resp_q = await api_env.client.get(f"/api/v1/admin/trash?q={iss1_key}")
    assert resp_q.status_code == 200
    data_q = resp_q.json()
    assert len(data_q["items"]) == 1
    assert data_q["items"][0]["id"] == str(iss1_id)

    # 5. Filter by project_id
    resp_proj = await api_env.client.get(f"/api/v1/admin/trash?project_id={proj_id}")
    assert resp_proj.status_code == 200
    data_proj = resp_proj.json()
    assert len(data_proj["items"]) >= 2


@pytest.mark.asyncio
async def test_admin_trash_acl_deny_isolation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Workspace Admin NEVER sees restricted private items with explicit ACL DENY."""
    ws_admin = await make_user("deny_test_admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("DENY", created_by=ws_admin, roles={ws_admin: "PROJECT_ADMIN"})
    client = as_principal(ws_admin)
    await _as_admin_aal2(api_env, ws_admin)

    # Create two issues
    r1 = await client.post("/api/v1/projects/DENY/issues", json={"summary": "Visible Trashed"})
    assert r1.status_code == 201
    i1_id = uuid.UUID(r1.json()["id"])

    r2 = await client.post(
        "/api/v1/projects/DENY/issues", json={"summary": "Restricted Secret Trashed"}
    )
    assert r2.status_code == 201
    i2_id = uuid.UUID(r2.json()["id"])

    # Soft-delete both
    t_del = datetime.now(UTC) - timedelta(days=1)
    await api_env.seed.execute(
        text("UPDATE objects SET deleted_at = :ts WHERE id IN (:i1, :i2)"),
        {"ts": t_del, "i1": i1_id, "i2": i2_id},
    )

    # Inject explicit DENY for ws_admin on i2 in resource_acl_entries
    # DENY VIEW capability (bitmask 1)
    await api_env.seed.execute(
        text(
            "INSERT INTO resource_acl_entries "
            "(workspace_id, object_id, principal_id, capability_mask, effect, created_by_id) "
            "VALUES (:ws_id, :oid, :pid, 255, 'DENY', :creator)"
        ),
        {"ws_id": ws_admin.workspace_id, "oid": i2_id, "pid": ws_admin.id, "creator": ws_admin.id},
    )
    await api_env.seed.commit()

    # GET /api/v1/admin/trash as ws_admin
    resp = await api_env.client.get("/api/v1/admin/trash")
    assert resp.status_code == 200
    items = resp.json()["items"]
    item_ids = [item["id"] for item in items]

    assert str(i1_id) in item_ids
    # i2 MUST NOT be present due to explicit ACL DENY!
    assert str(i2_id) not in item_ids


@pytest.mark.asyncio
async def test_admin_trash_project_admin_isolation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Project Admin sees only items from projects they administer."""
    p_admin = await make_user("proj_admin_iso", workspace_role=None)
    other_admin = await make_user("other_admin_iso", workspace_role=None)
    await make_project("PRJ1", created_by=p_admin, roles={p_admin: "PROJECT_ADMIN"})
    await make_project("PRJ2", created_by=other_admin, roles={other_admin: "PROJECT_ADMIN"})

    # Create issues in both projects
    client1 = as_principal(p_admin)
    r1 = await client1.post("/api/v1/projects/PRJ1/issues", json={"summary": "Issue 1"})
    assert r1.status_code == 201
    i1_id = uuid.UUID(r1.json()["id"])

    client2 = as_principal(other_admin)
    r2 = await client2.post("/api/v1/projects/PRJ2/issues", json={"summary": "Issue 2"})
    assert r2.status_code == 201
    i2_id = uuid.UUID(r2.json()["id"])

    # Soft-trash both
    t_del = datetime.now(UTC) - timedelta(hours=1)
    await api_env.seed.execute(
        text("UPDATE objects SET deleted_at = :ts WHERE id IN (:i1, :i2)"),
        {"ts": t_del, "i1": i1_id, "i2": i2_id},
    )
    await api_env.seed.commit()

    # Step up p_admin to AAL2
    await _as_admin_aal2(api_env, p_admin)

    # GET /api/v1/admin/trash as p_admin
    resp = await api_env.client.get("/api/v1/admin/trash")
    assert resp.status_code == 200
    items = resp.json()["items"]
    item_ids = [item["id"] for item in items]

    assert str(i1_id) in item_ids
    assert str(i2_id) not in item_ids  # PRJ2 issue isolated from PRJ1 admin


@pytest.mark.asyncio
async def test_admin_trash_restore_and_permanent_purge_guards(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """WORKSPACE_ADMIN can restore; permanent_purge is restricted to SERVER_ADMIN."""
    ws_admin = await make_user("ws_admin_guard", workspace_role="WORKSPACE_ADMIN")
    await make_project("GUARD", created_by=ws_admin, roles={ws_admin: "PROJECT_ADMIN"})
    client = as_principal(ws_admin)
    await _as_admin_aal2(api_env, ws_admin)

    # Create issue and soft-delete it
    r_iss = await client.post(
        "/api/v1/projects/GUARD/issues", json={"summary": "Target Guard Issue"}
    )
    assert r_iss.status_code == 201
    iss_id = uuid.UUID(r_iss.json()["id"])
    iss_key = r_iss.json()["key"]

    t_del = datetime.now(UTC) - timedelta(hours=2)
    await api_env.seed.execute(
        text("UPDATE objects SET deleted_at = :ts WHERE id = :id"),
        {"ts": t_del, "id": iss_id},
    )
    await api_env.seed.commit()

    # 1. Attempt mode='permanent_purge' as WORKSPACE_ADMIN -> 403 SERVER_ADMIN_REQUIRED
    r_purge_req = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": iss_key, "mode": "permanent_purge"},
    )
    assert r_purge_req.status_code == 403
    assert r_purge_req.json()["code"] == "SERVER_ADMIN_REQUIRED"

    # 2. WORKSPACE_ADMIN + AAL2 can restore via /api/v1/admin/destructive:restore
    r_restore = await api_env.client.post(
        "/api/v1/admin/destructive:restore",
        json={
            "target_kind": "issue",
            "target": iss_key,
            "reason": "Restoring accidental trash for testing",
        },
    )
    assert r_restore.status_code == 200
    assert r_restore.json()["status"] == "restored"

    # Verify object deleted_at is now NULL
    obj_row = (
        await api_env.seed.execute(select(ObjectRecord.deleted_at).where(ObjectRecord.id == iss_id))
    ).first()
    assert obj_row is not None
    assert obj_row[0] is None

    # Soft-delete again and test restore via /api/v1/admin/trash/{target_id}:restore
    await api_env.seed.execute(
        text("UPDATE objects SET deleted_at = :ts WHERE id = :id"),
        {"ts": t_del, "id": iss_id},
    )
    await api_env.seed.commit()

    r_restore_id = await api_env.client.post(
        f"/api/v1/admin/trash/{iss_id}:restore",
    )
    assert r_restore_id.status_code == 200
    assert r_restore_id.json()["status"] == "restored"

    # 3. Test unknown kind filter -> returns empty items
    r_unk = await api_env.client.get("/api/v1/admin/trash?kind=unknown_kind")
    assert r_unk.status_code == 200
    assert r_unk.json()["items"] == []

    # 4. Test restore on non-existent object -> 404 Not Found
    r_not_found = await api_env.client.post(f"/api/v1/admin/trash/{uuid.uuid4()}:restore")
    assert r_not_found.status_code == 404


@pytest.mark.asyncio
async def test_admin_trash_project_admin_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Project Admin edge cases: project_id mismatch and unauthenticated."""
    p_user = await make_user("proj_admin_edge", workspace_role=None)
    await make_project("PRJA", created_by=p_user, roles={p_user: "PROJECT_ADMIN"})
    proj_b = await make_project("PRJB", created_by=p_user, roles={})

    as_principal(p_user)
    await _as_admin_aal2(api_env, p_user)

    # Query with project_id=proj_b where user is NOT admin
    r_mismatch = await api_env.client.get(f"/api/v1/admin/trash?project_id={proj_b}")
    assert r_mismatch.status_code == 200
    assert r_mismatch.json()["items"] == []


@pytest.mark.asyncio
async def test_admin_trash_pagination_limit_and_offset(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """GET /api/v1/admin/trash enforces limit and offset query pagination."""
    admin = await make_user("trash_page_admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("PGTR", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)
    await _as_admin_aal2(api_env, admin)

    # Create 4 issues
    created_ids: list[uuid.UUID] = []
    for idx in range(4):
        r = await client.post(
            "/api/v1/projects/PGTR/issues",
            json={"summary": f"Pagination Issue {idx}"},
        )
        assert r.status_code == 201
        created_ids.append(uuid.UUID(r.json()["id"]))

    # Soft-delete all 4 with slightly staggered timestamps (descending order by deleted_at)
    now = datetime.now(UTC)
    for idx, iss_id in enumerate(created_ids):
        t_del = now - timedelta(hours=idx + 1)
        await api_env.seed.execute(
            text("UPDATE objects SET deleted_at = :ts WHERE id = :id"),
            {"ts": t_del, "id": iss_id},
        )
    await api_env.seed.commit()

    # 1. limit=2, offset=0 returns first 2 items
    resp1 = await api_env.client.get("/api/v1/admin/trash?kind=issue&limit=2&offset=0")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert len(data1["items"]) == 2
    assert data1["items"][0]["id"] == str(created_ids[0])
    assert data1["items"][1]["id"] == str(created_ids[1])

    # 2. limit=2, offset=2 returns next 2 items
    resp2 = await api_env.client.get("/api/v1/admin/trash?kind=issue&limit=2&offset=2")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2["items"]) == 2
    assert data2["items"][0]["id"] == str(created_ids[2])
    assert data2["items"][1]["id"] == str(created_ids[3])

    # 3. limit bounds validation
    r_bad_limit = await api_env.client.get("/api/v1/admin/trash?limit=0")
    assert r_bad_limit.status_code == 422

    r_exceed_limit = await api_env.client.get("/api/v1/admin/trash?limit=501")
    assert r_exceed_limit.status_code == 422

    r_bad_offset = await api_env.client.get("/api/v1/admin/trash?offset=-1")
    assert r_bad_offset.status_code == 422


@pytest.mark.asyncio
async def test_admin_trash_filter_edge_cases(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """GET /api/v1/admin/trash edge cases: unknown kind, query filter, and project filter."""
    admin = await make_user("trash_edge_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("TEDG", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)
    await _as_admin_aal2(api_env, admin)

    # 1. Unknown kind returns empty list
    r_unknown_kind = await client.get("/api/v1/admin/trash?kind=unknown_kind_xyz")
    assert r_unknown_kind.status_code == 200
    assert r_unknown_kind.json()["items"] == []

    # 2. Search query filter
    r_q_empty = await client.get("/api/v1/admin/trash?q=nonexistent_token_12345")
    assert r_q_empty.status_code == 200
    assert r_q_empty.json()["items"] == []

    # 3. Project ID filter
    r_proj = await client.get(f"/api/v1/admin/trash?project_id={proj_id}")
    assert r_proj.status_code == 200

    # 4. Member user without admin projects is forbidden
    member = await make_user("plain_trash_member", workspace_role="WORKSPACE_MEMBER")
    client_member = as_principal(member)
    r_member_empty = await client_member.get("/api/v1/admin/trash")
    assert r_member_empty.status_code == 403

    # 5. Project admin querying an unmanaged project
    proj_other = await make_project("NOTM", created_by=admin)
    proj_admin_user = await make_user("only_proj_admin", workspace_role="WORKSPACE_MEMBER")
    await api_env.seed.execute(
        text(
            "INSERT INTO role_bindings (principal_id, workspace_id, role, scope_type, project_id) "
            "VALUES (:uid, :ws, 'PROJECT_ADMIN', 'project', :pid)"
        ),
        {"uid": proj_admin_user.id, "ws": api_env.workspace_id, "pid": proj_id},
    )
    await api_env.seed.commit()
    client_padmin = as_principal(proj_admin_user)
    await _as_admin_aal2(api_env, proj_admin_user)
    r_unmanaged = await client_padmin.get(f"/api/v1/admin/trash?project_id={proj_other}")
    assert r_unmanaged.status_code == 200
    assert r_unmanaged.json()["items"] == []

    # 6. Test soft_trash request and execute through REST endpoints
    client = as_principal(admin)
    await _as_admin_aal2(api_env, admin)
    r_iss = await client.post("/api/v1/projects/TEDG/issues", json={"summary": "To Be Trashed"})
    assert r_iss.status_code == 201
    iss_key = r_iss.json()["key"]

    r_req = await client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": iss_key, "mode": "trash"},
    )
    assert r_req.status_code == 200
    req_data = r_req.json()
    token = req_data["confirmation_token"]
    phrase = req_data["confirm_phrase"]

    r_exec = await client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": iss_key,
            "mode": "trash",
            "confirmation_token": token,
            "confirm_phrase": phrase,
            "reason": "Test soft trash",
        },
    )
    assert r_exec.status_code == 200


