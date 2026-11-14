# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration tests for CustomFieldExecutor cache partitioning, escalation gates, and server audit.

KB-P5-13, S13.2, S13.3.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import select, text

from database.models import (
    ApprovedWasmModule,
    CustomFieldDefinition,
    CustomFieldValue,
)
from database.models.activity import ActivityRecord
from database.models.custom_field_approval import CustomFieldApproval
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.custom_fields.approvals import (
    compute_approval_signature_hmac,
    load_key_material,
)
from kanban.custom_fields.executor import CustomFieldExecutor
from kanban.custom_fields.manifest import compute_field_manifest_sha256
from kanban.sandbox.wasm_runner import TierAWasmRunner

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.committed_db
FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "wasm"


async def _seed_context(db_session: AsyncSession) -> dict[str, Any]:
    """Seed test workspace, users, project KAN, issue KAN-142, and approved wasm module."""
    ws_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    sec_admin_id = uuid.uuid4()
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    kan_id = uuid.uuid4()
    iss_id = uuid.uuid4()

    await db_session.execute(text("RESET SESSION AUTHORIZATION"))
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Custom Fields Test WS"},
    )

    for pid, dname in (
        (admin_id, "Project Admin"),
        (sec_admin_id, "Sec Admin"),
        (user_a_id, "User A"),
        (user_b_id, "User B"),
    ):
        await db_session.execute(
            text("SELECT register_object('user'::object_kind, :ws, NULL, :ckey, :name, :uid, :id)"),
            {"ws": ws_id, "ckey": f"usr-{pid.hex[:8]}", "name": dname, "uid": pid, "id": pid},
        )
        await db_session.execute(
            text(
                "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
                "VALUES (:id, :ws_id, 'USER', :name)"
            ),
            {"id": pid, "ws_id": ws_id, "name": dname},
        )
        await db_session.execute(
            text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
            {"id": pid, "ws_id": ws_id, "email": f"{pid.hex[:8]}@example.com"},
        )

    # Register project KAN
    await db_session.execute(
        text(
            "SELECT register_object("
            "'project'::object_kind, :ws, NULL, 'KAN', 'Kanban Project', :uid, :id)"
        ),
        {"ws": ws_id, "uid": admin_id, "id": kan_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws_id, 'KAN', 'Kanban Project')"
        ),
        {"id": kan_id, "ws_id": ws_id},
    )

    # Fetch default state & priority
    st_row = await db_session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p AND is_default = true"),
        {"p": kan_id},
    )
    st_id = st_row.scalar_one()

    pr_row = await db_session.execute(
        text("SELECT id FROM project_priorities WHERE project_id = :p AND is_default = true"),
        {"p": kan_id},
    )
    pr_id = pr_row.scalar_one()

    # Register issue KAN-142
    await db_session.execute(
        text("UPDATE projects SET issue_seq_counter = 142 WHERE id = :p"),
        {"p": kan_id},
    )
    await db_session.execute(
        text(
            "SELECT register_object("
            "'issue'::object_kind, :ws, :proj, 'KAN-142', 'Test Issue 142', :cr, :id)"
        ),
        {"ws": ws_id, "proj": kan_id, "cr": admin_id, "id": iss_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO issues (id, workspace_id, project_id, sequence_id, "
            "state_id, priority_id, summary, created_by_id, board_rank) "
            "VALUES (:id, :ws, :proj, 142, :st, :pr, 'Test Issue 142', :cr, '0|hzzzzz:')"
        ),
        {"id": iss_id, "ws": ws_id, "proj": kan_id, "st": st_id, "pr": pr_id, "cr": admin_id},
    )

    # Register echo_cvss.wasm
    echo_bytes = (FIXTURES_DIR / "echo_cvss.wasm").read_bytes()
    runner = TierAWasmRunner.get_instance()
    sha256_cvss = runner.validate_module(echo_bytes)

    wasm_mod = ApprovedWasmModule(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        project_id=kan_id,
        sha256=sha256_cvss,
        name="echo_cvss.wasm",
        wasm_bytes=echo_bytes,
        approved_by_id=admin_id,
    )
    db_session.add(wasm_mod)
    await db_session.commit()

    return {
        "workspace_id": ws_id,
        "project_id": kan_id,
        "admin_id": admin_id,
        "sec_admin_id": sec_admin_id,
        "user_a_id": user_a_id,
        "user_b_id": user_b_id,
        "issue_id": iss_id,
        "sha256_cvss": sha256_cvss,
    }


@pytest.mark.asyncio
async def test_cache_partitioning_invoking_user_and_sp(
    db_session: AsyncSession,
) -> None:
    """Test 4: Cache partitioning on INVOKING_USER vs shared cache on PROJECT_ADMIN_SP (S13.2)."""
    ctx = await _seed_context(db_session)
    ws_id = ctx["workspace_id"]
    proj_id = ctx["project_id"]
    sha256_cvss = ctx["sha256_cvss"]
    iss_id = ctx["issue_id"]

    hash_a = hashlib.sha256(b"userA-sec-group").digest()
    hash_b = hashlib.sha256(b"userB-no-sec").digest()

    caller_a = PrincipalContext(
        principal_id=ctx["user_a_id"],
        workspace_id=ws_id,
        aal_level=1,
        user_access_hash=hash_a,  # type: ignore[call-arg]
    )
    caller_b = PrincipalContext(
        principal_id=ctx["user_b_id"],
        workspace_id=ws_id,
        aal_level=1,
        user_access_hash=hash_b,  # type: ignore[call-arg]
    )

    # 1. Create INVOKING_USER field
    field_iu_id = uuid.uuid4()
    manifest_iu = compute_field_manifest_sha256(
        script_source=sha256_cvss.hex(),
        output_format="severity_pill",
        output_format_metadata={},
        tier="wasm",
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
    )
    field_iu = CustomFieldDefinition(
        id=field_iu_id,
        workspace_id=ws_id,
        project_id=proj_id,
        slug="cvss-calc",
        name="CVSS Pill",
        tier="wasm",
        output_format="severity_pill",
        output_format_metadata={},
        script_source=sha256_cvss.hex(),
        wasm_module_sha256=sha256_cvss,
        script_version=1,
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
        egress_allowlist=[],
        manifest_sha256=manifest_iu,
        is_enabled=True,
        created_by_id=ctx["admin_id"],
    )
    db_session.add(field_iu)
    await db_session.commit()

    executor = CustomFieldExecutor(db_session)

    # User A executes on KAN-142
    res_a = await executor.execute_for_issue(db_session, caller_a, "KAN-142", field_iu_id)
    assert res_a["status"] == "computed"
    assert res_a["value"] == {"level": "high", "score": 8.8, "label": "8.8 High"}

    # Verify 1 cache row partitioned by hash_a
    rows_stmt = select(CustomFieldValue).where(
        CustomFieldValue.issue_id == iss_id,
        CustomFieldValue.field_id == field_iu_id,
    )
    rows = list((await db_session.execute(rows_stmt)).scalars().all())
    assert len(rows) == 1
    assert rows[0].user_access_hash == hash_a

    # User B executes on KAN-142 -> distinct cache partition (not User A's row)
    res_b = await executor.execute_for_issue(db_session, caller_b, "KAN-142", field_iu_id)
    assert res_b["status"] == "computed"
    assert res_b["value"] == {"level": "high", "score": 8.8, "label": "8.8 High"}

    rows_after = list((await db_session.execute(rows_stmt)).scalars().all())
    assert len(rows_after) == 2
    hashes = {r.user_access_hash for r in rows_after}
    assert hashes == {hash_a, hash_b}

    # 2. Create PROJECT_ADMIN_SP field (shared cache with user_access_hash == b"")
    field_sp_id = uuid.uuid4()
    manifest_sp = compute_field_manifest_sha256(
        script_source=sha256_cvss.hex(),
        output_format="severity_pill",
        output_format_metadata={},
        tier="wasm",
        target_scope="PROJECT",
        credential_mode="PROJECT_ADMIN_SP",
    )
    field_sp = CustomFieldDefinition(
        id=field_sp_id,
        workspace_id=ws_id,
        project_id=proj_id,
        slug="cvss-sp",
        name="CVSS SP",
        tier="wasm",
        output_format="severity_pill",
        output_format_metadata={},
        script_source=sha256_cvss.hex(),
        wasm_module_sha256=sha256_cvss,
        script_version=1,
        target_scope="PROJECT",
        credential_mode="PROJECT_ADMIN_SP",
        egress_allowlist=[],
        manifest_sha256=manifest_sp,
        is_enabled=True,
        created_by_id=ctx["admin_id"],
    )
    db_session.add(field_sp)
    await db_session.commit()

    # Insert approved escalation record
    auth_pepper = load_key_material().auth_pepper
    valid_sp_hmac = compute_approval_signature_hmac(
        field_id=field_sp_id,
        manifest_sha256=manifest_sp,
        target_scope="PROJECT",
        credential_mode="PROJECT_ADMIN_SP",
        primary_approver_id=ctx["admin_id"],
        secondary_approver_id=None,
        auth_pepper=auth_pepper,
    )
    approval_sp = CustomFieldApproval(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        project_id=proj_id,
        field_id=field_sp_id,
        manifest_sha256=manifest_sp,
        target_scope="PROJECT",
        credential_mode="PROJECT_ADMIN_SP",
        required_tier="PROJECT_ADMIN",
        status="APPROVED",
        requested_by_id=ctx["admin_id"],
        justification="Shared SP evaluation",
        primary_approver_id=ctx["admin_id"],
        primary_approver_aal=2,
        primary_approved_at=datetime.now(UTC),
        sp_warning_acknowledged=True,
        approval_signature_hmac=valid_sp_hmac,
    )
    db_session.add(approval_sp)
    await db_session.commit()

    # User A executes SP field
    res_sp_a = await executor.execute_for_issue(db_session, caller_a, "KAN-142", field_sp_id)
    assert res_sp_a["status"] == "computed"

    sp_rows_stmt = select(CustomFieldValue).where(
        CustomFieldValue.issue_id == iss_id,
        CustomFieldValue.field_id == field_sp_id,
    )
    sp_rows = list((await db_session.execute(sp_rows_stmt)).scalars().all())
    assert len(sp_rows) == 1
    assert sp_rows[0].user_access_hash == b""

    # User B executes SP field -> cache hit!
    res_sp_b = await executor.execute_for_issue(db_session, caller_b, "KAN-142", field_sp_id)
    assert res_sp_b["status"] == "cached"
    sp_rows_final = list((await db_session.execute(sp_rows_stmt)).scalars().all())
    assert len(sp_rows_final) == 1


@pytest.mark.asyncio
async def test_revoked_approval_and_server_audit(db_session: AsyncSession) -> None:
    """Test 5: Tampered script returns 409 APPROVAL_REVOKED.

    SERVER scope writes 3 audits and 0 cache.
    """
    ctx = await _seed_context(db_session)
    ws_id = ctx["workspace_id"]
    proj_id = ctx["project_id"]
    sha256_cvss = ctx["sha256_cvss"]
    iss_id = ctx["issue_id"]

    admin_caller = PrincipalContext(
        principal_id=ctx["admin_id"],
        workspace_id=ws_id,
        aal_level=2,
    )

    # 1. Create SERVER-scope field
    field_srv_id = uuid.uuid4()
    manifest_srv = compute_field_manifest_sha256(
        script_source=sha256_cvss.hex(),
        output_format="severity_pill",
        output_format_metadata={},
        tier="wasm",
        target_scope="SERVER",
        credential_mode="SERVER_ADMIN_SP",
    )
    field_srv = CustomFieldDefinition(
        id=field_srv_id,
        workspace_id=ws_id,
        project_id=proj_id,
        slug="cvss-server",
        name="CVSS Server Scope",
        tier="wasm",
        output_format="severity_pill",
        output_format_metadata={},
        script_source=sha256_cvss.hex(),
        wasm_module_sha256=sha256_cvss,
        script_version=1,
        target_scope="SERVER",
        credential_mode="SERVER_ADMIN_SP",
        egress_allowlist=[],
        manifest_sha256=manifest_srv,
        is_enabled=True,
        created_by_id=ctx["admin_id"],
    )
    db_session.add(field_srv)
    await db_session.commit()

    # Insert dual-approved SERVER-scope escalation record
    auth_pepper = load_key_material().auth_pepper
    sec_admin_id = ctx["sec_admin_id"]

    valid_srv_hmac = compute_approval_signature_hmac(
        field_id=field_srv_id,
        manifest_sha256=manifest_srv,
        target_scope="SERVER",
        credential_mode="SERVER_ADMIN_SP",
        primary_approver_id=ctx["admin_id"],
        secondary_approver_id=sec_admin_id,
        auth_pepper=auth_pepper,
    )
    approval_srv = CustomFieldApproval(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        project_id=proj_id,
        field_id=field_srv_id,
        manifest_sha256=manifest_srv,
        target_scope="SERVER",
        credential_mode="SERVER_ADMIN_SP",
        required_tier="SERVER_ADMIN_DUAL",
        status="APPROVED",
        requested_by_id=ctx["admin_id"],
        justification="Server scope audit testing",
        primary_approver_id=ctx["admin_id"],
        primary_approver_aal=2,
        primary_approved_at=datetime.now(UTC),
        secondary_approver_id=sec_admin_id,
        secondary_approver_aal=2,
        secondary_approved_at=datetime.now(UTC),
        sp_warning_acknowledged=True,
        approval_signature_hmac=valid_srv_hmac,
    )
    db_session.add(approval_srv)
    await db_session.commit()

    executor = CustomFieldExecutor(db_session)

    # Execute approved SERVER-scope field 3 times
    for _ in range(3):
        res = await executor.execute_for_issue(db_session, admin_caller, "KAN-142", field_srv_id)
        assert res["status"] == "computed"

    # Verify 0 rows stored in custom_field_values
    cached_cnt = await db_session.scalar(
        select(text("COUNT(*)"))
        .select_from(CustomFieldValue)
        .where(
            CustomFieldValue.issue_id == iss_id,
            CustomFieldValue.field_id == field_srv_id,
        )
    )
    assert cached_cnt == 0

    # Verify 3 CUSTOM_FIELD_SERVER_INVOKED rows in activity_records
    act_cnt = await db_session.scalar(
        select(text("COUNT(*)"))
        .select_from(ActivityRecord)
        .where(
            ActivityRecord.workspace_id == ws_id,
            ActivityRecord.event_type == "CUSTOM_FIELD_SERVER_INVOKED",
        )
    )
    assert act_cnt == 3

    # Tamper script_source -> manifest mismatch causes 409 APPROVAL_REVOKED
    await db_session.execute(
        text("UPDATE custom_field_definitions SET manifest_sha256 = :new_m WHERE id = :id"),
        {"new_m": b"\x00" * 32, "id": field_srv_id},
    )
    await db_session.commit()

    with pytest.raises(ProblemException) as exc_info:
        await executor.execute_for_issue(db_session, admin_caller, "KAN-142", field_srv_id)
    assert exc_info.value.status == 409
    assert exc_info.value.code == "APPROVAL_REVOKED"

    # Verify cached_only=True lists tampered field as APPROVAL_REVOKED and value is None
    list_revoked = await executor.list_values_for_issue(
        db_session, admin_caller, "KAN-142", cached_only=True
    )
    rev_items = [it for it in list_revoked if it["field_id"] == str(field_srv_id)]
    assert len(rev_items) == 1
    assert rev_items[0]["status"] == "APPROVAL_REVOKED"
    assert rev_items[0]["value"] is None


@pytest.mark.asyncio
async def test_executor_error_branches(db_session: AsyncSession) -> None:
    """Validate error branches: missing issue, missing field, schema invalid, tier B 503."""
    ctx = await _seed_context(db_session)
    ws_id = ctx["workspace_id"]
    proj_id = ctx["project_id"]
    admin_caller = PrincipalContext(
        principal_id=ctx["admin_id"],
        workspace_id=ws_id,
        aal_level=2,
    )
    executor = CustomFieldExecutor(db_session)

    # Non-existent issue -> 404
    with pytest.raises(ProblemException) as iss_err:
        await executor.execute_for_issue(db_session, admin_caller, "KAN-9999", uuid.uuid4())
    assert iss_err.value.status == 404

    # Non-existent field -> 404
    with pytest.raises(ProblemException) as fld_err:
        await executor.execute_for_issue(db_session, admin_caller, "KAN-142", uuid.uuid4())
    assert fld_err.value.status == 404

    # Tier B field -> 503 SANDBOX_UNAVAILABLE_IN_STANDALONE
    tier_b_id = uuid.uuid4()
    manifest_b = compute_field_manifest_sha256(
        script_source="print('hello')",
        output_format="text",
        output_format_metadata={},
        tier="nsjail",
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
    )
    tier_b_field = CustomFieldDefinition(
        id=tier_b_id,
        workspace_id=ws_id,
        project_id=proj_id,
        slug="nsjail-field",
        name="Nsjail Script",
        tier="nsjail",
        output_format="text",
        output_format_metadata={},
        script_source="print('hello')",
        script_version=1,
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
        egress_allowlist=[],
        manifest_sha256=manifest_b,
        is_enabled=True,
        created_by_id=ctx["admin_id"],
    )
    db_session.add(tier_b_field)
    await db_session.commit()

    with pytest.raises(ProblemException) as b_err:
        await executor.execute_for_issue(db_session, admin_caller, "KAN-142", tier_b_id)
    assert b_err.value.status == 503
    assert b_err.value.code == "SANDBOX_UNAVAILABLE_IN_STANDALONE"

    # Schema invalid output: wasm outputs severity_pill JSON, but field expects number
    bad_schema_id = uuid.uuid4()
    manifest_bad = compute_field_manifest_sha256(
        script_source=ctx["sha256_cvss"].hex(),
        output_format="number",
        output_format_metadata={"min": 0, "max": 10},
        tier="wasm",
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
    )
    bad_field = CustomFieldDefinition(
        id=bad_schema_id,
        workspace_id=ws_id,
        project_id=proj_id,
        slug="bad-schema-field",
        name="Bad Schema",
        tier="wasm",
        output_format="number",
        output_format_metadata={"min": 0, "max": 10},
        script_source=ctx["sha256_cvss"].hex(),
        wasm_module_sha256=ctx["sha256_cvss"],
        script_version=1,
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
        egress_allowlist=[],
        manifest_sha256=manifest_bad,
        is_enabled=True,
        created_by_id=ctx["admin_id"],
    )
    db_session.add(bad_field)
    await db_session.commit()

    with pytest.raises(ProblemException) as s_err:
        await executor.execute_for_issue(db_session, admin_caller, "KAN-142", bad_schema_id)
    assert s_err.value.status == 422
    assert s_err.value.code == "SCRIPT_OUTPUT_SCHEMA_INVALID"

    # list_values_for_issue includes all fields
    all_vals = await executor.list_values_for_issue(db_session, admin_caller, "KAN-142")
    assert len(all_vals) >= 2


@pytest.mark.asyncio
async def test_executor_edge_branches(db_session: AsyncSession) -> None:
    """Validate remaining branch paths in CustomFieldExecutor."""
    ctx = await _seed_context(db_session)
    ws_id = ctx["workspace_id"]
    proj_id = ctx["project_id"]
    admin_caller = PrincipalContext(
        principal_id=ctx["admin_id"],
        workspace_id=ws_id,
        aal_level=2,
        user_access_hash=hashlib.sha256(b"admin-hex-hash").hexdigest(),  # type: ignore[arg-type]
    )
    executor = CustomFieldExecutor(db_session)

    # 1. No active session provided
    naked_executor = CustomFieldExecutor(session=None)
    with pytest.raises(RuntimeError, match="No AsyncSession provided"):
        await naked_executor.execute_for_issue("KAN-142", uuid.uuid4(), admin_caller)

    # 2. Missing Wasm module in approved_wasm_modules -> 404
    missing_mod_id = uuid.uuid4()
    dummy_sha = b"\xaa" * 32
    manifest_miss = compute_field_manifest_sha256(
        script_source=dummy_sha.hex(),
        output_format="text",
        output_format_metadata={},
        tier="wasm",
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
    )
    f_missing = CustomFieldDefinition(
        id=missing_mod_id,
        workspace_id=ws_id,
        project_id=proj_id,
        slug="missing-mod",
        name="Missing Mod",
        tier="wasm",
        output_format="text",
        output_format_metadata={},
        script_source=dummy_sha.hex(),
        wasm_module_sha256=dummy_sha,
        script_version=1,
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
        egress_allowlist=[],
        manifest_sha256=manifest_miss,
        is_enabled=True,
        created_by_id=ctx["admin_id"],
    )
    db_session.add(f_missing)
    await db_session.commit()

    with pytest.raises(ProblemException) as miss_err:
        await executor.execute_for_issue(db_session, admin_caller, "KAN-142", missing_mod_id)
    assert miss_err.value.status == 404
    assert miss_err.value.code == "WASM_MODULE_NOT_FOUND"

    # 3. Base64 fallback when wasm_module_sha256 is None
    echo_wasm = (FIXTURES_DIR / "echo_cvss.wasm").read_bytes()
    b64_wasm = base64.b64encode(echo_wasm).decode("ascii")

    f_b64_id = uuid.uuid4()
    manifest_b64 = compute_field_manifest_sha256(
        script_source=b64_wasm,
        output_format="severity_pill",
        output_format_metadata={},
        tier="wasm",
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
    )
    f_b64 = CustomFieldDefinition(
        id=f_b64_id,
        workspace_id=ws_id,
        project_id=proj_id,
        slug="b64-mod",
        name="B64 Mod",
        tier="wasm",
        output_format="severity_pill",
        output_format_metadata={},
        script_source=b64_wasm,
        wasm_module_sha256=None,
        script_version=1,
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
        egress_allowlist=[],
        manifest_sha256=manifest_b64,
        is_enabled=True,
        created_by_id=ctx["admin_id"],
    )
    db_session.add(f_b64)
    await db_session.commit()

    # Execute by slug
    res_slug = await executor.execute_for_issue(db_session, admin_caller, "KAN-142", "b64-mod")
    assert res_slug["status"] == "computed"

    # 4. Invalid base64/hex in script_source when wasm_module_sha256 is None
    f_bad_b64_id = uuid.uuid4()
    manifest_bad_b64 = compute_field_manifest_sha256(
        script_source="not-valid-b64-or-wasm!!!",
        output_format="text",
        output_format_metadata={},
        tier="wasm",
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
    )
    f_bad_b64 = CustomFieldDefinition(
        id=f_bad_b64_id,
        workspace_id=ws_id,
        project_id=proj_id,
        slug="bad-b64",
        name="Bad B64",
        tier="wasm",
        output_format="text",
        output_format_metadata={},
        script_source="not-valid-b64-or-wasm!!!",
        wasm_module_sha256=None,
        script_version=1,
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
        egress_allowlist=[],
        manifest_sha256=manifest_bad_b64,
        is_enabled=True,
        created_by_id=ctx["admin_id"],
    )
    db_session.add(f_bad_b64)
    await db_session.commit()

    with pytest.raises(ProblemException) as bad_b64_err:
        await executor.execute_for_issue(db_session, admin_caller, "KAN-142", f_bad_b64_id)
    assert bad_b64_err.value.status == 422
    assert bad_b64_err.value.code == "WASM_BINARY_INVALID"

    # 5. Invalid tier (simulated via in-memory definition mutation without autoflush)
    with db_session.no_autoflush:
        f_b64.tier = "unknown_tier"
        with pytest.raises(ProblemException) as tier_err:
            await executor.execute_for_issue(
                db_session, admin_caller, "KAN-142", f_b64_id, force_refresh=True
            )
        assert tier_err.value.status == 422
        assert tier_err.value.code == "INVALID_TIER"
        f_b64.tier = "wasm"

    # 6. list_values_for_issue with cached_only=True returns cached and not_computed items
    list_cached = await executor.list_values_for_issue(
        db_session, admin_caller, "KAN-142", cached_only=True
    )
    assert len(list_cached) >= 1
    for it in list_cached:
        assert it["status"] in ("cached", "not_computed")
