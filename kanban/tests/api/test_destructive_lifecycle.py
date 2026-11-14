# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Feature unit tests for two-stage destructive lifecycle REST API (KB-P4-12, S11.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
import uuid

import pytest
from sqlalchemy import select, text

from database.models import (
    ActivityRecord,
    Issue,
    LinkKind,
    ObjectKind,
    ObjectLink,
    ObjectRecord,
)
from database.models.destructive_token import DestructiveConfirmationToken
from database.models.knowledge import Doc, Page
from database.models.projects import Module
from kanban.services.destructive_lifecycle import compute_object_blast_radius
from kanban.tests.security.helpers import (
    add_role_binding,
    create_registered_object,
    rebuild_era,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


async def _enroll_totp(session: AsyncSession, p_id: uuid.UUID) -> None:
    """Enroll and confirm active TOTP factor to satisfy require_admin_aal2."""
    await session.execute(
        text("SELECT kb_auth.totp_enroll(:p_id, :blob, :dek, 'kek-v1')"),
        {
            "p_id": p_id,
            "blob": b"\x01" + b"\x00" * 28,
            "dek": b"\x01" + b"\x00" * 44,
        },
    )
    res = await session.execute(
        text("SELECT id FROM kb_auth.totp_get_pending(:p_id)"),
        {"p_id": p_id},
    )
    p_row = res.mappings().first()
    if p_row:
        await session.execute(
            text("SELECT kb_auth.totp_confirm(:p_fid, 100)"),
            {"p_fid": p_row["id"]},
        )
    await session.commit()


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
    """Create an ACTIVE object_link directly in seed session."""
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


async def test_case_1_positive_issue_trash_and_restore(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
) -> None:
    """Case 1a: request_delete(trash) -> execute_delete -> soft-trashed -> restore."""
    admin = await make_user("dest_admin", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin.id)
    await make_project("DEST", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin, aal_level=2)

    # 1. Create parent issue + 2 children + 3 inbound linked issues
    res_parent = await client.post(
        "/api/v1/projects/DEST/issues",
        json={"summary": "Parent Issue", "description_markdown": "Test parent"},
    )
    assert res_parent.status_code == 201
    parent_key = res_parent.json()["key"]
    parent_id = uuid.UUID(res_parent.json()["id"])

    res_c1 = await client.post(
        "/api/v1/projects/DEST/issues",
        json={"summary": "Child 1", "parent": parent_key},
    )
    res_c2 = await client.post(
        "/api/v1/projects/DEST/issues",
        json={"summary": "Child 2", "parent": parent_key},
    )
    assert res_c1.status_code == 201
    assert res_c2.status_code == 201
    c1_id = uuid.UUID(res_c1.json()["id"])
    c2_id = uuid.UUID(res_c2.json()["id"])

    inbound_ids: list[uuid.UUID] = []
    inbound_keys: list[str] = []
    for i in range(3):
        r = await client.post(
            "/api/v1/projects/DEST/issues",
            json={"summary": f"Inbound {i + 1}"},
        )
        assert r.status_code == 201
        inbound_ids.append(uuid.UUID(r.json()["id"]))
        inbound_keys.append(r.json()["key"])

    for sid, skey in zip(inbound_ids, inbound_keys, strict=True):
        await _make_link(
            api_env.seed,
            api_env.workspace_id,
            source_id=sid,
            source_key=skey,
            target_id=parent_id,
            target_key=parent_key,
            creator_id=admin.id,
        )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # 2. Stage 1: request_delete
    req_resp = await client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": parent_key, "mode": "trash"},
    )
    contract_recorder.record("destructive_request_200", req_resp.request, req_resp)
    assert req_resp.status_code == 200
    req_data = req_resp.json()
    assert req_data["stage"] == "confirmation_required"
    assert req_data["target"] == parent_key
    assert req_data["target_kind"] == "issue"
    assert req_data["mode"] == "trash"
    assert req_data["confirm_phrase"] == f"TRASH ISSUE {parent_key}"
    assert "2 sub-issues unparented, 3 inbound object_links flagged" in req_data["blast_summary"]
    token = req_data["confirmation_token"]
    assert token.startswith("kb_del_")
    assert req_data["expires_in_sec"] == 300

    # 3. Stage 2: execute_delete
    exec_resp = await client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": parent_key,
            "mode": "trash",
            "confirmation_token": token,
            "confirm_phrase": f"TRASH ISSUE {parent_key}",
            "reason": "Decommissioning old epic for Wave 21 migration",
        },
    )
    contract_recorder.record("destructive_execute_200", exec_resp.request, exec_resp)
    assert exec_resp.status_code == 200
    exec_data = exec_resp.json()
    assert exec_data["status"] == "executed"
    assert exec_data["target"] == parent_key

    # Check soft-deleted
    obj_row = await api_env.seed.get(ObjectRecord, parent_id)
    assert obj_row is not None
    assert obj_row.deleted_at is not None

    # Check sub-issues unparented
    c1_row = await api_env.seed.get(Issue, c1_id)
    c2_row = await api_env.seed.get(Issue, c2_id)
    assert c1_row is not None and c1_row.parent_issue_id is None
    assert c2_row is not None and c2_row.parent_issue_id is None

    # 4. Restore: restore_object
    rest_resp = await client.post(
        "/api/v1/admin/destructive:restore",
        json={
            "target_kind": "issue",
            "target": parent_key,
            "reason": "Accidental deletion restored by audit team",
        },
    )
    contract_recorder.record("destructive_restore_200", rest_resp.request, rest_resp)
    assert rest_resp.status_code == 200
    assert rest_resp.json()["status"] == "restored"

    # Check restored
    await api_env.seed.refresh(obj_row)
    assert obj_row.deleted_at is None


