# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for Scope x Principal matrix, HMAC signatures, cache partitioning and execution gates.

KB-P5-12, S13.2, S4.2, S3.2.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from database.models.custom_field import CustomFieldDefinition
from database.models.custom_field_approval import CustomFieldApproval
from kanban.api.problems import ProblemException
from kanban.custom_fields.approvals import (
    ApprovalRevokedError,
    CustomFieldApprovalService,
    assert_execution_authorized,
    compute_approval_signature_hmac,
    compute_cache_partition_key,
    required_approver_tier,
    validate_escalation_tuple,
)
from kanban.custom_fields.manifest import compute_field_manifest_sha256

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.committed_db


def test_01_scope_principal_matrix_valid_tuples() -> None:
    """Validate all 6 valid (target_scope, credential_mode) combinations in S13.2."""
    assert required_approver_tier("PROJECT", "INVOKING_USER") is None
    assert validate_escalation_tuple("PROJECT", "INVOKING_USER") is None

    assert required_approver_tier("PROJECT", "PROJECT_ADMIN_SP") == "PROJECT_ADMIN"
    assert validate_escalation_tuple("PROJECT", "PROJECT_ADMIN_SP") == "PROJECT_ADMIN"

    assert required_approver_tier("WORKSPACE", "INVOKING_USER") == "WORKSPACE_ADMIN"
    assert validate_escalation_tuple("WORKSPACE", "INVOKING_USER") == "WORKSPACE_ADMIN"

    assert required_approver_tier("WORKSPACE", "PROJECT_ADMIN_SP") == "WORKSPACE_ADMIN"
    assert validate_escalation_tuple("WORKSPACE", "PROJECT_ADMIN_SP") == "WORKSPACE_ADMIN"

    assert required_approver_tier("SERVER", "INVOKING_USER") == "SERVER_ADMIN_DUAL"
    assert validate_escalation_tuple("SERVER", "INVOKING_USER") == "SERVER_ADMIN_DUAL"

    assert required_approver_tier("SERVER", "SERVER_ADMIN_SP") == "SERVER_ADMIN_DUAL"
    assert validate_escalation_tuple("SERVER", "SERVER_ADMIN_SP") == "SERVER_ADMIN_DUAL"


def test_02_scope_principal_matrix_invalid_tuples() -> None:
    """Invalid Scope x Principal tuples reject with 422 ESCALATION_COMBO_INVALID."""
    invalid_tuples = [
        ("PROJECT", "SERVER_ADMIN_SP"),
        ("WORKSPACE", "SERVER_ADMIN_SP"),
        ("SERVER", "PROJECT_ADMIN_SP"),
        ("UNKNOWN", "INVOKING_USER"),
        ("PROJECT", "UNKNOWN"),
    ]
    for scope, cred in invalid_tuples:
        with pytest.raises(ProblemException) as exc_info:
            validate_escalation_tuple(scope, cred)
        assert exc_info.value.status == 422
        assert exc_info.value.code == "ESCALATION_COMBO_INVALID"

        with pytest.raises(ProblemException) as exc_info:
            required_approver_tier(scope, cred)
        assert exc_info.value.status == 422
        assert exc_info.value.code == "ESCALATION_COMBO_INVALID"


