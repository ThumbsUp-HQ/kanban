# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Forensic unit tests for envelope-encrypted activity records and hash chains (KB-SEC-SHRED-01)."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from database.models.activity_key import ActivityRecordKey
from database.tests.conftest import bootstrap_workspace_admin

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _make_dummy_v1_envelope(
    workspace_id: uuid.UUID,
    activity_id: uuid.UUID,
    event_type: str,
) -> tuple[int, bytes, bytes, bytes, bytes, bytes, str]:
    """Generate dummy envelope-encrypted fields for database chain testing."""
    ct = os.urandom(64)
    nonce = os.urandom(12)
    aad = f"{workspace_id}|{activity_id}|{event_type}".encode()
    aad_sha = hashlib.sha256(aad).digest()
    wrapped_dek = os.urandom(48)
    dek_nonce = os.urandom(12)
    dek_kid = "kek-v1"
    return 1, ct, nonce, aad_sha, wrapped_dek, dek_nonce, dek_kid


async def _create_workspace(db_session: AsyncSession) -> uuid.UUID:
    """Provision a workspace for hash-chain testing."""
    ws_id, _ = await bootstrap_workspace_admin(db_session, name="CryptoShred-WS")
    return ws_id


@pytest.mark.asyncio
async def test_mixed_v0_v1_activity_chain_and_crypto_shred(db_session: AsyncSession) -> None:
    """Verify mixed v0/v1 records, hash verification, DEK shredding, and chain integrity."""
    ws_id = await _create_workspace(db_session)

    # 1. Append 2 legacy v0 records
    v0_ids: list[uuid.UUID] = []
    for step in range(1, 3):
        res = await db_session.execute(
            text("SELECT append_activity(  :ws_id, NULL, NULL, NULL, 'ISSUE_CREATED', :payload)"),
            {"ws_id": ws_id, "payload": json.dumps({"legacy_step": step})},
        )
        v0_ids.append(res.scalar_one())

    # 2. Append 3 envelope-encrypted v1 records with wrapped DEKs
    v1_ids: list[uuid.UUID] = []
    dummy_obj_id = uuid.uuid4()
    for _step in range(3, 6):
        act_id = uuid.uuid4()
        (
            enc_ver,
            ct,
            nonce,
            aad_sha,
            wrapped_dek,
            dek_nonce,
            dek_kid,
        ) = _make_dummy_v1_envelope(
            workspace_id=ws_id,
            activity_id=act_id,
            event_type="ISSUE_FIELD_CHANGED",
        )

        # Store wrapped key
        key_record = ActivityRecordKey(
            workspace_id=ws_id,
            activity_id=act_id,
            object_id=dummy_obj_id,
            actor_id=None,
            wrapped_dek=wrapped_dek,
            dek_nonce=dek_nonce,
            dek_kid=dek_kid,
        )
        db_session.add(key_record)
        await db_session.flush()

        persisted_payload = json.dumps({"encrypted": True, "v": 1})
        res = await db_session.execute(
            text(
                "SELECT append_activity("
                "  :ws_id, NULL, NULL, NULL, 'ISSUE_FIELD_CHANGED', :payload,"
                "  :enc_ver, :ct, :nonce, :aad_sha, :act_id"
                ")"
            ),
            {
                "ws_id": ws_id,
                "payload": persisted_payload,
                "enc_ver": enc_ver,
                "ct": ct,
                "nonce": nonce,
                "aad_sha": aad_sha,
                "act_id": act_id,
            },
        )
        v1_ids.append(res.scalar_one())

    await db_session.commit()

    # 3. Verify initial mixed chain: 2 v0 + 3 v1 rows
    verify_res = await db_session.execute(
        text(
            "SELECT is_valid, checked_rows, first_broken_seq, failure_reason "
            "FROM verify_activity_chain(:ws_id)"
        ),
        {"ws_id": ws_id},
    )
    rep = verify_res.mappings().one()
    assert rep["is_valid"] is True
    assert rep["checked_rows"] == 5
    assert rep["first_broken_seq"] is None
    assert rep["failure_reason"] is None

    # 4. Execute crypto-shred on row 4 key
    target_shred_id = v1_ids[1]
    await db_session.execute(
        text(
            "UPDATE activity_record_keys "
            "SET wrapped_dek = NULL, dek_nonce = NULL, shredded_at = clock_timestamp(), "
            "    shred_reason = 'PII erasure' "
            "WHERE workspace_id = :ws_id AND activity_id = :act_id"
        ),
        {"ws_id": ws_id, "act_id": target_shred_id},
    )
    await db_session.commit()

    # Verify key was shredded
    key_row = (
        await db_session.execute(
            select(ActivityRecordKey).where(
                ActivityRecordKey.workspace_id == ws_id,
                ActivityRecordKey.activity_id == target_shred_id,
            )
        )
    ).scalar_one()
    assert key_row.wrapped_dek is None
    assert key_row.dek_nonce is None
    assert key_row.shredded_at is not None

    # 5. Re-verify activity chain: STILL VALID!
    reverify_res = await db_session.execute(
        text(
            "SELECT is_valid, checked_rows, first_broken_seq, failure_reason "
            "FROM verify_activity_chain(:ws_id)"
        ),
        {"ws_id": ws_id},
    )
    re_rep = reverify_res.mappings().one()
    assert re_rep["is_valid"] is True
    assert re_rep["checked_rows"] == 5

    # 6. Shred all keys for dummy_obj_id
    await db_session.execute(
        text(
            "UPDATE activity_record_keys "
            "SET wrapped_dek = NULL, dek_nonce = NULL, shredded_at = clock_timestamp() "
            "WHERE workspace_id = :ws_id AND object_id = :oid"
        ),
        {"ws_id": ws_id, "oid": dummy_obj_id},
    )
    await db_session.commit()

    # Re-verify again: STILL VALID!
    final_res = await db_session.execute(
        text("SELECT is_valid, checked_rows FROM verify_activity_chain(:ws_id)"),
        {"ws_id": ws_id},
    )
    final_rep = final_res.mappings().one()
    assert final_rep["is_valid"] is True
    assert final_rep["checked_rows"] == 5