async def test_case_1b_positive_permanent_purge(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 1b: Server Admin permanently purges soft-trashed issue with link audit & purge."""
    s_admin = await make_user("s_admin")
    await _enroll_totp(api_env.seed, s_admin.id)
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="SERVER_ADMIN",
        scope_type="server",
    )
    await make_project("PURG", created_by=s_admin, roles={s_admin: "PROJECT_ADMIN"})
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()
    client = as_principal(s_admin, aal_level=2)

    # 1. Create target issue + 1 link
    res_iss = await client.post(
        "/api/v1/projects/PURG/issues",
        json={"summary": "Issue to Purge"},
    )
    assert res_iss.status_code == 201
    iss_key = res_iss.json()["key"]
    iss_id = uuid.UUID(res_iss.json()["id"])

    res_link = await client.post(
        "/api/v1/projects/PURG/issues",
        json={"summary": "Linked issue"},
    )
    assert res_link.status_code == 201
    other_id = uuid.UUID(res_link.json()["id"])
    other_key = res_link.json()["key"]

    await _make_link(
        api_env.seed,
        api_env.workspace_id,
        source_id=other_id,
        source_key=other_key,
        target_id=iss_id,
        target_key=iss_key,
        creator_id=s_admin.id,
    )

    # Move to trash first
    req1 = await client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": iss_key, "mode": "trash"},
    )
    assert req1.status_code == 200
    tok1 = req1.json()["confirmation_token"]
    ex1 = await client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": iss_key,
            "mode": "trash",
            "confirmation_token": tok1,
            "confirm_phrase": f"TRASH ISSUE {iss_key}",
            "reason": "Moving to soft-trash before purge",
        },
    )
    assert ex1.status_code == 200

    # Permanent purge request
    req_purge = await client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": iss_key, "mode": "permanent_purge"},
    )
    assert req_purge.status_code == 200
    purge_data = req_purge.json()
    assert purge_data["mode"] == "permanent_purge"
    assert purge_data["confirm_phrase"] == f"PURGE ISSUE {iss_key}"
    purge_tok = purge_data["confirmation_token"]

    # Permanent purge execute
    exec_purge = await client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": iss_key,
            "mode": "permanent_purge",
            "confirmation_token": purge_tok,
            "confirm_phrase": f"PURGE ISSUE {iss_key}",
            "reason": "Permanent audited purge of decommissioned issue",
        },
    )
    assert exec_purge.status_code == 200
    assert exec_purge.json()["status"] == "executed"

    # Verify completely deleted from issues and objects
    obj_chk = await api_env.seed.get(ObjectRecord, iss_id)
    assert obj_chk is None
    iss_chk = await api_env.seed.get(Issue, iss_id)
    assert iss_chk is None

    # Verify activity record DESTRUCTIVE_LIFECYCLE_EXECUTED
    act_res = await api_env.seed.execute(
        select(ActivityRecord).where(
            ActivityRecord.event_type == "DESTRUCTIVE_LIFECYCLE_EXECUTED"
        )
    )
    records = list(act_res.scalars().all())
    assert len(records) >= 2


async def test_case_1c_page_subtree_and_module(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 1c: Two-stage delete of page subtree and module."""
    s_admin = await make_user("mod_admin")
    await _enroll_totp(api_env.seed, s_admin.id)
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        s_admin.id,
        role="SERVER_ADMIN",
        scope_type="server",
    )
    proj_id = await make_project("TREE", created_by=s_admin, roles={s_admin: "PROJECT_ADMIN"})
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()
    client = as_principal(s_admin, aal_level=2)

    # 1. Create Doc + Parent Page + Child Page
    doc_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="doc",
        key="DocTree",
        title="DocTree",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    doc = Doc(
        id=doc_id,
        workspace_id=api_env.workspace_id,
        project_id=proj_id,
        title="DocTree",
        body_markdown="Doc body",
        hierarchy_path="tree",
    )
    api_env.seed.add(doc)

    parent_page_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="page",
        key="ParentPage",
        title="ParentPage",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    p_page = Page(
        id=parent_page_id,
        workspace_id=api_env.workspace_id,
        doc_id=doc_id,
        title="ParentPage",
        body_markdown="Parent page body",
        hierarchy_path="tree.parent",
    )
    api_env.seed.add(p_page)

    child_page_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="page",
        key="ChildPage",
        title="ChildPage",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    c_page = Page(
        id=child_page_id,
        workspace_id=api_env.workspace_id,
        doc_id=doc_id,
        parent_page_id=parent_page_id,
        title="ChildPage",
        body_markdown="Child page body",
        hierarchy_path="tree.parent.child",
    )
    api_env.seed.add(c_page)
    await api_env.seed.commit()

    # Request delete parent page (trash)
    req_page = await client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "page", "target": str(parent_page_id), "mode": "trash"},
    )
    assert req_page.status_code == 200
    page_tok = req_page.json()["confirmation_token"]

    exec_page = await client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "page",
            "target": str(parent_page_id),
            "mode": "trash",
            "confirmation_token": page_tok,
            "confirm_phrase": req_page.json()["confirm_phrase"],
            "reason": "Removing outdated documentation page hierarchy",
        },
    )
    assert exec_page.status_code == 200

    # Verify both parent and child page are soft-deleted
    p_obj = await api_env.seed.get(ObjectRecord, parent_page_id)
    c_obj = await api_env.seed.get(ObjectRecord, child_page_id)
    assert p_obj is not None and p_obj.deleted_at is not None
    assert c_obj is not None and c_obj.deleted_at is not None

    # 2. Module two-stage permanent purge
    mod_id = await create_registered_object(
        api_env.seed,
        api_env.workspace_id,
        kind="module",
        key="ModAlpha",
        title="ModAlpha",
        project_id=proj_id,
        created_by_id=s_admin.id,
    )
    mod = Module(
        id=mod_id,
        workspace_id=api_env.workspace_id,
        project_id=proj_id,
        name="ModAlpha",
    )
    api_env.seed.add(mod)
    await api_env.seed.commit()

    req_mod = await client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "module", "target": "ModAlpha", "mode": "permanent_purge"},
    )
    assert req_mod.status_code == 200
    mod_tok = req_mod.json()["confirmation_token"]

    exec_mod = await client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "module",
            "target": "ModAlpha",
            "mode": "permanent_purge",
            "confirmation_token": mod_tok,
            "confirm_phrase": req_mod.json()["confirm_phrase"],
            "reason": "Decommissioning completed project module",
        },
    )
    assert exec_mod.status_code == 200
    mod_chk = await api_env.seed.get(ObjectRecord, mod_id)
    assert mod_chk is None