def test_03_compute_approval_signature_hmac() -> None:
    """HMAC-SHA256 derivation is deterministic, 32 bytes, and sensitive to every field."""
    pepper = b"\x42" * 32
    fid = uuid.uuid4()
    m_sha = hashlib.sha256(b"manifest-payload").digest()
    p_admin = uuid.uuid4()
    s_admin = uuid.uuid4()

    sig1 = compute_approval_signature_hmac(
        field_id=fid,
        manifest_sha256=m_sha,
        target_scope="SERVER",
        credential_mode="SERVER_ADMIN_SP",
        primary_approver_id=p_admin,
        secondary_approver_id=s_admin,
        auth_pepper=pepper,
    )
    assert len(sig1) == 32

    # Determinism
    sig1_repeat = compute_approval_signature_hmac(
        field_id=fid,
        manifest_sha256=m_sha,
        target_scope="SERVER",
        credential_mode="SERVER_ADMIN_SP",
        primary_approver_id=p_admin,
        secondary_approver_id=s_admin,
        auth_pepper=pepper,
    )
    assert sig1 == sig1_repeat

    # Secondary approver None vs set
    sig_none_sec = compute_approval_signature_hmac(
        field_id=fid,
        manifest_sha256=m_sha,
        target_scope="PROJECT",
        credential_mode="PROJECT_ADMIN_SP",
        primary_approver_id=p_admin,
        secondary_approver_id=None,
        auth_pepper=pepper,
    )
    assert len(sig_none_sec) == 32
    assert sig_none_sec != sig1

    # Tamper each field
    sig_alt_fid = compute_approval_signature_hmac(
        field_id=uuid.uuid4(),
        manifest_sha256=m_sha,
        target_scope="SERVER",
        credential_mode="SERVER_ADMIN_SP",
        primary_approver_id=p_admin,
        secondary_approver_id=s_admin,
        auth_pepper=pepper,
    )
    assert sig_alt_fid != sig1

    sig_alt_manifest = compute_approval_signature_hmac(
        field_id=fid,
        manifest_sha256=hashlib.sha256(b"tampered").digest(),
        target_scope="SERVER",
        credential_mode="SERVER_ADMIN_SP",
        primary_approver_id=p_admin,
        secondary_approver_id=s_admin,
        auth_pepper=pepper,
    )
    assert sig_alt_manifest != sig1

    sig_alt_pepper = compute_approval_signature_hmac(
        field_id=fid,
        manifest_sha256=m_sha,
        target_scope="SERVER",
        credential_mode="SERVER_ADMIN_SP",
        primary_approver_id=p_admin,
        secondary_approver_id=s_admin,
        auth_pepper=b"\x99" * 32,
    )
    assert sig_alt_pepper != sig1


def test_04_compute_cache_partition_key() -> None:
    """Validate S13.2 cache partitioning rules for all valid tuples."""
    dummy_issue = uuid.uuid4()
    dummy_field = uuid.uuid4()
    version = 1
    user_hash1 = hashlib.sha256(b"user1-groups-and-acls").digest()
    user_hash2 = hashlib.sha256(b"user2-groups-and-acls").digest()

    # 1. SERVER scope always returns should_cache=False
    can_cache_server1, key_server1 = compute_cache_partition_key(
        "SERVER", "INVOKING_USER", dummy_issue, dummy_field, version, user_hash1
    )
    assert can_cache_server1 is False
    assert key_server1 == b""

    can_cache_server2, key_server2 = compute_cache_partition_key(
        "SERVER", "SERVER_ADMIN_SP", dummy_issue, dummy_field, version, user_hash1
    )
    assert can_cache_server2 is False
    assert key_server2 == b""

    # 2. Service Principal modes return should_cache=True, partitioned with b""
    can_cache_sp1, key_sp1 = compute_cache_partition_key(
        "PROJECT", "PROJECT_ADMIN_SP", dummy_issue, dummy_field, version, user_hash1
    )
    assert can_cache_sp1 is True
    assert key_sp1 == b""

    can_cache_sp2, key_sp2 = compute_cache_partition_key(
        "WORKSPACE", "PROJECT_ADMIN_SP", dummy_issue, dummy_field, version, user_hash2
    )
    assert can_cache_sp2 is True
    assert key_sp2 == b""

    # 3. INVOKING_USER modes return should_cache=True, partitioned with user_access_hash
    can_cache_u1, key_u1 = compute_cache_partition_key(
        "PROJECT", "INVOKING_USER", dummy_issue, dummy_field, version, user_hash1
    )
    assert can_cache_u1 is True
    assert key_u1 == user_hash1

    can_cache_u2, key_u2 = compute_cache_partition_key(
        "WORKSPACE", "INVOKING_USER", dummy_issue, dummy_field, version, user_hash2
    )
    assert can_cache_u2 is True
    assert key_u2 == user_hash2
    assert key_u1 != key_u2