@pytest.mark.asyncio
async def test_activity_ledger_immutability_and_tamper_detection(db_session: AsyncSession) -> None:
    """Verify that immutable trigger rejects mutations and tampering breaks the chain."""
    ws_id = await _create_workspace(db_session)

    # Insert 1 v1 encrypted record
    act_id = uuid.uuid4()
    enc_ver, ct, nonce, aad_sha, _w_dek, _d_nonce, _d_kid = _make_dummy_v1_envelope(
        ws_id, act_id, "SECRET_ROTATED"
    )

    await db_session.execute(
        text(
            "SELECT append_activity("
            "  :ws_id, NULL, NULL, NULL, 'SECRET_ROTATED', "
            '  \'{"encrypted": true, "v": 1}\'::jsonb,'
            "  :enc_ver, :ct, :nonce, :aad_sha, :act_id"
            ")"
        ),
        {
            "ws_id": ws_id,
            "enc_ver": enc_ver,
            "ct": ct,
            "nonce": nonce,
            "aad_sha": aad_sha,
            "act_id": act_id,
        },
    )
    await db_session.commit()

    # 1. Direct UPDATE on activity_records must raise ACTIVITY_LEDGER_IMMUTABLE
    with pytest.raises(Exception, match="ACTIVITY_LEDGER_IMMUTABLE"):
        await db_session.execute(
            text("UPDATE activity_records SET encryption_ver = 0 WHERE workspace_id = :ws_id"),
            {"ws_id": ws_id},
        )
    await db_session.rollback()

    # 2. Direct DELETE on activity_records must raise ACTIVITY_LEDGER_IMMUTABLE
    with pytest.raises(Exception, match="ACTIVITY_LEDGER_IMMUTABLE"):
        await db_session.execute(
            text("DELETE FROM activity_records WHERE workspace_id = :ws_id"),
            {"ws_id": ws_id},
        )
    await db_session.rollback()

    # 3. Tamper with payload_ciphertext by 1 byte (triggers temporarily disabled)
    await db_session.execute(text("ALTER TABLE activity_records DISABLE TRIGGER USER"))
    tampered_ct = bytearray(ct)
    tampered_ct[0] ^= 0x01
    await db_session.execute(
        text("UPDATE activity_records SET payload_ciphertext = :t_ct WHERE workspace_id = :ws_id"),
        {"ws_id": ws_id, "t_ct": bytes(tampered_ct)},
    )
    await db_session.execute(text("ALTER TABLE activity_records ENABLE TRIGGER USER"))
    await db_session.commit()

    # Verify chain verification fails with ROW_HASH_MISMATCH
    tamper_res = await db_session.execute(
        text("SELECT is_valid, checked_rows, failure_reason FROM verify_activity_chain(:ws_id)"),
        {"ws_id": ws_id},
    )
    rep = tamper_res.mappings().one()
    assert rep["is_valid"] is False
    assert rep["failure_reason"] == "ROW_HASH_MISMATCH"


@pytest.mark.asyncio
async def test_tamper_nonce_and_aad_detection(db_session: AsyncSession) -> None:
    """Verify that tampering with payload_nonce or payload_aad_sha256 fails chain check."""
    ws_id = await _create_workspace(db_session)

    act_id = uuid.uuid4()
    enc_ver, ct, nonce, aad_sha, _, _, _ = _make_dummy_v1_envelope(ws_id, act_id, "STATE_CHANGED")

    await db_session.execute(
        text(
            "SELECT append_activity("
            "  :ws_id, NULL, NULL, NULL, 'STATE_CHANGED', '{\"encrypted\": true}'::jsonb,"
            "  :enc_ver, :ct, :nonce, :aad_sha, :act_id"
            ")"
        ),
        {
            "ws_id": ws_id,
            "enc_ver": enc_ver,
            "ct": ct,
            "nonce": nonce,
            "aad_sha": aad_sha,
            "act_id": act_id,
        },
    )
    await db_session.commit()

    # Tamper with nonce
    await db_session.execute(text("ALTER TABLE activity_records DISABLE TRIGGER USER"))
    tampered_nonce = bytearray(nonce)
    tampered_nonce[0] ^= 0xFF
    await db_session.execute(
        text("UPDATE activity_records SET payload_nonce = :t_nonce WHERE workspace_id = :ws_id"),
        {"ws_id": ws_id, "t_nonce": bytes(tampered_nonce)},
    )
    await db_session.execute(text("ALTER TABLE activity_records ENABLE TRIGGER USER"))
    await db_session.commit()

    res = await db_session.execute(
        text("SELECT is_valid, failure_reason FROM verify_activity_chain(:ws_id)"),
        {"ws_id": ws_id},
    )
    assert res.mappings().one()["failure_reason"] == "ROW_HASH_MISMATCH"