async def test_case_2_replay_expiry_and_binding_security(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 2: Replay, expiry, caller mismatch, target mismatch, phrase mismatch fail-closed."""
    admin_a = await make_user("admin_a", workspace_role="WORKSPACE_ADMIN")
    admin_b = await make_user("admin_b", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin_a.id)
    await _enroll_totp(api_env.seed, admin_b.id)
    await make_project("SEC", created_by=admin_a, roles={admin_a: "PROJECT_ADMIN", admin_b: "PROJECT_ADMIN"})
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # Create 2 issues as Admin A
    as_principal(admin_a, aal_level=2)
    r1 = await api_env.client.post("/api/v1/projects/SEC/issues", json={"summary": "Issue 1"})
    r2 = await api_env.client.post("/api/v1/projects/SEC/issues", json={"summary": "Issue 2"})
    key1 = r1.json()["key"]
    key2 = r2.json()["key"]

    # Request token for issue 1 as Admin A
    as_principal(admin_a, aal_level=2)
    req1 = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": key1, "mode": "trash"},
    )
    assert req1.status_code == 200
    token1 = req1.json()["confirmation_token"]
    phrase1 = req1.json()["confirm_phrase"]

    # 1. Admin B attempts to execute Admin A's token -> 403 TOKEN_CALLER_MISMATCH
    as_principal(admin_b, aal_level=2)
    res_b = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": key1,
            "mode": "trash",
            "confirmation_token": token1,
            "confirm_phrase": phrase1,
            "reason": "Attempt by non-authorized caller to consume token",
        },
    )
    assert res_b.status_code == 403
    assert res_b.json()["code"] == "TOKEN_CALLER_MISMATCH"

    # Token must now be burned! Admin A retrying same token -> 409 CONFIRMATION_TOKEN_INVALID_OR_EXPIRED
    as_principal(admin_a, aal_level=2)
    res_burned = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": key1,
            "mode": "trash",
            "confirmation_token": token1,
            "confirm_phrase": phrase1,
            "reason": "Attempt to reuse burned token by legitimate admin",
        },
    )
    assert res_burned.status_code == 409
    assert res_burned.json()["code"] == "CONFIRMATION_TOKEN_INVALID_OR_EXPIRED"

    # 2. Target mismatch: token minted for key1, passed with target=key2
    as_principal(admin_a, aal_level=2)
    req2 = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": key1, "mode": "trash"},
    )
    token2 = req2.json()["confirmation_token"]
    phrase2 = req2.json()["confirm_phrase"]

    res_target_mismatch = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": key2,  # Target swapped!
            "mode": "trash",
            "confirmation_token": token2,
            "confirm_phrase": phrase2,
            "reason": "Swapping target to unauthorized item",
        },
    )
    assert res_target_mismatch.status_code == 409
    assert res_target_mismatch.json()["code"] == "TOKEN_TARGET_MISMATCH"

    # 3. Wrong confirm_phrase -> 422 CONFIRM_PHRASE_MISMATCH & token burned
    as_principal(admin_a, aal_level=2)
    req3 = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": key1, "mode": "trash"},
    )
    token3 = req3.json()["confirmation_token"]

    res_wrong_phrase = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": key1,
            "mode": "trash",
            "confirmation_token": token3,
            "confirm_phrase": f"DELETE ISSUE {key1}",  # Wrong verb!
            "reason": "Wrong confirmation phrase supplied",
        },
    )
    assert res_wrong_phrase.status_code == 422
    assert res_wrong_phrase.json()["code"] == "CONFIRM_PHRASE_MISMATCH"

    # 4. Token replay: valid execution then immediate replay
    as_principal(admin_a, aal_level=2)
    req4 = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": key1, "mode": "trash"},
    )
    token4 = req4.json()["confirmation_token"]
    phrase4 = req4.json()["confirm_phrase"]

    res_ok = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": key1,
            "mode": "trash",
            "confirmation_token": token4,
            "confirm_phrase": phrase4,
            "reason": "Legitimate soft-trash execution",
        },
    )
    assert res_ok.status_code == 200

    res_replay = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": key1,
            "mode": "trash",
            "confirmation_token": token4,
            "confirm_phrase": phrase4,
            "reason": "Replaying previously consumed confirmation token",
        },
    )
    assert res_replay.status_code == 409
    assert res_replay.json()["code"] == "CONFIRMATION_TOKEN_INVALID_OR_EXPIRED"

    # 5. Token expiry (advancing expires_at backwards in DB)
    as_principal(admin_a, aal_level=2)
    req5 = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": key2, "mode": "trash"},
    )
    token5 = req5.json()["confirmation_token"]
    phrase5 = req5.json()["confirm_phrase"]

    await api_env.seed.execute(
        text(
            "UPDATE destructive_confirmation_tokens "
            "SET expires_at = clock_timestamp() - interval '10 seconds' "
            "WHERE target_object_id = (SELECT id FROM issues WHERE project_id = (SELECT id FROM projects WHERE identifier = 'SEC') AND sequence_id = 2)"
        )
    )
    await api_env.seed.commit()

    res_expired = await api_env.client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": key2,
            "mode": "trash",
            "confirmation_token": token5,
            "confirm_phrase": phrase5,
            "reason": "Attempting to execute expired confirmation token",
        },
    )
    assert res_expired.status_code == 409
    assert res_expired.json()["code"] == "CONFIRMATION_TOKEN_INVALID_OR_EXPIRED"


async def test_case_3_blast_hash_toctou_protection(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 3: Concurrently attaching a new child issue or link triggers 412 BLAST_RADIUS_CHANGED."""
    admin = await make_user("toctou_admin", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin.id)
    await make_project("TOCT", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()
    client = as_principal(admin, aal_level=2)

    r_parent = await client.post("/api/v1/projects/TOCT/issues", json={"summary": "Parent TOCTOU"})
    parent_key = r_parent.json()["key"]
    parent_id = uuid.UUID(r_parent.json()["id"])

    # Stage 1: Request delete
    req = await client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": parent_key, "mode": "trash"},
    )
    assert req.status_code == 200
    token = req.json()["confirmation_token"]
    phrase = req.json()["confirm_phrase"]

    # Concurrently add child issue to parent!
    r_child = await client.post(
        "/api/v1/projects/TOCT/issues",
        json={"summary": "Concurrent child issue", "parent": parent_key},
    )
    assert r_child.status_code == 201

    # Stage 2: Execute delete -> 412 BLAST_RADIUS_CHANGED
    res_exec = await client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": parent_key,
            "mode": "trash",
            "confirmation_token": token,
            "confirm_phrase": phrase,
            "reason": "Executing delete while blast radius changed",
        },
    )
    assert res_exec.status_code == 412
    assert res_exec.json()["code"] == "BLAST_RADIUS_CHANGED"

    # Verify parent issue was left completely untouched
    obj_row = await api_env.seed.get(ObjectRecord, parent_id)
    assert obj_row is not None
    assert obj_row.deleted_at is None