@pytest.mark.asyncio
async def test_05_assert_execution_authorized_passthrough(db_session: AsyncSession) -> None:
    """(PROJECT, INVOKING_USER) baseline succeeds immediately without querying approvals."""
    definition = CustomFieldDefinition(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        slug="baseline-field",
        name="Baseline Field",
        tier="wasm",
        output_format="text",
        output_format_metadata={"format": "text"},
        script_source="export default () => 1;",
        script_version=1,
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
        egress_allowlist=[],
        manifest_sha256=b"\x11" * 32,
        is_enabled=True,
        created_by_id=uuid.uuid4(),
    )
    res = await assert_execution_authorized(db_session, definition)
    assert res is None


@pytest.mark.asyncio
async def test_06_assert_execution_authorized_escalated(  # noqa: PLR0915
    db_session: AsyncSession,
) -> None:
    """Escalated fields fail closed unless an APPROVED row with valid HMAC signature exists."""
    pepper = b"\x55" * 32
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    sa_id = uuid.uuid4()

    # Seed workspace, project, principals
    await db_session.execute(text("RESET SESSION AUTHORIZATION"))
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}", "name": "Custom Fields WS"},
    )

    for pid, dname in (
        (admin_id, "Project Admin"),
        (sa_id, "Server Admin"),
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

    ident = f"P{uuid.uuid4().hex[:4].upper()}"
    proj_id = await db_session.scalar(
        text(
            "SELECT register_object("
            "'project'::object_kind, :ws, NULL, :ident, 'Custom Field Proj', :uid)"
        ),
        {"ws": ws_id, "ident": ident, "uid": admin_id},
    )
    assert isinstance(proj_id, uuid.UUID)
    await db_session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws_id, :ident, 'Custom Field Proj')"
        ),
        {
            "id": proj_id,
            "ws_id": ws_id,
            "ident": ident,
        },
    )

    field_id = uuid.uuid4()
    fid = field_id
    source = "export default () => 'escalated';"
    meta = {"format": "text", "max_length": 100}
    m_sha = compute_field_manifest_sha256(
        script_source=source,
        output_format="text",
        output_format_metadata=meta,
        target_scope="PROJECT",
        credential_mode="PROJECT_ADMIN_SP",
    )

    await db_session.execute(
        text(
            "INSERT INTO custom_field_definitions ("
            "  id, workspace_id, project_id, slug, name, tier, output_format, "
            "  output_format_metadata, script_source, script_version, target_scope, "
            "  credential_mode, egress_allowlist, manifest_sha256, is_enabled, created_by_id"
            ") VALUES ("
            "  :id, :ws, :proj, 'sp-field', 'SP Field', 'wasm', 'text', "
            "  CAST(:meta AS jsonb), :source, 1, 'PROJECT', "
            "  'PROJECT_ADMIN_SP', '{}', :m, true, :uid"
            ")"
        ),
        {
            "id": field_id,
            "ws": ws_id,
            "proj": proj_id,
            "meta": json.dumps(meta),
            "source": source,
            "m": m_sha,
            "uid": admin_id,
        },
    )

    field_def = (
        (
            await db_session.execute(
                text("SELECT * FROM custom_field_definitions WHERE id = :id"),
                {"id": field_id},
            )
        )
        .mappings()
        .one()
    )

    # 1. No approval record -> fails closed
    definition = CustomFieldDefinition(
        id=field_def["id"],
        workspace_id=field_def["workspace_id"],
        project_id=field_def["project_id"],
        slug=field_def["slug"],
        name=field_def["name"],
        tier=field_def["tier"],
        output_format=field_def["output_format"],
        output_format_metadata=field_def["output_format_metadata"],
        script_source=field_def["script_source"],
        script_version=field_def["script_version"],
        target_scope=field_def["target_scope"],
        credential_mode=field_def["credential_mode"],
        egress_allowlist=field_def["egress_allowlist"],
        manifest_sha256=field_def["manifest_sha256"],
        is_enabled=field_def["is_enabled"],
        created_by_id=field_def["created_by_id"],
    )

    with pytest.raises(ApprovalRevokedError) as exc_info:
        await assert_execution_authorized(db_session, definition, auth_pepper=pepper)
    assert exc_info.value.code == "APPROVAL_REVOKED"

    # 2. Status is PENDING -> fails closed
    appr_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO custom_field_approvals ("
            "  id, workspace_id, project_id, field_id, manifest_sha256, "
            "  target_scope, credential_mode, required_tier, status, "
            "  requested_by_id, justification"
            ") VALUES ("
            "  :id, :ws, :proj, :fid, :m, "
            "  'PROJECT', 'PROJECT_ADMIN_SP', 'PROJECT_ADMIN', 'PENDING', "
            "  :uid, 'Justification for testing status'"
            ")"
        ),
        {
            "id": appr_id,
            "ws": ws_id,
            "proj": proj_id,
            "fid": field_id,
            "m": m_sha,
            "uid": admin_id,
        },
    )

    with pytest.raises(ApprovalRevokedError):
        await assert_execution_authorized(db_session, definition, auth_pepper=pepper)

    # 3. Status is APPROVED with invalid signature -> fails closed
    await db_session.execute(
        text(
            "UPDATE custom_field_approvals "
            "SET status = 'APPROVED', primary_approver_id = :admin, "
            "    approval_signature_hmac = :bad_hmac "
            "WHERE id = :id"
        ),
        {"id": appr_id, "admin": admin_id, "bad_hmac": b"\x00" * 32},
    )
    def_row = await db_session.get(CustomFieldDefinition, fid)
    assert def_row is not None
    definition = def_row

    with pytest.raises(ApprovalRevokedError) as exc_info:
        await assert_execution_authorized(db_session, definition, auth_pepper=pepper)
    assert "tamper detected" in str(exc_info.value)

    # 4. Status is APPROVED with valid signature -> succeeds
    valid_hmac = compute_approval_signature_hmac(
        field_id=field_id,
        manifest_sha256=m_sha,
        target_scope="PROJECT",
        credential_mode="PROJECT_ADMIN_SP",
        primary_approver_id=admin_id,
        secondary_approver_id=None,
        auth_pepper=pepper,
    )
    appr_obj = await db_session.get(CustomFieldApproval, appr_id)
    assert appr_obj is not None
    appr_obj.approval_signature_hmac = valid_hmac
    await db_session.flush()

    auth_record = await assert_execution_authorized(db_session, definition, auth_pepper=pepper)
    assert auth_record is not None
    assert auth_record.id == appr_id
    assert auth_record.status == "APPROVED"

    # 5. Default auth_pepper (loads from environment pepper b"\x31" * 32)
    env_hmac = compute_approval_signature_hmac(
        field_id=field_id,
        manifest_sha256=m_sha,
        target_scope="PROJECT",
        credential_mode="PROJECT_ADMIN_SP",
        primary_approver_id=admin_id,
        secondary_approver_id=None,
        auth_pepper=b"\x31" * 32,
    )
    appr_obj.approval_signature_hmac = env_hmac
    await db_session.flush()

    auth_default = await assert_execution_authorized(db_session, definition)
    assert auth_default is not None


