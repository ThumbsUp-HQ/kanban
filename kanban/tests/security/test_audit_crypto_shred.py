# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Security tests for AAL2 two-stage crypto-shredding and feed tombstones (KB-SEC-SHRED-01)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from database.models.activity import ActivityRecord
from database.models.activity_key import ActivityRecordKey
from kanban.services.activity import (
    ActivityEventType,
    record_activity,
)
from kanban.tests.security.helpers import add_role_binding, rebuild_era

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

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


@pytest.mark.asyncio
async def test_case_1_two_stage_crypto_shred_by_activity_id(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify record sealing, feed unwrapping, 2-stage shred, and tombstones."""
    admin = await make_user("shred_admin_1", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin.id)
    await make_project("SHR1", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin, aal_level=2)

    # 1. Create issue
    res_issue = await client.post(
        "/api/v1/projects/SHR1/issues",
        json={"summary": "Secret Leak Issue", "description_markdown": "Initial content"},
    )
    assert res_issue.status_code == 201
    issue_data = res_issue.json()
    issue_id = uuid.UUID(issue_data["id"])
    issue_key = issue_data["key"]

    # 2. Record an envelope-encrypted activity record with sensitive secret
    act_id = await record_activity(
        session=api_env.seed,
        workspace_id=admin.workspace_id,
        object_id=issue_id,
        actor_principal_id=admin.id,
        event_type=ActivityEventType.ISSUE_FIELD_CHANGED,
        payload={"sensitive_token": "secret-leaked-token-xyz-12345", "field": "internal_token"},
        encrypt_payload=True,
    )
    await api_env.seed.commit()

    # 3. Read activity feed before shredding: payload must be decrypted and readable
    feed_res = await client.get(f"/api/v1/issues/{issue_key}/activity?tab=all")
    assert feed_res.status_code == 200
    feed_items = feed_res.json()["items"]
    target_item = next((item for item in feed_items if item["id"] == str(act_id)), None)
    assert target_item is not None
    assert target_item["payload"].get("sensitive_token") == "secret-leaked-token-xyz-12345"

    # Verify initial hash chain
    chain_chk = await api_env.seed.execute(
        text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws)"),
        {"ws": admin.workspace_id},
    )
    assert chain_chk.mappings().one()["is_valid"] is True

    # 4. Stage 1: Request crypto-shred for this specific activity_id
    req_res = await client.post(
        "/api/v1/admin/audit-ledger/request-shred",
        json={"activity_id": str(act_id), "reason": "Secret spill containment protocol"},
    )
    assert req_res.status_code == 200
    req_data = req_res.json()
    assert req_data["stage"] == "confirmation_required"
    assert req_data["target_type"] == "activity_id"
    assert req_data["target_id"] == str(act_id)
    assert req_data["records_to_shred"] == 1
    conf_token = req_data["confirmation_token"]
    conf_phrase = req_data["confirm_phrase"]

    # 5. Stage 2: Execute crypto-shred
    exec_res = await client.post(
        "/api/v1/admin/audit-ledger/execute-shred",
        json={
            "confirmation_token": conf_token,
            "confirm_phrase": conf_phrase,
            "reason": "Authorized by Security Officer for secret spill",
        },
    )
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["status"] == "shredded"
    assert exec_data["records_shredded"] == 1

    # 6. Database Verification: wrapped_dek and dek_nonce must be NULL
    key_row = (
        await api_env.seed.execute(
            select(ActivityRecordKey).where(
                ActivityRecordKey.workspace_id == admin.workspace_id,
                ActivityRecordKey.activity_id == act_id,
            )
        )
    ).scalar_one()
    assert key_row.wrapped_dek is None
    assert key_row.dek_nonce is None
    assert key_row.shredded_at is not None

    # 7. Activity Feed Verification: payload must return CRYPTO_SHREDDED tombstone
    shredded_feed_res = await client.get(f"/api/v1/issues/{issue_key}/activity?tab=all")
    assert shredded_feed_res.status_code == 200
    shredded_items = shredded_feed_res.json()["items"]
    shredded_item = next((item for item in shredded_items if item["id"] == str(act_id)), None)
    assert shredded_item is not None
    assert shredded_item["payload"] == {
        "redacted": True,
        "reason": "CRYPTO_SHREDDED",
        "shredded_at": key_row.shredded_at.isoformat(),
    }

    # 8. Hash Chain Verification: verify_activity_chain() MUST remain valid!
    chain_post_shred = await api_env.seed.execute(
        text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws)"),
        {"ws": admin.workspace_id},
    )
    assert chain_post_shred.mappings().one()["is_valid"] is True

    # 9. Verify CRYPTO_SHRED_EXECUTED audit record exists in activity_records
    audit_rec = (
        await api_env.seed.execute(
            select(ActivityRecord).where(
                ActivityRecord.workspace_id == admin.workspace_id,
                ActivityRecord.event_type == ActivityEventType.CRYPTO_SHRED_EXECUTED,
            )
        )
    ).scalar_one_or_none()
    assert audit_rec is not None
    assert audit_rec.payload["target_id"] == str(act_id)
    assert audit_rec.payload["records_shredded"] == 1


@pytest.mark.asyncio
async def test_case_2_object_level_crypto_shred(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Positive Test 2: Shred all encrypted records associated with an entire issue."""
    admin = await make_user("shred_admin_2", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin.id)
    await make_project("SHR2", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin, aal_level=2)

    res_issue = await client.post(
        "/api/v1/projects/SHR2/issues",
        json={"summary": "Multi Secret Issue"},
    )
    issue_data = res_issue.json()
    issue_id = uuid.UUID(issue_data["id"])
    issue_key = issue_data["key"]

    # Record 3 encrypted activities for this issue
    act_ids: list[uuid.UUID] = []
    for i in range(1, 4):
        aid = await record_activity(
            session=api_env.seed,
            workspace_id=admin.workspace_id,
            object_id=issue_id,
            actor_principal_id=admin.id,
            event_type=ActivityEventType.ISSUE_FIELD_CHANGED,
            payload={"secret_num": i, "val": f"val_{i}"},
            encrypt_payload=True,
        )
        act_ids.append(aid)
    await api_env.seed.commit()

    # Stage 1: Request shred for object_id
    req_res = await client.post(
        "/api/v1/admin/audit-ledger/request-shred",
        json={"object_id": str(issue_id), "reason": "GDPR erasure request for issue"},
    )
    assert req_res.status_code == 200
    req_data = req_res.json()
    assert req_data["target_type"] == "object_id"
    assert req_data["records_to_shred"] >= 3

    # Stage 2: Execute shred
    exec_res = await client.post(
        "/api/v1/admin/audit-ledger/execute-shred",
        json={
            "confirmation_token": req_data["confirmation_token"],
            "confirm_phrase": req_data["confirm_phrase"],
            "reason": "GDPR erasure execution",
        },
    )
    assert exec_res.status_code == 200
    assert exec_res.json()["records_shredded"] >= 3

    # Feed check: all 3 items must be CRYPTO_SHREDDED
    feed_res = await client.get(f"/api/v1/issues/{issue_key}/activity?tab=all")
    assert feed_res.status_code == 200
    items_by_id = {item["id"]: item for item in feed_res.json()["items"]}
    for aid in act_ids:
        item = items_by_id.get(str(aid))
        assert item is not None
        assert item["payload"].get("reason") == "CRYPTO_SHREDDED"

    # Hash chain remains valid
    chain_chk = await api_env.seed.execute(
        text("SELECT is_valid FROM verify_activity_chain(:ws)"),
        {"ws": admin.workspace_id},
    )
    assert chain_chk.mappings().one()["is_valid"] is True


@pytest.mark.asyncio
async def test_case_3_negative_security_rejections(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Negative Test: Reject non-AAL2, bad tokens, phrase mismatches, and multiple targets."""
    admin = await make_user("shred_admin_3", workspace_role="WORKSPACE_ADMIN")
    await _enroll_totp(api_env.seed, admin.id)
    normal_member = await make_user("normal_user_3", workspace_role="WORKSPACE_MEMBER")
    await make_project("SHR3", created_by=admin)

    dummy_id = str(uuid.uuid4())

    # 1. Non-admin / non-AAL2 user rejected with 403
    client = as_principal(normal_member, aal_level=1)
    m_req = await client.post(
        "/api/v1/admin/audit-ledger/request-shred",
        json={"activity_id": dummy_id, "reason": "Unauthorized attempt"},
    )
    assert m_req.status_code in (401, 403)

    # Switch to admin with AAL2
    client = as_principal(admin, aal_level=2)

    # 2. Invalid target: both activity_id and object_id provided -> 422
    inv_req = await client.post(
        "/api/v1/admin/audit-ledger/request-shred",
        json={"activity_id": dummy_id, "object_id": dummy_id, "reason": "Both targets"},
    )
    assert inv_req.status_code == 422

    # 3. Invalid target: no target provided -> 422
    no_target_req = await client.post(
        "/api/v1/admin/audit-ledger/request-shred",
        json={"reason": "Missing targets"},
    )
    assert no_target_req.status_code == 422

    # 4. Valid Stage 1
    req_res = await client.post(
        "/api/v1/admin/audit-ledger/request-shred",
        json={"activity_id": dummy_id, "reason": "Valid test reason"},
    )
    assert req_res.status_code == 200
    token = req_res.json()["confirmation_token"]
    _ = req_res.json()["confirm_phrase"]

    # 5. Phrase mismatch -> 409 (token is consumed fail-closed)
    bad_phrase = await client.post(
        "/api/v1/admin/audit-ledger/execute-shred",
        json={
            "confirmation_token": token,
            "confirm_phrase": "WRONG PHRASE",
            "reason": "Testing bad phrase rejection",
        },
    )
    assert bad_phrase.status_code == 409
    assert bad_phrase.json()["code"] == "CONFIRM_PHRASE_MISMATCH"

    # 6. Request a new token for successful execution and replay test
    req_res_2 = await client.post(
        "/api/v1/admin/audit-ledger/request-shred",
        json={"activity_id": dummy_id, "reason": "Second request for execution"},
    )
    assert req_res_2.status_code == 200
    token_2 = req_res_2.json()["confirmation_token"]
    phrase_2 = req_res_2.json()["confirm_phrase"]

    good_exec = await client.post(
        "/api/v1/admin/audit-ledger/execute-shred",
        json={
            "confirmation_token": token_2,
            "confirm_phrase": phrase_2,
            "reason": "First consume valid reason",
        },
    )
    assert good_exec.status_code == 200

    # 7. Replay consumed token -> 409
    replay_exec = await client.post(
        "/api/v1/admin/audit-ledger/execute-shred",
        json={
            "confirmation_token": token_2,
            "confirm_phrase": phrase_2,
            "reason": "Replay attempt reason",
        },
    )
    assert replay_exec.status_code == 409
    assert replay_exec.json()["code"] == "INVALID_CONFIRMATION_TOKEN"


@pytest.mark.asyncio
async def test_case_4_permanent_purge_cascades_key_shredding(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Boundary Test: permanent_purge automatically crypto-shreds activity keys."""
    # SERVER_ADMIN required for permanent_purge
    sadmin = await make_user("super_admin_4", workspace_role="SERVER_ADMIN")
    await add_role_binding(
        api_env.seed,
        api_env.workspace_id,
        sadmin.id,
        role="WORKSPACE_ADMIN",
        scope_type="workspace",
    )
    await rebuild_era(api_env.seed, api_env.workspace_id)
    await api_env.seed.commit()
    await _enroll_totp(api_env.seed, sadmin.id)
    await make_project("SHR4", created_by=sadmin, roles={sadmin: "PROJECT_ADMIN"})
    client = as_principal(sadmin, aal_level=2)

    # 1. Create issue
    res_issue = await client.post(
        "/api/v1/projects/SHR4/issues",
        json={"summary": "Purge Me Issue"},
    )
    issue_data = res_issue.json()
    issue_id = uuid.UUID(issue_data["id"])
    issue_key = issue_data["key"]

    # 2. Record an encrypted activity for this issue
    act_id = await record_activity(
        session=api_env.seed,
        workspace_id=sadmin.workspace_id,
        object_id=issue_id,
        actor_principal_id=sadmin.id,
        event_type=ActivityEventType.ISSUE_FIELD_CHANGED,
        payload={"spilled_secret": "will_be_purged"},
        encrypt_payload=True,
    )
    await api_env.seed.commit()

    # Verify key initially exists and is not shredded
    k_init = (
        await api_env.seed.execute(
            select(ActivityRecordKey).where(
                ActivityRecordKey.workspace_id == sadmin.workspace_id,
                ActivityRecordKey.activity_id == act_id,
            )
        )
    ).scalar_one()
    assert k_init.wrapped_dek is not None

    # 3. Soft-trash the issue (two-stage delete)
    req_trash = await client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": issue_key, "mode": "trash"},
    )
    assert req_trash.status_code == 200
    trash_data = req_trash.json()

    exec_trash = await client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": issue_key,
            "mode": "trash",
            "confirmation_token": trash_data["confirmation_token"],
            "confirm_phrase": trash_data["confirm_phrase"],
            "reason": "Authorized test trash",
        },
    )
    assert exec_trash.status_code == 200

    # 4. Permanent purge the issue (two-stage delete)
    req_purge = await client.post(
        "/api/v1/admin/destructive:request",
        json={"target_kind": "issue", "target": issue_key, "mode": "permanent_purge"},
    )
    assert req_purge.status_code == 200
    purge_data = req_purge.json()

    exec_purge = await client.post(
        "/api/v1/admin/destructive:execute",
        json={
            "target_kind": "issue",
            "target": issue_key,
            "mode": "permanent_purge",
            "confirmation_token": purge_data["confirmation_token"],
            "confirm_phrase": purge_data["confirm_phrase"],
            "reason": "Authorized test permanent purge",
        },
    )
    assert exec_purge.status_code == 200

    # 5. Verify that permanent purge automatically shredded the key!
    api_env.seed.expire_all()
    k_purged = (
        await api_env.seed.execute(
            select(ActivityRecordKey).where(
                ActivityRecordKey.workspace_id == sadmin.workspace_id,
                ActivityRecordKey.activity_id == act_id,
            )
        )
    ).scalar_one()
    assert k_purged.wrapped_dek is None
    assert k_purged.dek_nonce is None
    assert k_purged.shredded_at is not None

    # 6. Verify workspace activity chain remains valid
    chain_post_purge = await api_env.seed.execute(
        text("SELECT is_valid FROM verify_activity_chain(:ws)"),
        {"ws": sadmin.workspace_id},
    )
    assert chain_post_purge.mappings().one()["is_valid"] is True
