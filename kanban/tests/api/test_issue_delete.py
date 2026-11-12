"""Unit tests for issue delete preview, soft trash, and restore endpoints (S7.2 8q; KB-P3-09b)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text

from database.models import (
    ActivityRecord,
    Issue,
    LinkKind,
    ObjectKind,
    ObjectLink,
)
from kanban.api.problems import ProblemException
from kanban.services.issue_delete import compute_blast_radius
from kanban.settings import Settings
from kanban.tests.security.helpers import (
    add_acl_entry,
    add_role_binding,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def _make_link(  # noqa: PLR0913, PLR0917
    seed: AsyncSession,
    ws_id: uuid.UUID,
    source_id: uuid.UUID,
    source_key: str,
    target_id: uuid.UUID,
    target_key: str,
    creator_id: uuid.UUID,
    link_type: LinkKind = LinkKind.RELATES_TO,
) -> uuid.UUID:
    """Create an ACTIVE object_link directly in the seed session."""
    link_id = uuid.uuid4()
    link = ObjectLink(
        id=link_id,
        workspace_id=ws_id,
        source_id=source_id,
        source_type=ObjectKind.ISSUE,
        target_id=target_id,
        target_type=ObjectKind.ISSUE,
        link_type=link_type,
        link_state="ACTIVE",
        source_key_snapshot=source_key,
        target_key_snapshot=target_key,
        created_by_id=creator_id,
    )
    seed.add(link)
    await seed.commit()
    return link_id


async def test_case_1_positive_delete_preview_and_soft_trash(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1: Positive delete preview returns counts and hash; DELETE soft-trashes."""
    admin = await make_user("del_admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("DEL", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Create target parent issue
    resp_parent = await client.post(
        "/api/v1/projects/DEL/issues",
        json={"summary": "Parent Issue to Delete", "description_markdown": "Parent description"},
    )
    assert resp_parent.status_code == 201
    parent_key = resp_parent.json()["key"]
    parent_id = uuid.UUID(resp_parent.json()["id"])

    # 2. Create 2 child issues
    resp_c1 = await client.post(
        "/api/v1/projects/DEL/issues",
        json={"summary": "Child 1", "parent": parent_key},
    )
    assert resp_c1.status_code == 201
    child1_id = uuid.UUID(resp_c1.json()["id"])

    resp_c2 = await client.post(
        "/api/v1/projects/DEL/issues",
        json={"summary": "Child 2", "parent": parent_key},
    )
    assert resp_c2.status_code == 201
    child2_id = uuid.UUID(resp_c2.json()["id"])

    # 3. Create 3 other issues to form inbound links
    inbound_keys: list[str] = []
    inbound_ids: list[uuid.UUID] = []
    for i in range(3):
        r = await client.post(
            "/api/v1/projects/DEL/issues",
            json={"summary": f"Inbound Source {i + 1}"},
        )
        assert r.status_code == 201
        inbound_keys.append(r.json()["key"])
        inbound_ids.append(uuid.UUID(r.json()["id"]))

    for src_id, src_key in zip(inbound_ids, inbound_keys, strict=True):
        await _make_link(
            seed=api_env.seed,
            ws_id=api_env.workspace_id,
            source_id=src_id,
            source_key=src_key,
            target_id=parent_id,
            target_key=parent_key,
            creator_id=admin.id,
        )

    # 4. GET /api/v1/issues/{issue_ref}/delete-preview
    preview_resp = await client.get(f"/api/v1/issues/{parent_key}/delete-preview")
    contract_recorder.record("get_delete_preview_200", preview_resp.request, preview_resp)
    assert preview_resp.status_code == 200
    preview_data = preview_resp.json()
    assert preview_data["issue_key"] == parent_key
    assert preview_data["sub_issues_unparented"] == 2
    assert preview_data["inbound_links_flagged"] == 3
    assert preview_data["outbound_links"] == 0
    assert preview_data["summary_text"] == "2 sub-issues unparented, 3 inbound object_links flagged"
    blast_hash = preview_data["blast_hash"]
    assert len(blast_hash) == 64
    assert preview_data["retention_days"] == 30

    # 5. DELETE /api/v1/issues/{issue_ref} with Kb-Blast-Hash header
    delete_resp = await client.delete(
        f"/api/v1/issues/{parent_key}",
        headers={"Kb-Blast-Hash": blast_hash},
    )
    contract_recorder.record("delete_issue_200", delete_resp.request, delete_resp)
    assert delete_resp.status_code == 200
    del_data = delete_resp.json()
    assert del_data["issue_key"] == parent_key
    assert del_data["deleted_at"] is not None
    assert del_data["purge_after"] is not None

    # 6. Verify children unparented (parent_issue_id = NULL)
    await api_env.seed.rollback()
    c1_row = (
        await api_env.seed.execute(select(Issue.parent_issue_id).where(Issue.id == child1_id))
    ).scalar_one_or_none()
    c2_row = (
        await api_env.seed.execute(select(Issue.parent_issue_id).where(Issue.id == child2_id))
    ).scalar_one_or_none()
    assert c1_row is None
    assert c2_row is None

    # 7. Verify ISSUE_TRASHED activity record
    act_row = (
        await api_env.seed.execute(
            select(ActivityRecord.payload).where(
                ActivityRecord.object_id == parent_id,
                ActivityRecord.event_type == "ISSUE_TRASHED",
            )
        )
    ).scalar_one_or_none()
    assert act_row is not None
    assert act_row["blast_hash"] == blast_hash
    assert str(child1_id) in act_row["unparented_child_ids"]
    assert str(child2_id) in act_row["unparented_child_ids"]
    assert act_row["inbound_links_flagged"] == 3

    # 8. Verify issue appears in trash
    trash_resp = await client.get("/api/v1/projects/DEL/trash")
    contract_recorder.record("list_trash_200", trash_resp.request, trash_resp)
    assert trash_resp.status_code == 200
    trash_data = trash_resp.json()
    trash_keys = [item["key"] for item in trash_data["items"]]
    assert parent_key in trash_keys

    # 9. Verify normal read paths 404 on deleted issue
    get_resp = await client.get(f"/api/v1/issues/{parent_key}")
    assert get_resp.status_code == 404


async def test_case_2_concurrency_and_missing_hash(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 2: 428 on missing hash; 412 with fresh current_preview on concurrency blast change."""
    admin = await make_user("cnc_admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("CNC", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Create issue
    resp = await client.post(
        "/api/v1/projects/CNC/issues",
        json={"summary": "Concurrency Target"},
    )
    assert resp.status_code == 201
    target_key = resp.json()["key"]
    target_id = uuid.UUID(resp.json()["id"])

    # 2. Add 3 inbound links
    link_sources: list[uuid.UUID] = []
    link_keys: list[str] = []
    for i in range(3):
        r = await client.post(
            "/api/v1/projects/CNC/issues",
            json={"summary": f"CNC Source {i + 1}"},
        )
        assert r.status_code == 201
        link_keys.append(r.json()["key"])
        link_sources.append(uuid.UUID(r.json()["id"]))

    for src_id, src_key in zip(link_sources, link_keys, strict=True):
        await _make_link(
            seed=api_env.seed,
            ws_id=api_env.workspace_id,
            source_id=src_id,
            source_key=src_key,
            target_id=target_id,
            target_key=target_key,
            creator_id=admin.id,
        )

    # 3. Missing header returns 428 BLAST_HASH_REQUIRED
    missing_resp = await client.delete(f"/api/v1/issues/{target_key}")
    contract_recorder.record("delete_missing_hash_428", missing_resp.request, missing_resp)
    assert missing_resp.status_code == 428
    assert missing_resp.json()["code"] == "BLAST_HASH_REQUIRED"

    # 4. Generate preview with 3 inbound links
    preview_resp = await client.get(f"/api/v1/issues/{target_key}/delete-preview")
    assert preview_resp.status_code == 200
    stale_hash = preview_resp.json()["blast_hash"]
    assert preview_resp.json()["inbound_links_flagged"] == 3

    # 5. Add 4th inbound link concurrently
    r4 = await client.post(
        "/api/v1/projects/CNC/issues",
        json={"summary": "CNC Source 4"},
    )
    assert r4.status_code == 201
    await _make_link(
        seed=api_env.seed,
        ws_id=api_env.workspace_id,
        source_id=uuid.UUID(r4.json()["id"]),
        source_key=r4.json()["key"],
        target_id=target_id,
        target_key=target_key,
        creator_id=admin.id,
    )

    # 6. DELETE with stale blast hash returns 412 BLAST_RADIUS_CHANGED
    mismatch_resp = await client.delete(
        f"/api/v1/issues/{target_key}",
        headers={"Kb-Blast-Hash": stale_hash},
    )
    contract_recorder.record(
        "delete_blast_radius_changed_412", mismatch_resp.request, mismatch_resp
    )
    assert mismatch_resp.status_code == 412
    err_body = mismatch_resp.json()
    assert err_body["code"] == "BLAST_RADIUS_CHANGED"
    assert "current_preview" in err_body
    assert err_body["current_preview"]["inbound_links_flagged"] == 4


async def test_case_3_security_non_viewer_and_edit_only_and_masked_child(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 3: Non-viewer 404, edit-only 403, and masked child in preview."""
    admin = await make_user("sec_admin", workspace_role="WORKSPACE_ADMIN")
    editor = await make_user("sec_editor")
    deleter = await make_user("sec_deleter")
    outsider = await make_user("sec_outsider")

    proj_pub_id = await make_project("SECPUB", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    await make_project("SECSEC", created_by=admin, roles={admin: "PROJECT_ADMIN"})

    # Grant editor only MEMBER (EDIT capability, but not DELETE or PROJECT_ADMIN) on SECPUB
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        editor.id,
        role="MEMBER",
        scope_type="project",
        project_id=proj_pub_id,
    )
    # Grant deleter PROJECT_ADMIN on SECPUB (DELETE capability)
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        deleter.id,
        role="PROJECT_ADMIN",
        scope_type="project",
        project_id=proj_pub_id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # Admin creates issue in SECPUB
    client_admin = as_principal(admin)
    resp_pub = await client_admin.post(
        "/api/v1/projects/SECPUB/issues",
        json={"summary": "Public Issue with Secret Child"},
    )
    assert resp_pub.status_code == 201
    pub_key = resp_pub.json()["key"]
    pub_id = uuid.UUID(resp_pub.json()["id"])

    # Admin creates child issue in SECPUB
    resp_child = await client_admin.post(
        "/api/v1/projects/SECPUB/issues",
        json={"summary": "Confidential Child", "parent": pub_key},
    )
    assert resp_child.status_code == 201
    sec_child_key = resp_child.json()["key"]
    child_id = uuid.UUID(resp_child.json()["id"])

    # Add explicit DENY VIEW ACL on child issue for deleter
    await add_acl_entry(
        api_env.seed,
        api_env.workspace_id,
        child_id,
        deleter.id,
        effect="DENY",
        capability_mask=1,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # Verify deleter CANNOT view confidential child (404 NOT_FOUND)
    client_deleter = as_principal(deleter)
    r_child_denied = await client_deleter.get(f"/api/v1/issues/{sec_child_key}")
    assert r_child_denied.status_code == 404

    # 1. Non-viewer preview -> 404 NOT_FOUND
    client_outsider = as_principal(outsider)
    r_unreadable = await client_outsider.get(f"/api/v1/issues/{pub_key}/delete-preview")
    assert r_unreadable.status_code == 404
    assert r_unreadable.json()["code"] == "NOT_FOUND"

    # 2. EDIT-only user DELETE -> 403 INSUFFICIENT_CAPABILITY
    client_editor = as_principal(editor)
    r_edit_delete = await client_editor.delete(
        f"/api/v1/issues/{pub_key}",
        headers={"Kb-Blast-Hash": "a" * 64},
    )
    assert r_edit_delete.status_code == 403
    assert r_edit_delete.json()["code"] == "INSUFFICIENT_CAPABILITY"

    # 3. Deleter preview counts hidden child without leaking its key or identifiers
    client_deleter = as_principal(deleter)
    r_preview = await client_deleter.get(f"/api/v1/issues/{pub_key}/delete-preview")
    assert r_preview.status_code == 200
    p_data = r_preview.json()
    assert p_data["sub_issues_unparented"] == 1
    assert p_data["inbound_links_flagged"] == 0
    # Verify child key (e.g. SECPUB-2) is NEVER in the response body
    assert sec_child_key not in r_preview.text
    old_hash = p_data["blast_hash"]

    # 4. Add a hidden inbound link from SECSEC (which deleter cannot view) to pub_key
    resp_sec = await as_principal(admin).post(
        "/api/v1/projects/SECSEC/issues",
        json={"summary": "Secret Inbound Source Issue"},
    )
    assert resp_sec.status_code == 201
    sec_key = resp_sec.json()["key"]
    sec_id = uuid.UUID(resp_sec.json()["id"])

    await _make_link(
        api_env.seed,
        api_env.workspace_id,
        source_id=sec_id,
        source_key=sec_key,
        target_id=pub_id,
        target_key=pub_key,
        creator_id=admin.id,
    )

    # 5. Deleter preview again: inbound_links_flagged increases, blast_hash changes
    client_deleter = as_principal(deleter)
    r_preview2 = await client_deleter.get(f"/api/v1/issues/{pub_key}/delete-preview")
    assert r_preview2.status_code == 200
    p_data2 = r_preview2.json()
    assert p_data2["inbound_links_flagged"] == 1
    new_hash = p_data2["blast_hash"]
    assert new_hash != old_hash

    # 6. Attempt delete with old hash returns 412 BLAST_RADIUS_CHANGED with current_preview
    r_mismatch = await client_deleter.delete(
        f"/api/v1/issues/{pub_key}",
        headers={"Kb-Blast-Hash": old_hash},
    )
    assert r_mismatch.status_code == 412
    mismatch_body = r_mismatch.json()
    assert mismatch_body["code"] == "BLAST_RADIUS_CHANGED"
    assert mismatch_body["current_preview"]["blast_hash"] == new_hash

    # 7. Delete with new hash succeeds
    r_del = await client_deleter.delete(
        f"/api/v1/issues/{pub_key}",
        headers={"Kb-Blast-Hash": new_hash},
    )
    assert r_del.status_code == 200

    # 8. Verify child in DB was cleanly unparented (parent_issue_id is NULL)
    await api_env.seed.rollback()
    child_parent_row = (
        await api_env.seed.execute(select(Issue.parent_issue_id).where(Issue.id == child_id))
    ).scalar_one_or_none()
    assert child_parent_row is None


async def test_case_4_restore_and_retention_expired(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 4: Restore within retention succeeds with note; restore after expiration returns 409."""
    admin = await make_user("res_admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("RES", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Create parent issue and child
    resp_p = await client.post(
        "/api/v1/projects/RES/issues",
        json={"summary": "Restorable Parent"},
    )
    assert resp_p.status_code == 201
    p_key = resp_p.json()["key"]
    p_id = uuid.UUID(resp_p.json()["id"])

    resp_c = await client.post(
        "/api/v1/projects/RES/issues",
        json={"summary": "Child will unparent", "parent": p_key},
    )
    assert resp_c.status_code == 201
    c_id = uuid.UUID(resp_c.json()["id"])

    # 2. Attempt restore when not in trash -> 409 NOT_IN_TRASH
    r_not_trash = await client.post(f"/api/v1/issues/{p_key}/restore")
    assert r_not_trash.status_code == 409
    assert r_not_trash.json()["code"] == "NOT_IN_TRASH"

    # 3. Soft-delete issue
    p_preview = (await client.get(f"/api/v1/issues/{p_key}/delete-preview")).json()
    del_resp = await client.delete(
        f"/api/v1/issues/{p_key}",
        headers={"Kb-Blast-Hash": p_preview["blast_hash"]},
    )
    assert del_resp.status_code == 200

    # 4. Restore within retention -> 200 with note
    restore_resp = await client.post(f"/api/v1/issues/{p_key}/restore")
    contract_recorder.record("restore_issue_200", restore_resp.request, restore_resp)
    assert restore_resp.status_code == 200
    res_body = restore_resp.json()
    assert res_body["key"] == p_key
    assert res_body.get("note") == "sub-issues remain unparented"

    # Verify child remains unparented
    await api_env.seed.rollback()
    c_parent = (
        await api_env.seed.execute(select(Issue.parent_issue_id).where(Issue.id == c_id))
    ).scalar_one_or_none()
    assert c_parent is None

    # Verify ISSUE_RESTORED activity record
    act_res = (
        await api_env.seed.execute(
            select(ActivityRecord.event_type).where(
                ActivityRecord.object_id == p_id,
                ActivityRecord.event_type == "ISSUE_RESTORED",
            )
        )
    ).scalar_one_or_none()
    assert act_res == "ISSUE_RESTORED"

    # 5. Soft-delete again and advance deleted_at beyond retention window (31 days ago)
    p2_preview = (await client.get(f"/api/v1/issues/{p_key}/delete-preview")).json()
    await client.delete(
        f"/api/v1/issues/{p_key}",
        headers={"Kb-Blast-Hash": p2_preview["blast_hash"]},
    )

    expired_ts = datetime.now(UTC) - timedelta(days=31)
    await api_env.seed.execute(
        text("UPDATE objects SET deleted_at = :ts WHERE id = :oid"),
        {"ts": expired_ts, "oid": p_id},
    )
    await api_env.seed.commit()

    # 6. Attempt restore on expired issue -> 409 RETENTION_EXPIRED
    expired_resp = await client.post(f"/api/v1/issues/{p_key}/restore")
    contract_recorder.record("restore_retention_expired_409", expired_resp.request, expired_resp)
    assert expired_resp.status_code == 409
    assert expired_resp.json()["code"] == "RETENTION_EXPIRED"


def test_case_6_settings_retention_days_validation() -> None:
    """Case 6: Settings boundary validation for trash_retention_days."""
    # Valid boundaries: 1 and 365
    s1 = Settings(trash_retention_days=1)
    assert s1.trash_retention_days == 1

    s365 = Settings(trash_retention_days=365)
    assert s365.trash_retention_days == 365

    # Invalid values: 0 and 366
    with pytest.raises(ValidationError):
        Settings(trash_retention_days=0)

    with pytest.raises(ValidationError):
        Settings(trash_retention_days=366)


async def test_list_trash_pagination_and_filtering(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test trash list keyset pagination and filtering items without DELETE capability."""
    admin = await make_user("tr_admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("tr_member")
    proj_id = await make_project("TRSH", created_by=admin, roles={admin: "PROJECT_ADMIN"})

    # Grant member only VIEWER on TRSH
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        member.id,
        role="VIEWER",
        scope_type="project",
        project_id=proj_id,
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    client = as_principal(admin)
    # Create 3 issues and trash them
    keys = []
    for i in range(3):
        r = await client.post(
            "/api/v1/projects/TRSH/issues", json={"summary": f"Trash Item {i + 1}"}
        )
        assert r.status_code == 201
        keys.append(r.json()["key"])

    for k in keys:
        prev = (await client.get(f"/api/v1/issues/{k}/delete-preview")).json()
        del_r = await client.delete(
            f"/api/v1/issues/{k}", headers={"Kb-Blast-Hash": prev["blast_hash"]}
        )
        assert del_r.status_code == 200

    # 1. Page with limit=2
    p1 = await client.get("/api/v1/projects/TRSH/trash?limit=2")
    assert p1.status_code == 200
    d1 = p1.json()
    assert len(d1["items"]) == 2
    assert d1["next_cursor"] is not None

    # 2. Page 2 with cursor
    p2 = await client.get(f"/api/v1/projects/TRSH/trash?limit=2&cursor={d1['next_cursor']}")
    assert p2.status_code == 200
    d2 = p2.json()
    assert len(d2["items"]) == 1
    assert d2["next_cursor"] is None

    # 3. Member who lacks DELETE capability on issues sees empty list
    client_member = as_principal(member)
    p_mem = await client_member.get("/api/v1/projects/TRSH/trash")
    assert p_mem.status_code == 200
    assert len(p_mem.json()["items"]) == 0


async def test_compute_blast_radius_and_restore_error_branches(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Test 404 on missing/deleted issue in compute_blast_radius and restore."""
    admin = await make_user("err_admin", workspace_role="WORKSPACE_ADMIN")
    await make_project("ERR", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    # 1. Non-existent UUID in compute_blast_radius -> 404
    fake_id = uuid.uuid4()
    with pytest.raises(ProblemException) as exc_info:
        await compute_blast_radius(api_env.seed, fake_id)
    assert exc_info.value.status == 404

    # 2. Non-existent issue restore -> 404
    r_restore = await client.post("/api/v1/issues/ERR-99999/restore")
    assert r_restore.status_code == 404

    # 3. Soft-deleted issue in compute_blast_radius -> 404
    r = await client.post("/api/v1/projects/ERR/issues", json={"summary": "To Be Deleted"})
    assert r.status_code == 201
    err_key = r.json()["key"]
    err_id = uuid.UUID(r.json()["id"])

    prev = (await client.get(f"/api/v1/issues/{err_key}/delete-preview")).json()
    await client.delete(f"/api/v1/issues/{err_key}", headers={"Kb-Blast-Hash": prev["blast_hash"]})

    with pytest.raises(ProblemException) as exc_info2:
        await compute_blast_radius(api_env.seed, err_id)
    assert exc_info2.value.status == 404