@pytest.mark.asyncio
async def test_08_assert_execution_authorized_missing_signature_fields(
    db_session: AsyncSession,
) -> None:
    """Missing signature fields raise ApprovalRevokedError."""
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    await db_session.execute(text("RESET SESSION AUTHORIZATION"))
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'WS')"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}"},
    )
    await db_session.execute(
        text("SELECT register_object('user'::object_kind, :ws, NULL, :ckey, 'Admin', :uid, :id)"),
        {"ws": ws_id, "ckey": f"usr-{admin_id.hex[:8]}", "uid": admin_id, "id": admin_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
            "VALUES (:id, :ws_id, 'USER', 'Admin')"
        ),
        {"id": admin_id, "ws_id": ws_id},
    )
    await db_session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, 'a@k.io')"),
        {"id": admin_id, "ws_id": ws_id},
    )
    ident = f"P{uuid.uuid4().hex[:4].upper()}"
    proj_id = await db_session.scalar(
        text("SELECT register_object('project'::object_kind, :ws, NULL, :ident, 'Proj', :uid)"),
        {"ws": ws_id, "ident": ident, "uid": admin_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws_id, :ident, 'Proj')"
        ),
        {"id": proj_id, "ws_id": ws_id, "ident": ident},
    )

    fid = uuid.uuid4()
    m_sha = compute_field_manifest_sha256(
        script_source="export default () => 1;",
        output_format="text",
        output_format_metadata={"format": "text"},
        target_scope="PROJECT",
        credential_mode="PROJECT_ADMIN_SP",
    )
    await db_session.execute(
        text(
            "INSERT INTO custom_field_definitions ("
            "  id, workspace_id, project_id, slug, name, tier, output_format, "
            "  output_format_metadata, script_source, script_version, target_scope, "
            "  credential_mode, egress_allowlist, manifest_sha256, is_enabled, created_by_id"
            ") VALUES ("
            "  :id, :ws, :proj, 'sig-field', 'Sig Field', 'wasm', 'text', "
            "  '{\"format\": \"text\"}', 'export default () => 1;', 1, 'PROJECT', "
            "  'PROJECT_ADMIN_SP', '{}', :m, true, :uid"
            ")"
        ),
        {"id": fid, "ws": ws_id, "proj": proj_id, "m": m_sha, "uid": admin_id},
    )

    def_row = await db_session.get(CustomFieldDefinition, fid)
    assert def_row is not None
    definition = def_row

    appr_id = uuid.uuid4()
    # Row with NULL signature and NULL primary_approver_id
    await db_session.execute(
        text(
            "INSERT INTO custom_field_approvals ("
            "  id, workspace_id, project_id, field_id, manifest_sha256, "
            "  target_scope, credential_mode, required_tier, status, "
            "  requested_by_id, justification, primary_approver_id, approval_signature_hmac"
            ") VALUES ("
            "  :id, :ws, :proj, :fid, :m, "
            "  'PROJECT', 'PROJECT_ADMIN_SP', 'PROJECT_ADMIN', 'APPROVED', "
            "  :uid, 'Valid justification text', NULL, NULL"
            ")"
        ),
        {"id": appr_id, "ws": ws_id, "proj": proj_id, "fid": fid, "m": m_sha, "uid": admin_id},
    )
    def_row = await db_session.get(CustomFieldDefinition, fid)
    assert def_row is not None
    definition = def_row

    with pytest.raises(ApprovalRevokedError) as exc_info:
        await assert_execution_authorized(db_session, definition)
    assert "invalid or missing approval signature" in str(exc_info.value)