async def test_case_4_role_and_scope_gates(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Case 4: AAL1 rejection, non-server-admin permanent purge, and soft-trash required."""
    admin = await make_user("gate_admin", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin.id)
    await make_project("GATE", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # Create active issue in GATE
    as_principal(admin, aal_level=2)
    r_iss = await api_env.client.post("/api/v1/projects/GATE/issues", json={"summary": "Gate Issue"})
    assert r_iss.status_code == 201
    gate_key = r_iss.json()["key"]

    # 1. AAL1 token -> 403 AAL2_REQUIRED
    as_principal(admin, aal_level=1)
    res_aal1 = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": gate_key, "mode": "trash"},
    )
    assert res_aal1.status_code == 403

    as_principal(admin, aal_level=2)

    # 2. Permanent purge requested by WORKSPACE_ADMIN (not SERVER_ADMIN) -> 403 SERVER_ADMIN_REQUIRED
    res_srv = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": gate_key, "mode": "permanent_purge"},
    )
    assert res_srv.status_code == 403
    assert res_srv.json()["code"] == "SERVER_ADMIN_REQUIRED"

    # Now make admin a SERVER_ADMIN
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        admin.id,
        role="SERVER_ADMIN",
        scope_type="server",
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()

    # 3. Permanent purge on active non-trashed issue -> 409 SOFT_TRASH_REQUIRED_FIRST
    as_principal(admin, aal_level=2)
    res_not_trashed = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": gate_key, "mode": "permanent_purge"},
    )
    assert res_not_trashed.status_code == 409
    assert res_not_trashed.json()["code"] == "SOFT_TRASH_REQUIRED_FIRST"

    # 4. Requesting trash mode on module -> 422 VALIDATION_FAILED
    as_principal(admin, aal_level=2)
    res_mod_trash = await api_env.client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "module", "target": "ModX", "mode": "trash"},
    )
    assert res_mod_trash.status_code == 422
    assert "do not support soft-trash" in res_mod_trash.json()["detail"]