@pytest.mark.asyncio
async def test_09_get_active_approval_summary(db_session: AsyncSession) -> None:
    """Test get_active_approval_summary for baseline, unapproved, and approved definitions."""
    ws_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    admin_id = uuid.uuid4()

    await db_session.execute(text("RESET SESSION AUTHORIZATION"))
    await db_session.execute(
        text("INSERT INTO workspaces (id, slug, name) VALUES (:id, :slug, 'WS')"),
        {"id": ws_id, "slug": f"ws-{ws_id.hex[:10]}"},
    )
    await db_session.execute(
        text("SELECT register_object('user'::object_kind, :ws, NULL, :ckey, 'Admin', :uid, :id)"),
        {"ws": ws_id, "ckey": f"usr-{admin_id.hex[:8]}", "uid": admin_id, "id": admin_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO principals (id, workspace_id, principal_type, display_name) "
            "VALUES (:id, :ws_id, 'USER', 'Admin')"
        ),
        {"id": admin_id, "ws_id": ws_id},
    )
    await db_session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, 'a@k.io')"),
        {"id": admin_id, "ws_id": ws_id},
    )
    ident = f"P{uuid.uuid4().hex[:4].upper()}"
    proj_id = await db_session.scalar(
        text("SELECT register_object('project'::object_kind, :ws, NULL, :ident, 'Proj', :uid)"),
        {"ws": ws_id, "ident": ident, "uid": admin_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws_id, :ident, 'Proj')"
        ),
        {"id": proj_id, "ws_id": ws_id, "ident": ident},
    )

    # 1. Baseline definition
    base_def = CustomFieldDefinition(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        project_id=proj_id,
        slug="base-field",
        name="Base Field",
        tier="wasm",
        output_format="text",
        output_format_metadata={"format": "text"},
        script_source="export default () => 1;",
        script_version=1,
        target_scope="PROJECT",
        credential_mode="INVOKING_USER",
        egress_allowlist=[],
        manifest_sha256=b"\x01" * 32,
        is_enabled=True,
        created_by_id=admin_id,
    )
    status_base, tier_base = await CustomFieldApprovalService.get_active_approval_summary(
        db_session, base_def
    )
    assert status_base == "default_no_escalation"
    assert tier_base is None

    # 2. Escalated definition with no approval row -> UNAPPROVED
    fid = uuid.uuid4()
    m_sha = compute_field_manifest_sha256(
        script_source="export default () => 1;",
        output_format="text",
        output_format_metadata={"format": "text"},
        target_scope="PROJECT",
        credential_mode="PROJECT_ADMIN_SP",
    )
    await db_session.execute(
        text(
            "INSERT INTO custom_field_definitions ("
            "  id, workspace_id, project_id, slug, name, tier, output_format, "
            "  output_format_metadata, script_source, script_version, target_scope, "
            "  credential_mode, egress_allowlist, manifest_sha256, is_enabled, created_by_id"
            ") VALUES ("
            "  :id, :ws, :proj, 'summary-field', 'Summary Field', 'wasm', 'text', "
            "  '{\"format\": \"text\"}', 'export default () => 1;', 1, 'PROJECT', "
            "  'PROJECT_ADMIN_SP', '{}', :m, true, :uid"
            ")"
        ),
        {"id": fid, "ws": ws_id, "proj": proj_id, "m": m_sha, "uid": admin_id},
    )
    esc_def = await db_session.get(CustomFieldDefinition, fid)
    assert esc_def is not None

    status_esc, tier_esc = await CustomFieldApprovalService.get_active_approval_summary(
        db_session, esc_def
    )
    assert status_esc == "UNAPPROVED"
    assert tier_esc == "PROJECT_ADMIN"

    # 3. Add PENDING approval row -> returns PENDING
    await db_session.execute(
        text(
            "INSERT INTO custom_field_approvals ("
            "  id, workspace_id, project_id, field_id, manifest_sha256, "
            "  target_scope, credential_mode, required_tier, status, "
            "  requested_by_id, justification"
            ") VALUES ("
            "  :id, :ws, :proj, :fid, :m, "
            "  'PROJECT', 'PROJECT_ADMIN_SP', 'PROJECT_ADMIN', 'PENDING', "
            "  :uid, 'Valid justification text'"
            ")"
        ),
        {"id": uuid.uuid4(), "ws": ws_id, "proj": proj_id, "fid": fid, "m": m_sha, "uid": admin_id},
    )
    def_row = await db_session.get(CustomFieldDefinition, fid)
    assert def_row is not None
    definition = def_row

    status_pend, tier_pend = await CustomFieldApprovalService.get_active_approval_summary(
        db_session, definition
    )
    assert status_pend == "PENDING"
    assert tier_pend == "PROJECT_ADMIN"


def test_07_approval_service_serialization() -> None:
    """Test CustomFieldApprovalService.serialize method."""
    row = CustomFieldApproval(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        field_id=uuid.uuid4(),
        manifest_sha256=b"\xab" * 32,
        target_scope="PROJECT",
        credential_mode="PROJECT_ADMIN_SP",
        required_tier="PROJECT_ADMIN",
        status="PENDING",
        requested_by_id=uuid.uuid4(),
        justification="Valid justification string",
        primary_approver_id=None,
        primary_approver_aal=None,
        primary_approved_at=None,
        secondary_approver_id=None,
        secondary_approver_aal=None,
        secondary_approved_at=None,
        sp_warning_acknowledged=False,
        approval_signature_hmac=None,
        revoked_at=None,
        revoked_reason=None,
    )
    res = CustomFieldApprovalService.serialize(row)
    assert res.id == row.id
    assert res.manifest_sha256 == ("ab" * 32)
    assert res.status == "PENDING"
    assert res.target_scope == "PROJECT"
    assert res.credential_mode == "PROJECT_ADMIN_SP"
